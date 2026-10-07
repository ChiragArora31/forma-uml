import asyncio
import io
import json
import logging
import secrets
import shutil
import time
import zipfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models import (
    CATALOG,
    Architecture,
    ConversationUpdateRequest,
    FeedbackRequest,
    GenerateRequest,
    SourceRequest,
)
from app.pipeline import Pipeline
from app.provider import LiveProvider, ProviderError, SampleProvider
from app.renderer import Renderer, RenderError
from app.report import design_report
from app.sample import APPROVAL_PROMPT, ASYNC_PROMPT, SEBI_PROMPT, SampleUnavailable
from app.store import Conflict, NotFound, QuotaExceeded, Store

logger = logging.getLogger("forma")
COOKIE = "forma_session"


def streamed_json(result):
    async def chunks():
        parts, size = [], 0
        for part in json.JSONEncoder(ensure_ascii=False).iterencode(result):
            parts.append(part)
            size += len(part)
            if size >= 65536:
                yield "".join(parts)
                parts, size = [], 0
        if parts:
            yield "".join(parts)

    return StreamingResponse(chunks(), media_type="application/json")


async def progress_events(graph, state, heartbeat_seconds=10):
    started = time.perf_counter()
    iterator = graph.astream(state, stream_mode="updates").__aiter__()
    task = asyncio.create_task(anext(iterator))
    try:
        while True:
            if time.perf_counter() - started > 240:
                raise TimeoutError("Generation exceeded its overall verification deadline")
            done, _ = await asyncio.wait({task}, timeout=heartbeat_seconds)
            if not done:
                yield None
                continue
            try:
                event = task.result()
            except StopAsyncIteration:
                break
            yield event
            task = asyncio.create_task(anext(iterator))
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await iterator.aclose()


