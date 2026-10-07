"""Build a private cache of real, validated sample renders for fast cold starts."""

import asyncio
import hashlib
import json
from pathlib import Path

from app.compiler import compile_diagram
from app.models import DiagramType
from app.renderer import Renderer
from app.sample import APPROVAL_PROMPT, ASYNC_PROMPT, SEBI_PROMPT, sample_architecture


async def main():
    jar = Path(".tools/plantuml.jar")
    renderer = Renderer(jar)
    design, artifacts = None, []
    for prompt in [SEBI_PROMPT, ASYNC_PROMPT, APPROVAL_PROMPT]:
        design = sample_architecture(prompt, design)

        async def render(kind, current=design):
            source = compile_diagram(current, kind)
            svg, _ = await renderer.render(source)
            return {"source": source, "svg": svg}

        artifacts += await asyncio.gather(*(render(kind) for kind in DiagramType))
    target = jar.parent / "case-study.json"
    target.write_text(
        json.dumps({"jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "diagrams": artifacts})
    )
    print(f"Validated {len(artifacts)} sample views for the cold-start cache")


if __name__ == "__main__":
    asyncio.run(main())
