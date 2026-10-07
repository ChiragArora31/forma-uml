import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class Conflict(ValueError):
    pass


class NotFound(ValueError):
    pass


def now():
    return datetime.now(UTC).isoformat()


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, latest INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                number INTEGER NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                prompt TEXT NOT NULL, architecture TEXT NOT NULL, diagrams TEXT NOT NULL,
                trace TEXT NOT NULL, timings TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(conversation_id, number), UNIQUE(request_id)
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                revision_id TEXT NOT NULL REFERENCES revisions(id), rating INTEGER NOT NULL,
                comment TEXT NOT NULL, diagram_type TEXT, request_id TEXT UNIQUE NOT NULL,
                request_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS training_outbox (
                id TEXT PRIMARY KEY, feedback_id TEXT UNIQUE NOT NULL REFERENCES feedback(id),
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner, updated_at);
            CREATE INDEX IF NOT EXISTS revisions_conversation ON revisions(conversation_id, number);
            CREATE INDEX IF NOT EXISTS feedback_revision ON feedback(revision_id);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def list_conversations(self, owner):
        with self.db() as db:
            return [
                dict(x)
                for x in db.execute(
                    "SELECT id,title,created_at,updated_at,latest FROM conversations "
                    "WHERE owner=? ORDER BY updated_at DESC LIMIT 100",
                    (owner,),
                )
            ]

    def conversation(self, owner, cid):
        with self.db() as db:
            row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=?", (cid, owner)).fetchone()
            if not row:
                raise NotFound("Conversation not found")
            revisions = db.execute("SELECT * FROM revisions WHERE conversation_id=? ORDER BY number", (cid,))
            return {
                **{k: row[k] for k in ["id", "title", "created_at", "updated_at", "latest"]},
                "revisions": [self.decode_revision(x) for x in revisions],
            }

    @staticmethod
    def decode_revision(row):
        result = dict(row)
        for key in ["architecture", "diagrams", "timings"]:
            result[key] = json.loads(result[key])
        result.pop("trace", None)
        result.pop("request_hash", None)
        return result

    def revision(self, owner, rid):
        with self.db() as db:
            row = db.execute(
                "SELECT r.* FROM revisions r JOIN conversations c ON c.id=r.conversation_id "
                "WHERE r.id=? AND c.owner=?",
                (rid, owner),
            ).fetchone()
            if not row:
                raise NotFound("Revision not found")
            return self.decode_revision(row)

    def replay(self, owner, request):
        with self.db() as db:
            row = db.execute(
                "SELECT r.*,c.owner FROM revisions r JOIN conversations c ON c.id=r.conversation_id "
                "WHERE r.request_id=?",
                (str(request.request_id),),
            ).fetchone()
            if not row:
                return None
            if row["owner"] != owner or row["request_hash"] != fingerprint(request.model_dump(mode="json")):
                raise Conflict("This request ID has already been used for a different request")
            result = self.decode_revision(row)
            result.pop("owner", None)
            return result

    def save_revision(self, owner, request, state, mode):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT request_hash FROM revisions WHERE request_id=?", (str(request.request_id),)
            ).fetchone()
            if existing:
                raise Conflict("This request has already completed. Reload the conversation.")
            cid = str(request.conversation_id) if request.conversation_id else str(uuid4())
            if request.conversation_id:
                current = db.execute(
                    "SELECT latest FROM conversations WHERE id=? AND owner=?", (cid, owner)
                ).fetchone()
                if not current:
                    raise NotFound("Conversation not found")
                if current["latest"] != request.base_revision:
                    raise Conflict("The conversation changed. Reload the latest revision before updating.")
                number = current["latest"] + 1
                db.execute(
                    "UPDATE conversations SET latest=?,updated_at=?,title=? WHERE id=?",
                    (number, now(), state["architecture"].title, cid),
                )
            else:
                number = 1
                db.execute(
                    "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                    (cid, owner, state["architecture"].title, now(), now(), number),
                )
            rid = str(uuid4())
            db.execute(
                "INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    cid,
                    number,
                    str(request.request_id),
                    fingerprint(request.model_dump(mode="json")),
                    request.prompt,
                    state["architecture"].model_dump_json(),
                    json.dumps(state["diagrams"]),
                    json.dumps(state["trace"]),
                    json.dumps(state["timings"]),
                    mode,
                    now(),
                ),
            )
            row = db.execute("SELECT * FROM revisions WHERE id=?", (rid,)).fetchone()
            return self.decode_revision(row)

    def feedback_for(self, owner, cid):
        with self.db() as db:
            return [
                dict(x)
                for x in db.execute(
                    "SELECT f.rating,f.comment,f.diagram_type,r.number AS revision FROM feedback f "
                    "JOIN revisions r ON r.id=f.revision_id JOIN conversations c ON c.id=r.conversation_id "
                    "WHERE c.id=? AND c.owner=? ORDER BY f.created_at DESC LIMIT 8",
                    (cid, owner),
                )
            ]

    def save_feedback(self, owner, request):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM feedback WHERE request_id=?", (str(request.request_id),)
            ).fetchone()
            if existing:
                if existing["owner"] != owner or existing["request_hash"] != fingerprint(
                    request.model_dump(mode="json")
                ):
                    raise Conflict("This feedback request ID has already been used")
                return self.feedback_result(db, existing["id"])
            revision = db.execute(
                "SELECT r.* FROM revisions r JOIN conversations c ON c.id=r.conversation_id "
                "WHERE r.id=? AND c.owner=?",
                (str(request.revision_id), owner),
            ).fetchone()
            if not revision:
                raise NotFound("Revision not found")
            if request.diagram_type and request.diagram_type.value not in {
                d["type"] for d in json.loads(revision["diagrams"])
            }:
                raise Conflict("The selected diagram does not belong to this revision")
            fid = str(uuid4())
            db.execute(
                "INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    fid,
                    owner,
                    str(request.revision_id),
                    request.rating,
                    request.comment,
                    request.diagram_type.value if request.diagram_type else None,
                    str(request.request_id),
                    fingerprint(request.model_dump(mode="json")),
                    now(),
                ),
            )
            previous = db.execute(
                "SELECT architecture FROM revisions WHERE conversation_id=? AND number=?",
                (revision["conversation_id"], revision["number"] - 1),
            ).fetchone()
            payload = {
                "schema_version": 1,
                "feedback_id": fid,
                "revision_id": revision["id"],
                "conversation_id": revision["conversation_id"],
                "revision": revision["number"],
                "prompt": revision["prompt"],
                "previous_design": json.loads(previous["architecture"]) if previous else None,
                "architecture": json.loads(revision["architecture"]),
                "diagrams": json.loads(revision["diagrams"]),
                "trace": json.loads(revision["trace"]),
                "mode": revision["mode"],
                "rating": request.rating,
                "reward": (request.rating - 1) / 4,
                "comment": request.comment,
                "diagram_type": request.diagram_type,
                "created_at": now(),
            }
            db.execute(
                "INSERT INTO training_outbox (id,feedback_id,payload,updated_at) VALUES (?,?,?,?)",
                (str(uuid4()), fid, json.dumps(payload), now()),
            )
            return self.feedback_result(db, fid)

    @staticmethod
    def feedback_result(db, fid):
        row = db.execute(
            "SELECT f.id,f.revision_id,f.rating,f.comment,f.diagram_type,f.created_at,"
            "o.status AS training_status FROM feedback f JOIN training_outbox o ON o.feedback_id=f.id "
            "WHERE f.id=?",
            (fid,),
        ).fetchone()
        return dict(row)

    def feedback_list(self, owner, rid):
        self.revision(owner, rid)
        with self.db() as db:
            rows = db.execute(
                "SELECT id FROM feedback WHERE revision_id=? AND owner=? ORDER BY created_at", (rid, owner)
            ).fetchall()
            return [self.feedback_result(db, x["id"]) for x in rows]
