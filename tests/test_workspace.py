import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.provider import SampleProvider
from app.sample import ASYNC_PROMPT
from app.store import QuotaExceeded
from tests.test_api import completed, generate


def test_rename_survives_refinement_without_rewriting_blueprint(client):
    first = completed(generate(client))
    cid = first["conversation_id"]
    renamed = client.patch(f"/api/conversations/{cid}", json={"title": "My compliance workspace"})
    assert renamed.status_code == 200
    assert renamed.json()["revisions"][0]["architecture"]["title"] == first["architecture"]["title"]
    second = completed(generate(client, prompt=ASYNC_PROMPT, conversation_id=cid, base_revision=1))
    saved = client.get(f"/api/conversations/{cid}").json()
    assert saved["title"] == "My compliance workspace"
    assert saved["latest"] == second["number"] == 2


def test_archive_is_reversible_and_blocks_new_revisions(client):
    first = completed(generate(client))
    cid = first["conversation_id"]
    assert client.patch(f"/api/conversations/{cid}", json={"archived": True}).status_code == 200
    assert client.get("/api/conversations").json() == []
    assert client.get("/api/conversations?archived=true").json()[0]["id"] == cid
    assert client.get(f"/api/conversations/{cid}").json()["latest"] == 1
    assert generate(client, prompt=ASYNC_PROMPT, conversation_id=cid, base_revision=1).status_code == 409
    assert client.patch(f"/api/conversations/{cid}", json={"archived": False}).status_code == 200
    assert client.get("/api/conversations").json()[0]["id"] == cid


@pytest.mark.parametrize("payload", [{}, {"title": "   "}, {"title": "x" * 101}, {"archived": "invalid"}])
def test_management_validation_keeps_existing_design(client, payload):
    revision = completed(generate(client))
    assert client.patch(f"/api/conversations/{revision['conversation_id']}", json=payload).status_code == 422
    assert client.get("/api/conversations").json()[0]["title"] == revision["architecture"]["title"]


def test_foreign_browser_cannot_manage_or_export_report(app, client):
    revision = completed(generate(client))
    with TestClient(app) as other:
        other.get("/api/session")
        headers = {"X-Forma-Request": "1"}
        assert (
            other.patch(
                f"/api/conversations/{revision['conversation_id']}", json={"archived": True}, headers=headers
            ).status_code
            == 404
        )
        assert other.get(f"/api/revisions/{revision['id']}/report").status_code == 404
    assert client.get("/api/conversations").json()[0]["latest"] == 1


def test_management_requires_mutation_header(client):
    revision = completed(generate(client))
    del client.headers["X-Forma-Request"]
    assert (
        client.patch(
            f"/api/conversations/{revision['conversation_id']}", json={"title": "Changed"}
        ).status_code
        == 403
    )


def test_handoff_package_has_review_and_feedback_snapshot(client):
    revision = completed(generate(client))
    saved = client.post(
        "/api/feedback",
        json={"revision_id": revision["id"], "rating": 4, "comment": "Keep officer approval explicit."},
    )
    assert saved.status_code == 201
    response = client.get(f"/api/revisions/{revision['id']}/report")
    assert response.status_code == 200
    assert "Keep officer approval explicit." in response.text
    assert "## Requirements" in response.text
    assert "(diagrams/" not in response.text
    with zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/revisions/{revision['id']}/export").content)
    ) as archive:
        assert "DESIGN_REVIEW.md" in archive.namelist()
        assert "diagrams/component.svg" in archive.read("DESIGN_REVIEW.md").decode()
        assert json.loads(archive.read("reviews.json"))[0]["id"] == saved.json()["id"]
        assert "trace" not in json.loads(archive.read("revision.json"))


def test_live_allowance_replays_do_not_charge_and_samples_are_free(tmp_path, fake_renderer):
    settings = Settings(
        _env_file=None,
        mode="live",
        api_key="test-key",
        data_dir=tmp_path,
        frontend_dir=Path("/not-built"),
        live_daily_limit=1,
        live_global_daily_limit=2,
    )
    app = create_app(settings, provider=SampleProvider(), renderer=fake_renderer)
    with TestClient(app) as client:
        client.get("/api/session")
        client.headers["X-Forma-Request"] = "1"
        request_id = str(uuid4())
        first = completed(generate(client, request_id=request_id))
        assert client.get("/api/allowance").json()["remaining"] == 0
        assert completed(generate(client, request_id=request_id))["id"] == first["id"]
        assert generate(client).status_code == 429
        assert completed(generate(client, mode="sample"))["mode"] == "sample"
        with app.state.store.db() as db:
            assert db.execute("SELECT SUM(count) AS total FROM provider_usage").fetchone()["total"] == 1
            assert db.execute("SELECT COUNT(*) AS total FROM generation_leases").fetchone()["total"] == 0


def test_global_allowance_is_shared_across_owners(app):
    store = app.state.store
    store.reserve_live_generation("one", 5, 1)
    assert store.quota("two", 5, 1)["remaining"] == 0
    with pytest.raises(QuotaExceeded):
        store.reserve_live_generation("two", 5, 1)


def test_sample_server_does_not_accept_live_requests(client):
    assert generate(client, mode="live").status_code == 503
    assert client.get("/api/conversations").json() == []
