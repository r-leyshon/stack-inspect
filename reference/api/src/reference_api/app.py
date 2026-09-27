"""Reference API. Every endpoint exists to demonstrate one stack-inspect behaviour."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import asyncpg
import stack_inspect_db
import stack_inspect_fastapi
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:stackinspect@127.0.0.1:54329/stackinspect",
)
ALLOWED_ORIGIN = os.environ.get("WEB_ORIGIN", "http://127.0.0.1:3000")
SEEDED_ITEMS = ("alpha", "beta", "gamma", "delta", "epsilon")
STREAM_MESSAGES = 3


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open a traced pool and seed the items table."""
    stack_inspect_db.install()
    pool = await asyncpg.create_pool(DATABASE_URL)
    app.state.pool = pool
    async with pool.acquire() as connection:
        await connection.execute("CREATE TABLE IF NOT EXISTS items (id int primary key, name text)")
        await connection.execute("DELETE FROM items")
        for index, name in enumerate(SEEDED_ITEMS, start=1):
            await connection.execute("INSERT INTO items (id, name) VALUES ($1, $2)", index, name)
    yield
    await pool.close()


def create_app() -> FastAPI:  # noqa: C901 # each route is one planted behaviour, kept together so the app reads as a list
    """Build the reference application and install the adapter."""
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ALLOWED_ORIGIN, "http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "traceparent"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/crash")
    async def crash() -> dict[str, str]:
        """Raise so the browser sees a CORS failure instead of this error."""
        message = "planted crash"
        raise RuntimeError(message)

    @app.get("/api/items")
    async def items() -> dict[str, bool]:
        """Used by the disallowed custom-header preflight."""
        return {"ok": True}

    @app.get("/api/dashboard")
    async def dashboard() -> dict[str, int]:
        """One query. The cross-stack trace ends here."""
        async with app.state.pool.acquire() as connection:
            count = await connection.fetchval("SELECT COUNT(*) FROM items")
        return {"count": int(count)}

    @app.get("/api/n-plus-one")
    async def n_plus_one() -> dict[str, list[str]]:
        """One query per row, after a query for the ids."""
        async with app.state.pool.acquire() as connection:
            rows = await connection.fetch("SELECT id FROM items")
            names: list[str] = []
            for row in rows:
                name = await connection.fetchval("SELECT name FROM items WHERE id = $1", row["id"])
                names.append(str(name))
        return {"names": names}

    @app.get("/api/sequential")
    async def sequential() -> dict[str, int]:
        """Two independent queries awaited one after the other."""
        async with app.state.pool.acquire() as connection:
            ids = await connection.fetch("SELECT id FROM items")
            names = await connection.fetch("SELECT name FROM items")
        return {"ids": len(ids), "names": len(names)}

    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        """A short server-sent event stream."""

        async def generate() -> AsyncIterator[str]:
            for index in range(STREAM_MESSAGES):
                yield f"id: {index + 1}\ndata: hello {index + 1}\n\n"
                await asyncio.sleep(0.05)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.websocket("/api/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Echo one message, then close."""
        await websocket.accept()
        text = await websocket.receive_text()
        await websocket.send_text(f"echo:{text}")
        await websocket.close()

    stack_inspect_fastapi.install(app)
    return app


app = create_app()
