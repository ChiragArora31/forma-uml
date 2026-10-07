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
    instance = LiveProvider(Settings(api_key="test-key", model="test-model"))
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
        LiveProvider(Settings(api_key=""))
