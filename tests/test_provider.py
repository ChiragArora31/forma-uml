import copy
import json

import httpx
import pytest
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.provider import LiveProvider, ProviderError
from app.sample import ASYNC_PROMPT, BASE, SEBI_PROMPT, sample_architecture


def completion(design, name="Architecture"):
    return {
        "id": "test-completion",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_design",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(design)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
    }


def provider(transport):
    instance = LiveProvider(Settings(_env_file=None, api_key="test-key", model="test-model"))
    instance.llm = ChatOpenAI(
        model="test-model",
        api_key="test-key",
        base_url="https://test.invalid/v1",
        http_async_client=httpx.AsyncClient(transport=transport),
        max_retries=0,
    )
    return instance


async def test_live_langchain_structured_generation_receives_previous_design_and_feedback():
    seen = []

    async def handle(request):
        data = json.loads(request.content)
        seen.append(data)
        return httpx.Response(
            200,
            json=completion(sample_architecture(ASYNC_PROMPT, sample_architecture(SEBI_PROMPT)).model_dump()),
        )

    live = provider(httpx.MockTransport(handle))
    result = await live.generate(
        ASYNC_PROMPT, sample_architecture(SEBI_PROMPT), [{"rating": 4, "comment": "Decouple ingestion"}]
    )
    assert "queue" in {c.id for c in result["architecture"].components}
    user = json.loads(seen[0]["messages"][1]["content"])
    assert user["previous_design"]["title"] == BASE["title"]
    assert user["review_feedback"][0]["comment"] == "Decouple ingestion"
    assert seen[0]["tools"][0]["function"]["name"] == "Architecture"
    assert result["trace"]["attempts"][0]["usage"]["total_tokens"] == 300
    assert "test-key" not in json.dumps(result["trace"])


async def test_schema_repair_preserves_valid_tool_call_protocol():
    seen = []
    bad = copy.deepcopy(BASE)
    bad["connections"][0]["source"] = "unknown"

    async def handle(request):
        data = json.loads(request.content)
        seen.append(data)
        return httpx.Response(200, json=completion(bad if len(seen) == 1 else BASE))

    result = await provider(httpx.MockTransport(handle)).generate(SEBI_PROMPT, None, [])
    assert result["architecture"].title == BASE["title"]
    assert len(seen) == 2
    assert [m["role"] for m in seen[1]["messages"]] == ["system", "user", "assistant", "tool", "user"]
    assert seen[1]["messages"][3]["tool_call_id"] == "call_design"


async def test_provider_failure_never_silently_falls_back_to_sample():
    async def handle(request):
        return httpx.Response(
            401, json={"error": {"message": "sensitive-provider-detail", "type": "authentication_error"}}
        )

    with pytest.raises(ProviderError) as failure:
        await provider(httpx.MockTransport(handle)).generate(SEBI_PROMPT, None, [])
    assert "sensitive-provider-detail" not in str(failure.value)


def test_live_mode_requires_explicit_credentials():
    with pytest.raises(ProviderError, match="FORMA_API_KEY"):
        LiveProvider(Settings(_env_file=None, api_key=""))


def test_gateway_oidc_is_never_forwarded_to_a_different_provider():
    with pytest.raises(ProviderError, match="FORMA_API_KEY"):
        LiveProvider(
            Settings(
                _env_file=None,
                oidc_token="test-oidc",
                base_url="https://unrelated.invalid/v1",
            )
        )


