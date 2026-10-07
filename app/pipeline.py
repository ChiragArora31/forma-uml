import asyncio
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.compiler import compile_diagram
from app.models import Architecture, DiagramType
from app.provider import Provider
from app.renderer import Renderer


class DesignState(TypedDict, total=False):
    prompt: str
    previous: Architecture | None
    feedback: list[dict]
    diagram_types: list[DiagramType]
    architecture: Architecture
    trace: dict
    diagrams: list[dict]
    timings: dict


class Pipeline:
    def __init__(self, provider: Provider, renderer: Renderer):
        self.provider = provider
        self.renderer = renderer
        graph = StateGraph(DesignState)
        graph.add_node("design", self.design)
        graph.add_node("compile_and_validate", self.compile_and_validate)
        graph.add_edge(START, "design")
        graph.add_edge("design", "compile_and_validate")
        graph.add_edge("compile_and_validate", END)
        self.graph = graph.compile()

    async def design(self, state):
        started = time.perf_counter()
        result = await self.provider.generate(
            state["prompt"], state.get("previous"), state.get("feedback", [])
        )
        return {**result, "timings": {"design_ms": round((time.perf_counter() - started) * 1000)}}

    async def compile_and_validate(self, state):
        started = time.perf_counter()
        architecture = state["architecture"]

        async def render(kind):
            source = compile_diagram(architecture, kind)
            svg, cached = await self.renderer.render(source)
            return {"type": kind.value, "source": source, "svg": svg, "validated": True, "cache_hit": cached}

        tasks = [asyncio.create_task(render(kind)) for kind in state["diagram_types"]]
        try:
            diagrams = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return {
            "diagrams": diagrams,
            "timings": {**state["timings"], "render_ms": round((time.perf_counter() - started) * 1000)},
        }
