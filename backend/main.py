"""
main.py
-------
FastAPI backend for GameWiki AI.

Endpoints:
    GET  /health  -> service status (index built? LLM configured?)
    GET  /games   -> games available in knowledge_base/
    POST /ask     -> {game, question} -> RAG answer + sources
    POST /ingest  -> rebuild the FAISS index from knowledge_base/

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root, and make backend modules importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from document_loader import list_games  # noqa: E402
from ingest import run_ingestion  # noqa: E402
from rag_pipeline import (  # noqa: E402
    FALLBACK_ANSWER,
    GameWikiRAG,
    IndexMissingError,
    LLMError,
    ingested_games,
    llm_info,
    read_index_info,
)

app = FastAPI(title="GameWiki AI", version="1.0.0")

# The Vite dev server (http://localhost:5173) calls this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# RAG singleton (the FAISS index + embedding model stay loaded between requests)
# ---------------------------------------------------------------------------

_rag_lock = threading.Lock()
_rag: GameWikiRAG | None = None


def get_rag() -> GameWikiRAG:
    global _rag
    with _rag_lock:
        if _rag is None:
            _rag = GameWikiRAG()
        return _rag


def reset_rag() -> None:
    """Drop the cached index so the next request loads the freshly ingested one."""
    global _rag
    with _rag_lock:
        _rag = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    game: str = Field(..., description="Game id, e.g. 'gta5'")
    question: str = Field(..., description="Natural language question")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    info = read_index_info()
    llm = {k: v for k, v in llm_info().items() if k != "api_base"}
    return {
        "status": "ok",
        "index_available": GameWikiRAG.index_available(),
        "ingested_at": info.get("ingested_at") if info else None,
        "games_ingested": ingested_games(),
        "llm": llm,
        "fallback_answer": FALLBACK_ANSWER,
    }


@app.get("/games")
def games() -> list[dict]:
    """Games discovered from knowledge_base/ sub-folders."""
    ingested = set(ingested_games())
    return [
        {**game, "ingested": game["id"] in ingested}
        for game in list_games()
    ]


@app.post("/ask")
async def ask(payload: AskRequest) -> dict:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    known_games = {game["id"] for game in list_games()}
    if payload.game not in known_games:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown game '{payload.game}'. Available: {sorted(known_games)}",
        )

    if not GameWikiRAG.index_available():
        raise HTTPException(
            status_code=503,
            detail="Vector index not built. Run 'python backend/ingest.py' or POST /ingest first.",
        )

    try:
        # Heavy work (embedding + FAISS search + LLM call) runs off the event loop.
        return await run_in_threadpool(get_rag().ask, payload.game, question)
    except IndexMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # unexpected errors still get a clean JSON response
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")


@app.post("/ingest")
async def ingest() -> dict:
    """Rebuild the vector index from knowledge_base/ (run after adding documents)."""
    try:
        result = await run_in_threadpool(run_ingestion)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")
    reset_rag()  # next /ask picks up the new index
    return result
