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
def app(tmp_path, fake_renderer):
    return create_app(
        Settings(data_dir=tmp_path, frontend_dir=Path("/not-built")),
        provider=SampleProvider(),
        renderer=fake_renderer,
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        client.get("/api/session")
        client.headers["X-Forma-Request"] = "1"
        yield client