async def test_gemini_schema_and_repair_preserve_strict_local_validation():
    from app.models import Architecture

    seen = []
    invalid = copy.deepcopy(BASE)
    invalid["connections"][0]["source"] = "not_declared"

    async def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion(invalid if len(seen) == 1 else BASE))

    settings = Settings(
        _env_file=None,
        api_key="test-key",
        model="gemini-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    live = LiveProvider(settings)
    live.llm = ChatOpenAI(
        model=settings.model,
        **live.options,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    result = await live.generate(SEBI_PROMPT, None, [])
    assert isinstance(result["architecture"], Architecture)
    assert len(seen) == 2
    assert seen[0]["tool_choice"] == "required"
    properties = seen[0]["tools"][0]["function"]["parameters"]["properties"]
    assert properties["steps"]["items"]["properties"]["guard"]["type"] == "string"
    assert [m["role"] for m in seen[1]["messages"]] == ["system", "user", "user"]
    assert "not_declared" in seen[1]["messages"][-1]["content"]
    repair = seen[1]["tools"][0]["function"]["parameters"]["properties"]
    assert repair["connections"]["items"]["properties"]["source"]["enum"] == [
        c["id"] for c in BASE["components"]
    ]
    assert repair["relations"]["items"]["properties"]["target"]["enum"] == [e["id"] for e in BASE["entities"]]
    assert repair["nodes"]["items"]["properties"]["components"]["items"]["enum"] == [
        c["id"] for c in BASE["components"]
    ]


async def test_gemini_exhausts_bounded_repairs_without_accepting_unknown_actors():
    seen = []
    invalid = copy.deepcopy(BASE)
    invalid["steps"][0]["owner"] = "undeclared_actor"

    async def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion(invalid))

    settings = Settings(
        _env_file=None,
        api_key="test-key",
        model="gemini-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    live = LiveProvider(settings)
    live.llm = ChatOpenAI(
        model=settings.model,
        **live.options,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(ProviderError, match="consistent design"):
        await live.generate(SEBI_PROMPT, None, [])
    assert len(seen) == 3
    assert "undeclared_actor" in seen[1]["messages"][-1]["content"]
    assert (
        "undeclared_actor"
        not in seen[1]["tools"][0]["function"]["parameters"]["properties"]["steps"]["items"]["properties"][
            "owner"
        ]["enum"]
    )


def test_identifier_normalization_never_invents_missing_references():
    from app.models import Architecture
    from app.provider import normalize_identifiers

    design = copy.deepcopy(BASE)
    old = design["components"][0]["id"]
    new = old.upper().replace("_", "-")
    design["components"][0]["id"] = new
    for connection in design["connections"]:
        for field in ["source", "target"]:
            if connection[field] == old:
                connection[field] = new
    for interaction in design["interactions"]:
        for field in ["source", "target"]:
            if interaction[field] == old:
                interaction[field] = new
    # Other references use already canonical spellings; exact canonical aliases remain valid.
    normalized = normalize_identifiers(design)
    assert normalized["components"][0]["id"] == old
    assert design["components"][0]["id"] == new
    Architecture.model_validate(normalized)
    design["connections"][0]["source"] = "missing_component"
    with pytest.raises(ValueError, match="missing_component"):
        Architecture.model_validate(normalize_identifiers(design))


async def test_configured_model_fallback_only_on_capacity_errors():
    seen = []

    async def handle(request):
        payload = json.loads(request.content)
        seen.append(payload["model"])
        if payload["model"] == "primary":
            return httpx.Response(
                503, json={"error": {"message": "capacity unavailable", "type": "server_error"}}
            )
        return httpx.Response(200, json=completion(BASE))

    settings = Settings(
        _env_file=None,
        api_key="test-key",
        model="primary",
        fallback_model="fallback",
        base_url="https://test.invalid/v1",
    )
    live = LiveProvider(settings)
    live.options["http_async_client"] = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    live.llm = ChatOpenAI(model=settings.model, **live.options)
    result = await live.generate(SEBI_PROMPT, None, [])
    assert seen == ["primary", "fallback"]
    assert result["trace"]["model"] == "fallback"


async def test_temporary_capacity_failure_retries_and_counts_failed_calls():
    attempts = 0

    async def handle(request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(
                503, json={"error": {"message": "temporary capacity", "type": "server_error"}}
            )
        return httpx.Response(200, json=completion(BASE))

    result = await provider(httpx.MockTransport(handle)).generate(SEBI_PROMPT, None, [])
    assert attempts == result["trace"]["model_calls"] == 3
    assert result["architecture"].title == BASE["title"]
