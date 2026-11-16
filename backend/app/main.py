import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db as dbmod
from .agent import runner
from .api import auth, content, qa, workspaces
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tellwind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    await dbmod.create_all()
    n = await runner.recover_stale_runs()
    if n:
        log.warning("marked %d interrupted runs as failed", n)
    if s.seed_demo:
        from .seed.demo import seed_demo

        try:
            await seed_demo()
        except Exception:  # noqa: BLE001 - never block startup on the demo
            log.exception("demo seed failed")
    task = None
    if s.scheduler_enabled:
        from .scheduler import loop

        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Tellwind", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(content.router)
app.include_router(content.cron_router)
app.include_router(qa.router)


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True}


# SPA: serve the built frontend from the same origin

_static = get_settings().static_dir
if (_static / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")
if (_static / "brand").exists():
    app.mount("/brand", StaticFiles(directory=_static / "brand"), name="brand")


@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def spa(path: str, request: Request):
    if path.startswith("api/"):
        raise HTTPException(404)
    f = _static / path
    if path and f.is_file() and _static in f.resolve().parents:
        return FileResponse(f)
    index = _static / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "frontend not built"}, status_code=404)
