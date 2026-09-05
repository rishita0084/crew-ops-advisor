"""FastAPI entrypoint.

Loads the operational picture once at startup so every request is served from memory.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import CORS_ORIGINS, DB_PATH
from app.db.repository import get_repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.exists():
        # The database is a generated cache of the committed JSON dataset. Hosting
        # platforms such as Render use an ephemeral filesystem, so a fresh deploy or
        # restart may not contain it even when the application code is present.
        from scripts.import_data import main as import_data

        print(f"No database at {DB_PATH}; rebuilding it from the JSON dataset")
        import_data()

    if not DB_PATH.exists():
        raise RuntimeError(f"Database bootstrap did not create {DB_PATH}")
    repo = get_repository()
    print(
        f"Crew Ops Advisor ready - {len(repo.crew)} crew, {len(repo.flights)} flights, "
        f"{len(repo.pairings)} pairings"
    )
    yield


app = FastAPI(
    title="dCortex Crew Ops Advisor",
    version="1.0.0",
    description=(
        "Conversational crew-control advisor. The LLM interprets and explains; "
        "deterministic code decides legality, cost and recovery."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(router)   # /health also served unprefixed
