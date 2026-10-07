import asyncio
from pathlib import Path

import pytest

from app.compiler import compile_diagram, text
from app.models import DiagramType
from app.renderer import Renderer, RenderError, check_source, sanitize_svg
from app.sample import APPROVAL_PROMPT, ASYNC_PROMPT, SEBI_PROMPT, sample_architecture

JAR = Path(".tools/plantuml.jar")


@pytest.mark.parametrize(
    "payload",
    [
        "@startuml\n!include /etc/passwd\n@enduml",
        "@startuml\n!includeurl https://example.com/a\n@enduml",
        "@startuml\nAlice -> Bob : [[https://example.com]]\n@enduml",
        "@startuml\n@enduml\n@startuml\n@enduml",
        '@startuml\n%load_json("a")\n@enduml',
        "@startuml\nAlice -> Bob: <img:https://example.com/x>\n@enduml",
    ],
)
def test_disallows_executable_or_remote_source(payload):
    with pytest.raises(RenderError):
        check_source(payload)


def test_svg_sanitization_removes_active_content():
    svg = sanitize_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>bad()</script>'
        '<foreignObject><div>bad</div></foreignObject><image href="https://example.com"/>'
        '<text onclick="bad()">Safe</text><style>@import "https://example.com";</style></svg>'
    )
    assert "script" not in svg and "foreignObject" not in svg and "onclick" not in svg
    assert "https://" not in svg
    assert "Safe" in svg


def test_diagram_text_cannot_inject_source():
    assert "\n" not in text("Name\n!include /etc/passwd\n@enduml")
    assert "!" not in text("Name\n!include /etc/passwd")
    assert '"' not in text('" as escape {')


@pytest.mark.renderer
@pytest.mark.parametrize("kind", list(DiagramType))
async def test_real_renderer_all_14_types_across_revisions(kind):
    if not JAR.exists():
        pytest.skip("Run scripts/setup.sh to install the pinned renderer")
    renderer = Renderer(JAR)
    a = sample_architecture(SEBI_PROMPT)
    for update in [None, ASYNC_PROMPT, APPROVAL_PROMPT]:
        if update:
            a = sample_architecture(update, a)
        source = compile_diagram(a, kind)
        svg, cached = await renderer.render(source)
        assert "<svg" in svg and "Syntax Error" not in svg
        assert not cached or update is not None
        again, cached = await renderer.render(source)
        assert cached and again == svg


@pytest.mark.renderer
async def test_real_engine_rejects_bad_syntax():
    if not JAR.exists():
        pytest.skip("Install renderer first")
    with pytest.raises(RenderError):
        await Renderer(JAR).render("@startuml\nclass {\nthis is broken\n@enduml")


async def test_concurrent_identical_renders_are_deduplicated(monkeypatch):
    r = Renderer(JAR)
    gate = asyncio.Event()
    calls = 0

    async def fake(source):
        nonlocal calls
        calls += 1
        await gate.wait()
        return "<svg/>"

    monkeypatch.setattr(r, "_render", fake)
    tasks = [asyncio.create_task(r.render("@startuml\nA -> B: Hi\n@enduml")) for _ in range(2)]
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(*tasks)
    assert calls == 1


async def test_missing_renderer_is_explicit_failure():
    with pytest.raises(RenderError, match="unavailable"):
        await Renderer(Path("/missing/plantuml.jar")).render("@startuml\nA -> B: Hi\n@enduml")


async def test_cancelling_one_request_preserves_a_shared_render(monkeypatch):
    renderer = Renderer(JAR)
    gate = asyncio.Event()

    async def fake(source):
        await gate.wait()
        return "<svg/>"

    monkeypatch.setattr(renderer, "_render", fake)
    source = "@startuml\nA -> B: Hi\n@enduml"
    first = asyncio.create_task(renderer.render(source))
    second = asyncio.create_task(renderer.render(source))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    gate.set()
    assert await second == ("<svg/>", True)
    assert not renderer.inflight and not renderer.waiters


async def test_cancelling_the_only_request_cleans_up_render_task(monkeypatch):
    renderer = Renderer(JAR)
    gate = asyncio.Event()

    async def fake(source):
        await gate.wait()

    monkeypatch.setattr(renderer, "_render", fake)
    request = asyncio.create_task(renderer.render("@startuml\nA -> B: Hi\n@enduml"))
    await asyncio.sleep(0)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not renderer.inflight and not renderer.waiters