def create_app(settings: Settings | None = None, provider=None, renderer=None):
    settings = settings or Settings()
    if settings.mode not in {"sample", "live"}:
        raise ValueError("FORMA_MODE must be sample or live")
    store = Store(settings.data_dir / "forma.sqlite3", database_url=settings.database_url)
    renderer = renderer or Renderer(
        settings.plantuml_jar,
        settings.java,
        settings.render_timeout,
        settings.render_concurrency,
        warm_samples=True,
    )
    provider = provider or (LiveProvider(settings) if settings.mode == "live" else SampleProvider())
    pipeline = Pipeline(provider, renderer)
    sample_pipeline = Pipeline(SampleProvider(), renderer)
    active: set[str] = set()
    owners_active: set[str] = set()
    render_requests: set[str] = set()
    recent_requests: OrderedDict[str, tuple[float, int]] = OrderedDict()

    @asynccontextmanager
    async def lifespan(app):
        yield
        tasks = list(renderer.inflight.values()) if hasattr(renderer, "inflight") else []
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Forma UML API", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.pipeline = store, pipeline

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(QuotaExceeded)
    async def quota_exceeded(request, exc):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    def owner(request: Request):
        session = request.cookies.get(COOKIE)
        if not session or len(session) != 64 or not all(c in "0123456789abcdef" for c in session):
            raise HTTPException(401, "Start a browser session first")
        return session

    def mutation(request: Request, uid=Depends(owner)):
        if request.headers.get("X-Forma-Request") != "1":
            raise HTTPException(403, "Missing request header")
        # A non-simple custom header prevents cross-origin browser writes; no permissive CORS.
        stamp = time.monotonic()
        recent, count = recent_requests.get(uid, (stamp, 0))
        count = count + 1 if stamp - recent < 60 else 1
        if count > 60:
            raise HTTPException(429, "Too many requests. Please wait a minute.")
        recent_requests[uid] = (recent if stamp - recent < 60 else stamp, count)
        recent_requests.move_to_end(uid)
        if len(recent_requests) > 1000:
            recent_requests.popitem(last=False)
        return uid

    @app.get("/api/session")
    async def session(request: Request):
        response = JSONResponse(
            {
                "mode": settings.mode,
                "storage": "postgres" if settings.database_url else "sqlite",
                "model": settings.model if settings.mode == "live" else None,
                "sample_prompt": SEBI_PROMPT,
                "sample_updates": [ASYNC_PROMPT, APPROVAL_PROMPT],
                "diagram_types": [
                    {"id": i, "label": label, "category": c, "description": d} for i, label, c, d in CATALOG
                ],
            }
        )
        value = request.cookies.get(COOKIE, "")
        if len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
            response.set_cookie(
                COOKIE,
                secrets.token_hex(32),
                httponly=True,
                samesite="strict",
                secure=settings.cookie_secure,
                max_age=60 * 60 * 24 * 30,
                path="/",
            )
        return response

    @app.get("/api/health")
    async def health():
        try:
            database_ready = await asyncio.to_thread(store.ready)
        except Exception:
            database_ready = False
        renderer_ready = (
            settings.plantuml_jar.is_file()
            and bool(shutil.which(settings.java))
            and bool(shutil.which("dot"))
        )
        ready = database_ready and renderer_ready
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "unavailable",
                "mode": settings.mode,
                "renderer_ready": renderer_ready,
                "database_ready": database_ready,
            },
        )

    @app.get("/api/conversations")
    async def conversations(archived: bool = False, uid=Depends(owner)):
        return await asyncio.to_thread(store.list_conversations, uid, archived)

    @app.get("/api/allowance")
    async def allowance(uid=Depends(owner)):
        return await asyncio.to_thread(
            store.quota, uid, settings.live_daily_limit, settings.live_global_daily_limit
        )

    @app.patch("/api/conversations/{cid}")
    async def manage_conversation(cid: UUID, payload: ConversationUpdateRequest, uid=Depends(mutation)):
        return streamed_json(await asyncio.to_thread(store.update_conversation, uid, str(cid), payload))

    @app.get("/api/conversations/{cid}")
    async def conversation(cid: UUID, uid=Depends(owner)):
        result = await asyncio.to_thread(store.conversation, uid, str(cid))
        return streamed_json(result)

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.post("/api/generate")
    async def generate(payload: GenerateRequest, request: Request, uid=Depends(mutation)):
        replay = await asyncio.to_thread(store.replay, uid, payload)
        if replay:

            async def replay_stream():
                yield sse("complete", replay)

            return StreamingResponse(replay_stream(), media_type="text/event-stream")
        generation_mode = payload.mode or settings.mode
        if generation_mode == "live" and settings.mode != "live":
            raise HTTPException(
                503, "Live AI is unavailable in this workspace. The case study is ready to explore."
            )
        selected_pipeline = sample_pipeline if payload.mode == "sample" else pipeline
        previous = None
        feedback = []
        if payload.conversation_id:
            conv = await asyncio.to_thread(store.conversation, uid, str(payload.conversation_id))
            if conv["archived"]:
                raise Conflict("Restore this archived design before creating a new revision.")
            if generation_mode == "sample" and conv["revisions"][-1]["mode"] != "sample":
                raise Conflict(
                    "Curated refinements belong to a case-study design. Use live AI for this design, or start a new case study."
                )
            if conv["latest"] != payload.base_revision:
                raise Conflict("The conversation changed. Reload the latest revision before updating.")
            previous = Architecture.model_validate(conv["revisions"][-1]["architecture"])
            feedback = await asyncio.to_thread(store.feedback_for, uid, str(payload.conversation_id))
        key = str(payload.conversation_id or payload.request_id)
        if key in active or uid in owners_active:
            raise HTTPException(409, "A design is already in progress. Please wait for it to finish.")
        if len(active) >= settings.max_active_generations:
            raise HTTPException(429, "All design workers are busy. Please retry shortly.")
        await asyncio.to_thread(
            store.claim_generation, uid, str(payload.request_id), settings.max_active_generations
        )
        if generation_mode == "live":
            try:
                await asyncio.to_thread(
                    store.reserve_live_generation,
                    uid,
                    settings.live_daily_limit,
                    settings.live_global_daily_limit,
                )
            except BaseException:
                await asyncio.to_thread(store.release_generation, uid, str(payload.request_id))
                raise
        active.add(key)
        owners_active.add(uid)

        async def stream():
            started = time.perf_counter()
            state = {
                "prompt": payload.prompt,
                "previous": previous,
                "feedback": feedback,
                "diagram_types": payload.diagram_types,
            }
            try:
                yield sse("phase", {"phase": "design", "message": "Building a shared system model"})
                # Graph streams node completion; a validated design is committed atomically only after every view renders.
                async for event in progress_events(selected_pipeline.graph, state):
                    if await request.is_disconnected():
                        return
                    if event is None:
                        yield sse("heartbeat", {"elapsed_seconds": round(time.perf_counter() - started)})
                        continue
                    for node, update in event.items():
                        state.update(update)
                        if node == "design":
                            yield sse(
                                "phase", {"phase": "render", "message": "Compiling and verifying UML syntax"}
                            )
                        elif node == "compile_and_validate":
                            yield sse("phase", {"phase": "save", "message": "Saving your design revision"})
                state["timings"]["total_ms"] = round((time.perf_counter() - started) * 1000)
                revision = await asyncio.to_thread(store.save_revision, uid, payload, state, generation_mode)
                yield sse("complete", revision)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                yield sse(
                    "error",
                    {
                        "message": "This design took too long to verify. Your saved work is safe; retry with fewer views or a smaller brief.",
                        "request_id": str(payload.request_id),
                    },
                )
            except (SampleUnavailable, RenderError, ProviderError, Conflict, NotFound) as e:
                yield sse("error", {"message": str(e), "request_id": str(payload.request_id)})
            except Exception:
                logger.error("Generation failed for request %s", payload.request_id)
                yield sse(
                    "error",
                    {
                        "message": "The design could not be saved. Please retry; previous revisions are safe.",
                        "request_id": str(payload.request_id),
                    },
                )
            finally:
                active.discard(key)
                owners_active.discard(uid)
                try:
                    await asyncio.shield(
                        asyncio.to_thread(store.release_generation, uid, str(payload.request_id))
                    )
                except Exception:
                    logger.warning("Generation lease will expire for request %s", payload.request_id)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.post("/api/render")
    async def render(payload: SourceRequest, uid=Depends(mutation)):
        if uid in render_requests:
            raise HTTPException(429, "A source preview is already rendering")
        render_requests.add(uid)
        try:
            svg, cached = await renderer.render(payload.source)
            return {"svg": svg, "validated": True, "cache_hit": cached}
        except RenderError as e:
            raise HTTPException(422, str(e)) from e
        finally:
            render_requests.discard(uid)

    @app.post("/api/feedback", status_code=201)
    async def feedback(payload: FeedbackRequest, uid=Depends(mutation)):
        return await asyncio.to_thread(store.save_feedback, uid, payload)

    @app.get("/api/revisions/{rid}/feedback")
    async def feedback_list(rid: UUID, uid=Depends(owner)):
        return await asyncio.to_thread(store.feedback_list, uid, str(rid))

    @app.get("/api/revisions/{rid}/export")
    async def export(rid: UUID, uid=Depends(owner)):
        revision = await asyncio.to_thread(store.revision, uid, str(rid))
        reviews = await asyncio.to_thread(store.feedback_list, uid, str(rid))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("DESIGN_REVIEW.md", design_report(revision, reviews, packaged=True))
            archive.writestr("reviews.json", json.dumps(reviews, indent=2, ensure_ascii=False))
            for diagram in revision["diagrams"]:
                archive.writestr(f"diagrams/{diagram['type']}.puml", diagram["source"])
                archive.writestr(f"diagrams/{diagram['type']}.svg", diagram["svg"])
            archive.writestr(
                "architecture.json", json.dumps(revision["architecture"], indent=2, ensure_ascii=False)
            )
            archive.writestr(
                "revision.json",
                json.dumps(
                    {k: revision[k] for k in ["id", "number", "prompt", "mode", "created_at", "timings"]},
                    indent=2,
                ),
            )
            archive.writestr(
                "README.md",
                f"# {revision['architecture']['title']}\n\nRevision {revision['number']}\n\n"
                f"Mode: {revision['mode']}\n\n{revision['architecture']['summary']}\n\n"
                "All diagrams were compiled and syntax-validated with PlantUML. Semantic correctness requires human review.\n",
            )

        async def archive_chunks():
            output.seek(0)
            while chunk := output.read(65536):
                yield chunk

        return StreamingResponse(
            archive_chunks(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="forma-revision-{revision["number"]}.zip"'
            },
        )

    @app.get("/api/revisions/{rid}/report")
    async def report(rid: UUID, uid=Depends(owner)):
        revision, reviews = await asyncio.gather(
            asyncio.to_thread(store.revision, uid, str(rid)),
            asyncio.to_thread(store.feedback_list, uid, str(rid)),
        )
        return HTMLResponse(
            design_report(revision, reviews),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="forma-review-v{revision["number"]}.md"'},
        )

    if (settings.frontend_dir / "api-docs").is_dir():
        app.mount("/api-docs", StaticFiles(directory=settings.frontend_dir / "api-docs"), name="api-docs")

        @app.get("/docs", include_in_schema=False)
        async def api_docs():
            return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="UTF-8">
            <meta name="viewport" content="width=device-width,initial-scale=1"><title>Forma API</title>
            <link rel="stylesheet" href="/api-docs/swagger-ui.css"></head><body><div id="swagger-ui"></div>
            <script src="/api-docs/swagger-ui-bundle.js"></script><script src="/api-docs/init.js"></script>
            </body></html>""")

    if settings.frontend_dir.is_dir():
        assets = settings.frontend_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        async def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Route not found")
            return FileResponse(settings.frontend_dir / "index.html")

    return app


# Uvicorn factory avoids opening state while importing modules for tests or trainer commands.
