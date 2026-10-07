import asyncio
import io
import json
import logging
import secrets
import time
import zipfile
from collections import OrderedDict
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models import CATALOG, Architecture, FeedbackRequest, GenerateRequest, SourceRequest
from app.pipeline import Pipeline
from app.provider import LiveProvider, ProviderError, SampleProvider
from app.renderer import Renderer, RenderError
from app.sample import APPROVAL_PROMPT, ASYNC_PROMPT, SEBI_PROMPT, SampleUnavailable
from app.store import Conflict, NotFound, Store

logger = logging.getLogger("forma")
COOKIE = "forma_session"


def create_app(settings: Settings | None = None, provider=None, renderer=None):
    settings = settings or Settings()
    if settings.mode not in {"sample", "live"}:
        raise ValueError("FORMA_MODE must be sample or live")
    store = Store(settings.data_dir / "forma.sqlite3")
    renderer = renderer or Renderer(
        settings.plantuml_jar, settings.java, settings.render_timeout, settings.render_concurrency
    )
    provider = provider or (LiveProvider(settings) if settings.mode == "live" else SampleProvider())
    pipeline = Pipeline(provider, renderer)
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
        return {"status": "ok", "mode": settings.mode, "renderer_ready": settings.plantuml_jar.is_file()}

    @app.get("/api/conversations")
    async def conversations(uid=Depends(owner)):
        return await asyncio.to_thread(store.list_conversations, uid)

    @app.get("/api/conversations/{cid}")
    async def conversation(cid: UUID, uid=Depends(owner)):
        return await asyncio.to_thread(store.conversation, uid, str(cid))

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.post("/api/generate")
    async def generate(payload: GenerateRequest, request: Request, uid=Depends(mutation)):
        replay = await asyncio.to_thread(store.replay, uid, payload)
        if replay:

            async def replay_stream():
                yield sse("complete", replay)

            return StreamingResponse(replay_stream(), media_type="text/event-stream")
        previous = None
        feedback = []
        if payload.conversation_id:
            conv = await asyncio.to_thread(store.conversation, uid, str(payload.conversation_id))
            if conv["latest"] != payload.base_revision:
                raise Conflict("The conversation changed. Reload the latest revision before updating.")
            previous = Architecture.model_validate(conv["revisions"][-1]["architecture"])
            feedback = await asyncio.to_thread(store.feedback_for, uid, str(payload.conversation_id))
        key = str(payload.conversation_id or payload.request_id)
        if key in active or uid in owners_active:
            raise HTTPException(409, "A design is already in progress. Please wait for it to finish.")
        if len(active) >= settings.max_active_generations:
            raise HTTPException(429, "All design workers are busy. Please retry shortly.")
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
                async for event in pipeline.graph.astream(state, stream_mode="updates"):
                    if await request.is_disconnected():
                        return
                    for node, update in event.items():
                        state.update(update)
                        if node == "design":
                            yield sse(
                                "phase", {"phase": "render", "message": "Compiling and verifying UML syntax"}
                            )
                        elif node == "compile_and_validate":
                            yield sse("phase", {"phase": "save", "message": "Saving your design revision"})
                state["timings"]["total_ms"] = round((time.perf_counter() - started) * 1000)
                revision = await asyncio.to_thread(store.save_revision, uid, payload, state, settings.mode)
                yield sse("complete", revision)
            except asyncio.CancelledError:
                raise
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
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
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
        return Response(
            output.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="forma-revision-{revision["number"]}.zip"'
            },
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
