"""Apply versioned hosted migrations using Neon's direct connection, before deployment."""

from pathlib import Path

import psycopg

from app.config import Settings
from app.store import now


def main():
    settings = Settings()
    url = settings.database_url_unpooled or settings.database_url
    if not url:
        raise SystemExit("Configure DATABASE_URL_UNPOOLED before running hosted migrations")
    with psycopg.connect(url, connect_timeout=15) as db:
        db.execute("SELECT pg_advisory_xact_lock(687076265)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if db.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,)).fetchone():
                continue
            db.execute(path.read_text(), prepare=False)
            db.execute("INSERT INTO schema_migrations VALUES (%s,%s)", (version, now()))
            print(f"Applied migration {version:03}")


if __name__ == "__main__":
    main()
