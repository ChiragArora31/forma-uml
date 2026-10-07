import io
import json
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.sample import APPROVAL_PROMPT, ASYNC_PROMPT, SEBI_PROMPT


def generate(client, **extra):
    payload = {"prompt": SEBI_PROMPT, "diagram_types": ["sequential", "component"], **extra}
    response = client.post("/api/generate", json=payload)
    return response


def completed(response):
    assert response.status_code == 200, response.text
    for block in response.text.split("\n\n"):
        if block.startswith("event: complete"):
            return json.loads(block.split("data: ", 1)[1])
    pytest.fail(response.text)


def test_exact_minimum_input_accepts_alias_and_persists(client):
    revision = completed(generate(client))
    assert [d["type"] for d in revision["diagrams"]] == ["sequence", "component"]
    assert revision["number"] == 1
    assert all(d["validated"] for d in revision["diagrams"])
    assert client.get("/api/conversations").json()[0]["id"] == revision["conversation_id"]
    saved = client.get(f"/api/conversations/{revision['conversation_id']}").json()
    assert saved["revisions"][0]["architecture"] == revision["architecture"]
    assert "trace" not in revision
    assert "owner" not in saved
    assert "event: phase" in generate(client).text


def test_updates_preserve_original_requirements_and_add_boundaries(client):
    first = completed(generate(client))
    second = completed(
        generate(client, prompt=ASYNC_PROMPT, conversation_id=first["conversation_id"], base_revision=1)
    )
    assert second["number"] == 2
    assert {"queue", "dlq"} <= {c["id"] for c in second["architecture"]["components"]}
    assert set(first["architecture"]["requirements"]) <= set(second["architecture"]["requirements"])
    third = completed(
        generate(client, prompt=APPROVAL_PROMPT, conversation_id=first["conversation_id"], base_revision=2)
    )
    assert third["number"] == 3
    assert {"queue", "approval"} <= {c["id"] for c in third["architecture"]["components"]}
    saved = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assert saved["revisions"][0]["diagrams"] == first["diagrams"]
    assert saved["latest"] == 3


def test_idempotent_retries_do_not_duplicate_revisions(client):
    rid = str(uuid4())
    first = completed(generate(client, request_id=rid))
    replay = completed(generate(client, request_id=rid))
    assert replay["id"] == first["id"]
    assert len(client.get("/api/conversations").json()) == 1
    changed = generate(client, request_id=rid, diagram_types=["class"])
    assert changed.status_code == 409


def test_stale_update_fails_without_overwriting(client):
    first = completed(generate(client))
    completed(
        generate(client, prompt=ASYNC_PROMPT, conversation_id=first["conversation_id"], base_revision=1)
    )
    response = generate(
        client, prompt=APPROVAL_PROMPT, conversation_id=first["conversation_id"], base_revision=1
    )
    assert response.status_code == 409
    assert client.get(f"/api/conversations/{first['conversation_id']}").json()["latest"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "  "},
        {"prompt": "small"},
        {"prompt": "a" * 12001},
        {"prompt": SEBI_PROMPT, "diagram_types": []},
        {"prompt": SEBI_PROMPT, "diagram_types": ["nonsense"]},
        {"prompt": SEBI_PROMPT, "conversation_id": str(uuid4())},
        {"prompt": SEBI_PROMPT, "base_revision": 1},
    ],
)
def test_input_validation(client, body):
    assert client.post("/api/generate", json=body).status_code == 422


def test_feedback_is_linked_to_revision_and_outbox_atomically(client, app):
    first = completed(generate(client))
    payload = {
        "revision_id": first["id"],
        "rating": 4,
        "comment": "Need a review step",
        "diagram_type": "component",
        "request_id": str(uuid4()),
    }
    response = client.post("/api/feedback", json=payload)
    assert response.status_code == 201
    assert response.json()["training_status"] == "queued"
    assert client.post("/api/feedback", json=payload).json()["id"] == response.json()["id"]
    with app.state.store.db() as db:
        rows = db.execute("SELECT * FROM training_outbox").fetchall()
        assert len(rows) == 1
        data = json.loads(rows[0]["payload"])
        assert data["revision_id"] == first["id"]
        assert data["reward"] == 0.75
        assert data["architecture"] == first["architecture"]
        assert data["trace"]["trainable"] is False
        assert data["previous_design"] is None
    reviews = client.get(f"/api/revisions/{first['id']}/feedback").json()
    assert len(reviews) == 1
    assert reviews[0]["comment"] == payload["comment"]
    assert client.post("/api/feedback", json={**payload, "rating": 3}).status_code == 409


