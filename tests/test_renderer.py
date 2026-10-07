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


def test_readable_labels_do_not_become_activity_or_html_grammar():
    assert text("Parse; score >= 0.8; List<String>") == "Parse, score at least 0.8, List of String"
    assert text("size < 10 and count != 0") == "size below 10 and count differs from 0"


def test_private_aliases_avoid_reserved_words_without_mutating_the_blueprint():
    architecture = sample_architecture(SEBI_PROMPT)
    component = architecture.components[0]
    original = component.id
    component.id = "class"
    for connection in [*architecture.connections, *architecture.interactions]:
        if connection.source == original:
            connection.source = "class"
        if connection.target == original:
            connection.target = "class"
    for step in architecture.steps:
        if step.owner == original:
            step.owner = "class"
    for node in architecture.nodes:
        node.components = ["class" if c == original else c for c in node.components]
    for timeline in architecture.timelines:
        if timeline.component == original:
            timeline.component = "class"
    snapshot = architecture.model_dump()
    for kind in DiagramType:
        source = compile_diagram(architecture, kind)
        assert " as class\n" not in source
        check_source(source)
    assert " as c_class\n" in compile_diagram(architecture, DiagramType.COMPONENT)
    assert architecture.model_dump() == snapshot


def test_sequence_groups_contiguous_messages_in_the_same_loop():
    a = sample_architecture(SEBI_PROMPT)
    a.interactions[0].fragment = a.interactions[1].fragment = "loop"
    a.interactions[0].condition = a.interactions[1].condition = "For each circular"
    source = compile_diagram(a, DiagramType.SEQUENCE)
    assert source.count("loop For each circular") == 1
    start = source.index("loop For each circular")
    end = source.index("\nend", start)
    assert a.interactions[0].message in source[start:end]
    assert a.interactions[1].message in source[start:end]


def test_state_machine_marks_all_terminal_outcomes_without_ending_an_active_state():
    a = sample_architecture(SEBI_PROMPT)
    a.states.append("Rejected")
    a.transitions.append(a.transitions[-1].model_copy(update={"target": "Rejected"}))
    source = compile_diagram(a, DiagramType.STATE_MACHINE)
    assert "state_4 --> [*]" in source and "state_5 --> [*]" in source
    a.transitions.append(a.transitions[-1].model_copy(update={"source": "Rejected", "target": a.states[0]}))
    assert "state_5 --> [*]" not in compile_diagram(a, DiagramType.STATE_MACHINE)


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


def test_blank_preview_has_a_readable_validation_error():
    with pytest.raises(RenderError, match="Source must contain"):
        check_source(" " * 20)


async def test_prevalidated_sample_cache_requires_matching_renderer_and_sanitizes_svg(tmp_path):
    import hashlib
    import json

    jar = tmp_path / "plantuml.jar"
    jar.write_bytes(b"fixture-jar")
    source = "@startuml\nAlice -> Bob: hello\n@enduml"
    cache = {
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "diagrams": [
            {
                "source": source,
                "svg": '<svg xmlns="http://www.w3.org/2000/svg"><script>unsafe()</script><text>hello</text></svg>',
            }
        ],
    }
    target = tmp_path / "case-study.json"
    target.write_text(json.dumps(cache))
    renderer = Renderer(jar, warm_samples=True)
    svg, cached = await renderer.render(source)
    assert cached and "script" not in svg and "hello" in svg
    cache["jar_sha256"] = "different-engine"
    target.write_text(json.dumps(cache))
    assert not Renderer(jar, warm_samples=True).cache
    target.write_text('{"diagrams":null}')
    assert not Renderer(jar, warm_samples=True).cache
