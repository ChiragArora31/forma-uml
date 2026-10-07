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
CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner, updated_at);
CREATE INDEX IF NOT EXISTS revisions_conversation ON revisions(conversation_id, number);
CREATE INDEX IF NOT EXISTS feedback_revision ON feedback(revision_id);