def test_feedback_keeps_previous_design_for_revision_scenario(client, app):
    first = completed(generate(client))
    second = completed(
        generate(client, prompt=ASYNC_PROMPT, conversation_id=first["conversation_id"], base_revision=1)
    )
    client.post("/api/feedback", json={"revision_id": second["id"], "rating": 3})
    with app.state.store.db() as db:
        payload = json.loads(db.execute("SELECT payload FROM training_outbox").fetchone()[0])
        assert payload["previous_design"] == first["architecture"]


@pytest.mark.parametrize("rating", [0, 6, 1.5])
def test_feedback_rating_validation(client, rating):
    first = completed(generate(client))
    assert (
        client.post("/api/feedback", json={"revision_id": first["id"], "rating": rating}).status_code == 422
    )


def test_feedback_diagram_must_belong_to_revision(client):
    first = completed(generate(client))
    response = client.post(
        "/api/feedback", json={"revision_id": first["id"], "rating": 5, "diagram_type": "timing"}
    )
    assert response.status_code == 409


def test_browser_session_ownership_on_reads_writes_and_exports(client, app):
    revision = completed(generate(client))
    with TestClient(app) as stranger:
        stranger.get("/api/session")
        stranger.headers["X-Forma-Request"] = "1"
        assert stranger.get("/api/conversations").json() == []
        assert stranger.get(f"/api/conversations/{revision['conversation_id']}").status_code == 404
        assert stranger.get(f"/api/revisions/{revision['id']}/export").status_code == 404
        assert stranger.get(f"/api/revisions/{revision['id']}/feedback").status_code == 404
        assert (
            stranger.post("/api/feedback", json={"revision_id": revision["id"], "rating": 5}).status_code
            == 404
        )
        assert (
            generate(stranger, conversation_id=revision["conversation_id"], base_revision=1).status_code
            == 404
        )


def test_csrf_header_and_session_are_required(app):
    with TestClient(app) as client:
        assert client.get("/api/conversations").status_code == 401
        client.get("/api/session")
        assert generate(client).status_code == 403
        assert client.cookies["forma_session"]
        assert (
            "HttpOnly" in client.get("/api/session").headers.get("set-cookie", "")
            or client.cookies["forma_session"]
        )


def test_exports_contain_validated_diagrams_and_context_without_trace(client):
    revision = completed(generate(client))
    response = client.get(f"/api/revisions/{revision['id']}/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip:
        assert {
            "diagrams/component.puml",
            "diagrams/sequence.svg",
            "architecture.json",
            "revision.json",
            "README.md",
        } <= set(zip.namelist())
        assert json.loads(zip.read("architecture.json")) == revision["architecture"]
        assert zip.read("diagrams/component.puml").decode() == revision["diagrams"][1]["source"]
        assert b"api_key" not in zip.read("revision.json")


def test_sample_mode_refuses_arbitrary_prompt_without_saving(client):
    response = generate(client, prompt="Build an online book store with payment and checkout")
    assert "event: error" in response.text
    assert "Switch to live" in response.text
    assert client.get("/api/conversations").json() == []


def test_failed_render_does_not_commit_partial_revision(client, app):
    first = completed(generate(client))
    from app.renderer import RenderError

    async def fail(source):
        raise RenderError("Syntax rejected")

    app.state.pipeline.renderer.render = fail
    response = generate(
        client, prompt=ASYNC_PROMPT, conversation_id=first["conversation_id"], base_revision=1
    )
    assert "event: error" in response.text
    saved = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assert saved["latest"] == 1
    assert len(saved["revisions"]) == 1


def test_session_and_validation_headers(client):
    response = client.get("/api/session")
    assert response.headers["cache-control"] == "no-store"
    assert "object-src 'none'" in response.headers["content-security-policy"]
    catalog = response.json()["diagram_types"]
    assert len(catalog) == 14
