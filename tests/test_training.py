import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import GenerateRequest
from app.pipeline import Pipeline
from app.provider import SampleProvider
from app.sample import SEBI_PROMPT
from app.store import Store
from app.training import ARTProvider, claim_rows, export_scenarios, finish_rows, pending_rows


async def add_review(store, renderer, mode="live"):
    from app.models import FeedbackRequest

    request = GenerateRequest(prompt=SEBI_PROMPT)
    state = await Pipeline(SampleProvider(), renderer).graph.ainvoke(
        {"prompt": SEBI_PROMPT, "previous": None, "feedback": [], "diagram_types": request.diagram_types}
    )
    state["timings"]["total_ms"] = 1
    revision = store.save_revision("owner", request, state, mode)
    store.save_feedback(
        "owner", FeedbackRequest(revision_id=revision["id"], rating=4, comment="Keep provenance")
    )
    return revision


async def test_outbox_export_preserves_context_excludes_samples_and_is_retryable(tmp_path, fake_renderer):
    store = Store(tmp_path / "db.sqlite")
    live = await add_review(store, fake_renderer)
    await add_review(store, fake_renderer, "sample")
    assert len(pending_rows(store)) == 1
    assert len(pending_rows(store, include_samples=True)) == 2
    output = tmp_path / "feedback.jsonl"
    assert export_scenarios(store, output) == 1
    data = json.loads(output.read_text())
    assert data["revision_id"] == live["id"]
    assert data["comment"] == "Keep provenance"
    assert output.stat().st_mode & 0o777 == 0o600
    assert pending_rows(store)[0][1]["rating"] == 4
    assert export_scenarios(store, output) == 1  # export is repeatable, not consumed training


async def test_atomic_claim_prevents_duplicate_training_and_keeps_unknown_outcome(tmp_path, fake_renderer):
    store = Store(tmp_path / "db.sqlite")
    await add_review(store, fake_renderer)
    rows = pending_rows(store)
    claimed = claim_rows(store, rows, str(uuid4()))
    assert len(claimed) == 1
    assert claim_rows(store, rows, str(uuid4())) == []
    finish_rows(store, claimed, "needs_reconciliation", "Unknown remote outcome")
    assert pending_rows(store) == []


async def test_art_langgraph_adapter_uses_real_integration_api_with_logprobs(monkeypatch):
    pytest.importorskip("art")
    from art import langgraph

    seen = {}
    architecture = __import__("app.sample", fromlist=["sample_architecture"]).sample_architecture(SEBI_PROMPT)

    class FakeChat:
        def with_structured_output(self, schema):
            seen["schema"] = schema
            return self

        async def ainvoke(self, messages):
            seen["messages"] = messages
            return architecture

    def fake_init(model, **kwargs):
        seen["model"], seen["kwargs"] = model, kwargs
        return FakeChat()

    monkeypatch.setattr(langgraph, "init_chat_model", fake_init)
    model = SimpleNamespace(get_inference_name=lambda: "policy@step1")
    result = await ARTProvider(model).generate(SEBI_PROMPT, None, [{"comment": "Keep provenance"}])
    assert result["architecture"] is architecture
    assert seen["model"] == "policy@step1"
    assert seen["kwargs"]["logprobs"] is True
    assert "Keep provenance" in seen["messages"][1].content


def test_training_optional_dependency_is_importable_and_api_contract_matches():
    pytest.importorskip("art")
    import inspect

    import art
    from art.langgraph import init_chat_model, wrap_rollout
    from art.serverless import ServerlessBackend

    assert callable(init_chat_model) and callable(wrap_rollout)
    assert "learning_rate" in inspect.signature(ServerlessBackend.train).parameters
    model = art.TrainableModel(
        name="contract", run_name="contract", project="forma", base_model="test-policy"
    )
    trajectory = art.Trajectory(reward=0.75, messages_and_choices=[], metadata={"feedback_id": "test"})
    assert art.TrajectoryGroup([trajectory]).trajectories[0].reward == 0.75
    assert model.base_model == "test-policy"


async def test_real_art_wrapper_captures_a_langchain_completion(monkeypatch, tmp_path):
    """Actual ART integration + actual LangChain; only the provider transport is a fixture."""
    art = pytest.importorskip("art")
    import httpx
    from art.langgraph import llm_wrapper, wrap_rollout
    from langchain_openai import ChatOpenAI
    from openai.types.chat.chat_completion import Choice

    from app.sample import BASE
    from tests.test_provider import completion

    monkeypatch.chdir(tmp_path)

    async def transport(request):
        data = json.loads(request.content)
        assert data["logprobs"] is True
        result = completion(BASE)
        result["choices"][0]["logprobs"] = {
            "content": [{"token": "{", "logprob": -0.1, "bytes": [123], "top_logprobs": []}]
        }
        return httpx.Response(200, json=result)

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(
        llm_wrapper, "ChatOpenAI", lambda **kwargs: ChatOpenAI(**kwargs, http_async_client=client)
    )
    model = art.Model(
        name="fixture-policy",
        project="forma-tests",
        trainable=False,
        inference_model_name="fixture-policy",
        inference_api_key="test-key",
        inference_base_url="https://test.invalid/v1",
    )

    async def rollout():
        result = await ARTProvider(model).generate(SEBI_PROMPT, None, [{"comment": "Retain provenance"}])
        assert result["architecture"].title == BASE["title"]
        return art.Trajectory(reward=0.8, messages_and_choices=[])

    trajectory = await wrap_rollout(model, rollout)()
    assert len(trajectory.messages_and_choices) == 3
    choice = trajectory.messages_and_choices[-1]
    assert isinstance(choice, Choice)
    assert choice.logprobs.content[0].logprob == -0.1
    assert trajectory.tools[0]["function"]["name"] == "Architecture"
    await client.aclose()


async def test_sample_reviews_do_not_starve_live_training_batches(tmp_path, fake_renderer):
    store = Store(tmp_path / "db.sqlite")
    for _ in range(3):
        await add_review(store, fake_renderer, "sample")
    live = await add_review(store, fake_renderer)
    selected = pending_rows(store, limit=1)
    assert len(selected) == 1
    assert selected[0][1]["revision_id"] == live["id"]
