"""Measure the deterministic sample's cold/warm render pipeline; not live-model latency."""

import asyncio
import json
from pathlib import Path

from app.models import DiagramType
from app.pipeline import Pipeline
from app.provider import SampleProvider
from app.renderer import Renderer
from app.sample import SEBI_PROMPT


async def main():
    pipeline = Pipeline(SampleProvider(), Renderer(Path(".tools/plantuml.jar")))
    observations = []
    for label in ["cold", "warm"]:
        result = await pipeline.graph.ainvoke(
            {"prompt": SEBI_PROMPT, "previous": None, "feedback": [], "diagram_types": list(DiagramType)}
        )
        observations.append(
            {"run": label, **result["timings"], "cache_hits": sum(d["cache_hit"] for d in result["diagrams"])}
        )
    print(json.dumps(observations, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
