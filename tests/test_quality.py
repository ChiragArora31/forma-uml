import asyncio
import copy
import json

import httpx
import pytest
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.models import Architecture
from app.provider import LiveProvider
from app.quality import CallBudget, CallBudgetExceeded, improve_design, structural_issues
from app.sample import APPROVAL_PROMPT, BASE, SEBI_PROMPT, sample_architecture
from tests.test_provider import completion


def review(**updates):
    return {
        "summary": "The brief is covered consistently in this proposed design.",
        "covered_requirements": ["Clause extraction", "Control gaps", "IT and operational impact"],
        "missing_requirements": [],
        "critical_issues": [],
        "suggestions": [],
        **updates,
    }


def provider(handler):
    settings = Settings(
        _env_file=None,
        api_key="test-key",
        model="gemini-test",
        semantic_review=True,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    live = LiveProvider(settings)
    live.llm = ChatOpenAI(
        model=settings.model,
        **live.options,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return live


def test_structural_checks_are_advisory_and_cover_deployment_isolation_and_reachability():
    a = Architecture.model_validate(BASE)
    assert structural_issues(a) == []
    broken = a.model_copy(deep=True)
    for node in broken.nodes:
        node.components = [c for c in node.components if c != "portal"]
    broken.connections = [c for c in broken.connections if "portal" not in (c.source, c.target)]
    broken.interactions = [c for c in broken.interactions if "portal" not in (c.source, c.target)]
    broken.states.append("Unreachable")
    issues = structural_issues(broken)
    assert any("Deployment" in i and "portal" in i for i in issues)
    assert any("connection" in i and "portal" in i for i in issues)
    assert any("Unreachable" in i for i in issues)
    assert a.model_dump() == BASE  # stored/legacy designs are not modified


async def test_live_quality_review_uses_actual_sdk_and_preserves_audit_and_original_request():
    seen = []

    async def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        tool = body["tools"][0]["function"]["name"]
        return httpx.Response(200, json=completion(BASE if tool == "Architecture" else review(), tool))

    result = await provider(handler).generate(SEBI_PROMPT, None, [])
    assert len(seen) == 2
    assert all(b["reasoning_effort"] == "medium" for b in seen)
    assert result["trace"]["quality"]["status"] == "reviewed"
    assert result["trace"]["model_calls"] == 2
    assert result["trace"]["trainable"] is False
    assert json.loads(seen[1]["messages"][1]["content"])["request"] == SEBI_PROMPT


async def test_reviewed_repair_incorporates_missing_requirement_then_is_reviewed_again():
    seen = []
    improved = sample_architecture(APPROVAL_PROMPT, sample_architecture(SEBI_PROMPT)).model_dump()

    async def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        tool = body["tools"][0]["function"]["name"]
        response = [
            BASE,
            review(missing_requirements=["Officer approval before publication"]),
            improved,
            review(),
        ][len(seen) - 1]
        return httpx.Response(200, json=completion(response, tool))

    result = await provider(handler).generate(APPROVAL_PROMPT, sample_architecture(SEBI_PROMPT), [])
    assert len(seen) == 4
    assert result["trace"]["quality"]["status"] == "revised"
    assert len(result["trace"]["attempts"]) == 2
    assert "Officer approval before publication" in seen[2]["messages"][2]["content"]
    assert json.loads(seen[2]["messages"][1]["content"])["request"] == APPROVAL_PROMPT
    assert result["architecture"].model_dump() == improved


async def test_optional_reviewer_outage_keeps_valid_generation_available_without_leaking_errors():
    async def handler(request):
        body = json.loads(request.content)
        if body["tools"][0]["function"]["name"] == "DesignReview":
            return httpx.Response(503, json={"error": {"message": "sensitive-provider-detail"}})
        return httpx.Response(200, json=completion(BASE))

    result = await provider(handler).generate(SEBI_PROMPT, None, [])
    assert result["architecture"].title == BASE["title"]
    assert result["trace"]["quality"]["status"] == "unavailable"
    assert "sensitive-provider-detail" not in json.dumps(result["trace"])


async def test_budget_includes_failed_semantic_repairs_and_never_exceeds_six_model_calls():
    seen = []
    invalid = copy.deepcopy(BASE)
    invalid["connections"][0]["source"] = "missing"

    async def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        tool = body["tools"][0]["function"]["name"]
        if len(seen) < 3:
            response = invalid
        elif len(seen) == 3:
            response = BASE
        elif tool == "DesignReview":
            response = review(missing_requirements=["Officer approval"])
        else:
            response = invalid
        return httpx.Response(200, json=completion(response, tool))

    result = await provider(handler).generate(SEBI_PROMPT, None, [])
    assert len(seen) == result["trace"]["model_calls"] == 6
    assert result["architecture"].title == BASE["title"]
    assert result["trace"]["quality"]["status"] == "needs_review"


def test_call_budget_rejects_before_an_additional_request():
    budget = CallBudget(limit=1)
    budget.consume()
    with pytest.raises(CallBudgetExceeded):
        budget.consume()
    assert budget.used == 1


async def test_optional_review_timeout_falls_back_but_user_cancellation_propagates():
    waiting = asyncio.Event()

    class Chat:
        def bind_tools(self, *args, **kwargs):
            return self

        async def ainvoke(self, messages):
            waiting.set()
            await asyncio.sleep(30)

    base = {"architecture": Architecture.model_validate(BASE), "trace": {"attempts": []}}

    async def regenerate(correction):
        raise AssertionError("No repair before a review exists")

    from app.provider import gemini_schema

    result = await improve_design(
        Chat(), True, SEBI_PROMPT, None, [], base, CallBudget(), gemini_schema, regenerate, 0.01
    )
    assert result["trace"]["quality"]["status"] == "unavailable"
    waiting.clear()
    task = asyncio.create_task(
        improve_design(Chat(), True, SEBI_PROMPT, None, [], base, CallBudget(), gemini_schema, regenerate, 10)
    )
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_public_revision_exposes_review_findings_without_private_audit():
    from app.report import design_report
    from app.store import Store

    private = {
        "status": "reviewed",
        "summary": "Explicit requirements were covered.",
        "missing_requirements": [],
        "critical_issues": [],
        "structural_issues": [],
        "suggestions": ["Consider a secondary recovery region."],
        "review_attempts": [{"messages": "private audit"}],
        "review_error": {"detail": "private"},
    }
    row = {
        "id": "test",
        "number": 1,
        "created_at": "2026-10-07",
        "prompt": "design a system",
        "mode": "live",
        "architecture": json.dumps(BASE),
        "diagrams": "[]",
        "timings": "{}",
        "trace": json.dumps({"model": "test-model", "quality": private}),
    }
    public = Store.decode_revision(row)
    assert "review_attempts" not in public["quality"]
    assert "review_error" not in public["quality"]
    report = design_report(public, [])
    assert "Automatic requirement review" in report
    assert "secondary recovery region" in report
    assert "private" not in report
