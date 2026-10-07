from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.provider import SampleProvider


class FakeRenderer:
    def __init__(self):
        self.calls = []

    async def render(self, source):
        self.calls.append(source)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text>verified</text></svg>',
            False,
        )


@pytest.fixture
def fake_renderer():
    return FakeRenderer()


@pytest.fixture
def app(tmp_path, fake_renderer, request):
    dsn = (
        "postgresql://postgres:forma-test@127.0.0.1:5438/forma_test"
        if request.config.getoption("--postgres")
        else None
    )
    if dsn:
        import psycopg

        with psycopg.connect(dsn) as db:
            db.execute(
                "TRUNCATE training_outbox, feedback, revisions, conversations, generation_leases CASCADE"
            )
    return create_app(
        Settings(_env_file=None, database_url=dsn, data_dir=tmp_path, frontend_dir=Path("/not-built")),
        provider=SampleProvider(),
        renderer=fake_renderer,
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        client.get("/api/session")
        client.headers["X-Forma-Request"] = "1"
        yield client


@pytest.fixture
def admission_database(app):
    # The app fixture resets only the explicitly selected disposable local database.
    return app.state.store.database_url


def pytest_addoption(parser):
    parser.addoption(
        "--postgres",
        action="store_true",
        help="Run API boundaries against the disposable local Postgres test database",
    )
