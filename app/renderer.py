import asyncio
import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring


class RenderError(ValueError):
    pass


ALLOWED_TAGS = {
    "svg",
    "g",
    "path",
    "rect",
    "line",
    "polyline",
    "polygon",
    "circle",
    "ellipse",
    "text",
    "tspan",
    "defs",
    "clipPath",
    "linearGradient",
    "radialGradient",
    "stop",
    "title",
    "desc",
    "style",
}


def sanitize_svg(raw: str) -> str:
    try:
        root = fromstring(raw)
    except Exception as e:
        raise RenderError("Renderer returned invalid SVG") from e
    if root.tag.split("}")[-1] != "svg":
        raise RenderError("Renderer returned a non-SVG document")
    for parent in root.iter():
        for child in list(parent):
            if child.tag.split("}")[-1] not in ALLOWED_TAGS:
                parent.remove(child)
        for key, val in list(parent.attrib.items()):
            local = key.split("}")[-1].lower()
            if (
                local.startswith("on")
                or local in {"href", "src"}
                or re.search(r"url\((?!#)|javascript:", val, re.I)
            ):
                del parent.attrib[key]
        if parent.tag.split("}")[-1] == "style" and parent.text:
            if re.search(r"url\(|@import|expression\(", parent.text, re.I):
                parent.text = ""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="unicode")


def check_source(source: str):
    if len(source.encode()) > 60000:
        raise RenderError("Diagram source exceeds the size limit")
    lines = source.strip().splitlines()
    if not lines or lines[0].strip() != "@startuml" or lines[-1].strip() != "@enduml":
        raise RenderError("Source must contain one @startuml / @enduml diagram")
    if len(re.findall(r"@startuml|@enduml", source, re.I)) != 2:
        raise RenderError("Only one diagram may be rendered at a time")
    if re.search(r"!|%|\[\[|<img|<svg|<script|<iframe|@start(?!uml)|@end(?!uml)", source, re.I):
        raise RenderError("Includes, macros, external links, and embedded content are disabled")


class Renderer:
    def __init__(self, jar: Path, java="java", timeout=20.0, concurrency=3, warm_samples=False):
        self.jar, self.java, self.timeout = jar.resolve(), java, timeout
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache: OrderedDict[str, str] = OrderedDict()
        self.inflight: dict[str, asyncio.Task] = {}
        self.waiters: dict[str, int] = {}
        seed = self.jar.parent / "case-study.json"
        if warm_samples and self.jar.is_file() and seed.is_file():
            try:
                data = json.loads(seed.read_text())
                if data["jar_sha256"] == hashlib.sha256(self.jar.read_bytes()).hexdigest():
                    for item in data["diagrams"][:128]:
                        check_source(item["source"])
                        self.cache[hashlib.sha256(item["source"].encode()).hexdigest()] = sanitize_svg(
                            item["svg"]
                        )
            except (ValueError, KeyError, TypeError, OSError):
                self.cache.clear()

    async def render(self, source: str) -> tuple[str, bool]:
        check_source(source)
        key = hashlib.sha256(source.encode()).hexdigest()
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key], True
        shared = key in self.inflight
        if not shared:
            self.inflight[key] = asyncio.create_task(self._render(source))
        task = self.inflight[key]
        self.waiters[key] = self.waiters.get(key, 0) + 1
        try:
            svg = await asyncio.shield(task)
            self.cache[key] = svg
            self.cache.move_to_end(key)
            if len(self.cache) > 128:
                self.cache.popitem(last=False)
            return svg, shared
        finally:
            self.waiters[key] -= 1
            # A cancelled request must not abort a shared render that another request still needs.
            if self.waiters[key] == 0:
                self.inflight.pop(key, None)
                self.waiters.pop(key, None)
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async def _render(self, source):
        if not self.jar.is_file():
            raise RenderError("PlantUML is unavailable. Run the setup script before starting Forma.")
        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                self.java,
                "-Xmx192m",
                "-Djava.awt.headless=true",
                "-DPLANTUML_SECURITY_PROFILE=SANDBOX",
                "-jar",
                str(self.jar),
                "-tsvg",
                "-pipe",
                "-charset",
                "UTF-8",
                "-nometadata",
                "-failfast2",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(source.encode()), self.timeout)
            except (TimeoutError, asyncio.CancelledError) as e:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                if isinstance(e, asyncio.CancelledError):
                    raise
                raise RenderError("Diagram rendering exceeded the time limit") from e
            if process.returncode != 0 or b"Syntax Error" in stdout or b"syntax error" in stderr.lower():
                raise RenderError("PlantUML rejected the syntax. Check names, arrows, and balanced blocks.")
            if len(stdout) > 2_000_000:
                raise RenderError("Rendered diagram exceeds the size limit")
            return sanitize_svg(stdout.decode())
