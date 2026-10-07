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


class QuotaExceeded(ValueError):
    pass


def now():
    return datetime.now(UTC).isoformat()


def fingerprint(data):
    if isinstance(data, dict) and data.get("mode") is None:
        data = {k: v for k, v in data.items() if k != "mode"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


class Store:
    def __init__(self, path: Path, database_url: str | None = None):
        self.database_url = database_url
        if database_url:
            self.path = "postgres"
            return
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
            CREATE TABLE IF NOT EXISTS generation_leases (
                owner TEXT PRIMARY KEY, request_id TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_usage (
                owner TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
                PRIMARY KEY(owner, day)
            );
            CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner, updated_at);
            CREATE INDEX IF NOT EXISTS revisions_conversation ON revisions(conversation_id, number);
            CREATE INDEX IF NOT EXISTS feedback_revision ON feedback(revision_id);
            CREATE INDEX IF NOT EXISTS provider_usage_day ON provider_usage(day);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(conversations)")}
            if "custom_title" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN custom_title TEXT")
            if "archived" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def db(self):
        if self.database_url:
            import psycopg
            from psycopg.rows import dict_row

            from app.postgres import PostgresConnection

            connection = psycopg.connect(
                self.database_url, connect_timeout=10, row_factory=dict_row, prepare_threshold=None
            )
            db = PostgresConnection(connection)
        else:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            db = connection
        try:
            yield db
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_conversations(self, owner, archived=False):
        with self.db() as db:
            return [
                {**dict(x), "archived": bool(x["archived"])}
                for x in db.execute(
                    "SELECT id,COALESCE(custom_title,title) AS title,created_at,updated_at,latest,archived "
                    "FROM conversations WHERE owner=? AND archived=? ORDER BY updated_at DESC LIMIT 100",
                    (owner, int(archived)),
                )
            ]

    def ready(self):
        with self.db() as db:
            db.execute("SELECT latest,archived,custom_title FROM conversations LIMIT 0")
            db.execute("SELECT count FROM provider_usage LIMIT 0")
        return True

    def conversation(self, owner, cid):
        with self.db() as db:
            row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=?", (cid, owner)).fetchone()
            if not row:
                raise NotFound("Conversation not found")
            revisions = db.execute("SELECT * FROM revisions WHERE conversation_id=? ORDER BY number", (cid,))
            return {
                **{k: row[k] for k in ["id", "title", "created_at", "updated_at", "latest"]},
                "title": row["custom_title"] or row["title"],
                "archived": bool(row["archived"]),
                "revisions": [self.decode_revision(x) for x in revisions],
            }

    @staticmethod
    def decode_revision(row):
        result = dict(row)
        for key in ["architecture", "diagrams", "timings"]:
            result[key] = json.loads(result[key])
        trace = json.loads(result.pop("trace", "{}"))
        result["model"] = trace.get("model")
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
                    "SELECT latest,archived FROM conversations WHERE id=? AND owner=?"
                    + (" FOR UPDATE" if self.database_url else ""),
                    (cid, owner),
                ).fetchone()
                if not current:
                    raise NotFound("Conversation not found")
                if current["archived"]:
                    raise Conflict("Restore this archived design before creating a new revision.")
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
                    "INSERT INTO conversations (id,owner,title,created_at,updated_at,latest) VALUES (?,?,?,?,?,?)",
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

    def claim_generation(self, owner, request_id, maximum=4):
        import time

        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.database_url:
                # Transaction-scoped across every container; does not require session affinity.
                db.execute("SELECT pg_advisory_xact_lock(687076266)")
            stamp = time.time()
            db.execute("DELETE FROM generation_leases WHERE expires_at<=?", (stamp,))
            if db.execute("SELECT 1 FROM generation_leases WHERE owner=?", (owner,)).fetchone():
                raise Conflict("A design is already in progress. Please wait for it to finish.")
            if db.execute("SELECT COUNT(*) AS count FROM generation_leases").fetchone()["count"] >= maximum:
                raise Conflict("All design workers are busy. Please retry shortly.")
            db.execute("INSERT INTO generation_leases VALUES (?,?,?)", (owner, request_id, stamp + 300))

    def release_generation(self, owner, request_id):
        with self.db() as db:
            db.execute("DELETE FROM generation_leases WHERE owner=? AND request_id=?", (owner, request_id))

    def update_conversation(self, owner, cid, update):
        changes = update.model_dump(exclude_none=True)
        assignments, values = [], []
        if "title" in changes:
            assignments.append("custom_title=?")
            values.append(changes["title"])
        if "archived" in changes:
            assignments.append("archived=?")
            values.append(int(changes["archived"]))
        with self.db() as db:
            updated = db.execute(
                "UPDATE conversations SET " + ",".join(assignments) + ",updated_at=? WHERE id=? AND owner=?",
                (*values, now(), cid, owner),
            )
            if not updated.rowcount:
                raise NotFound("Conversation not found")
        return self.conversation(owner, cid)

    def quota(self, owner, owner_limit, global_limit):
        day = now()[:10]
        with self.db() as db:
            rows = db.execute("SELECT owner,count FROM provider_usage WHERE day=?", (day,)).fetchall()
        used = sum(row["count"] for row in rows if row["owner"] == owner)
        total = sum(row["count"] for row in rows)
        return {"remaining": max(0, min(owner_limit - used, global_limit - total)), "limit": owner_limit}

    def reserve_live_generation(self, owner, owner_limit, global_limit):
        day = now()[:10]
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.database_url:
                db.execute("SELECT pg_advisory_xact_lock(687076267)")
            rows = db.execute("SELECT owner,count FROM provider_usage WHERE day=?", (day,)).fetchall()
            used = sum(row["count"] for row in rows if row["owner"] == owner)
            total = sum(row["count"] for row in rows)
            if used >= owner_limit or total >= global_limit:
                raise QuotaExceeded(
                    "Today's free AI allowance is used. Your designs are safe. Explore the case study or return tomorrow."
                )
            db.execute(
                "INSERT INTO provider_usage (owner,day,count) VALUES (?,?,1) "
                "ON CONFLICT(owner,day) DO UPDATE SET count=provider_usage.count+1",
                (owner, day),
            )
