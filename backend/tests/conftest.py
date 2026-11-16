import os
import sys
import tempfile
from pathlib import Path

import pytest_asyncio

# Configure before the app (and its cached settings / engine) is imported.
_tmp = Path(tempfile.mkdtemp(prefix="tellwind-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["SEED_DEMO"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def make_client():
    await db.create_all()
    clients: list[httpx.AsyncClient] = []

    async def make() -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()
