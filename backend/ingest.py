"""
ingest.py
---------
Build (or rebuild) the FAISS vector index from knowledge_base/.

Run it whenever you add, change or remove game documents:

    python backend/ingest.py
    # or via the API:  POST http://localhost:8000/ingest

The index is written to vector_store/ together with index_info.json, which records
which games and files are inside the index (used by GET /health).

The index is fully rebuilt each run — simple and safe: deleted or edited files
never leave stale chunks behind. Embeddings are only recomputed here, never
during a user's question.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env from the project root before any config is read.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from document_loader import KNOWLEDGE_BASE_DIR, display_name, load_all_documents  # noqa: E402
from embeddings import get_embeddings  # noqa: E402

VECTOR_STORE_DIR = PROJECT_ROOT / "vector_store"
INDEX_INFO_FILE = VECTOR_STORE_DIR / "index_info.json"


def run_ingestion() -> dict:
    """Scan, chunk, embed, and write the FAISS index. Returns a status dict."""
    from langchain_community.vectorstores import FAISS

    print(f"Scanning {KNOWLEDGE_BASE_DIR} ...")
    documents, warnings = load_all_documents()
    for warning in warnings:
        print(f"  ! {warning}")

    if not documents:
        raise RuntimeError(
            f"No documents found in {KNOWLEDGE_BASE_DIR}. "
            "Add .txt, .pdf or .json files inside a game sub-folder first."
        )

    embeddings = get_embeddings()
    print(f"Generating embeddings for {len(documents)} chunks "
          f"using '{embeddings.model_name}' ...")
    vectorstore = FAISS.from_documents(documents, embeddings)

    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(VECTOR_STORE_DIR))

    # Record what ended up in the index (per-game chunk and file counts).
    games: dict[str, dict] = {}
    for doc in documents:
        game = doc.metadata.get("game", "unknown")
        entry = games.setdefault(game, {"name": display_name(game), "chunks": 0, "files": set()})
        entry["chunks"] += 1
        if doc.metadata.get("source"):
            entry["files"].add(doc.metadata["source"])
    for entry in games.values():
        entry["files"] = sorted(entry["files"])

    info = {
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embedding_model": embeddings.model_name,
        "chunk_count": len(documents),
        "min_score": float(os.getenv("RETRIEVAL_MIN_SCORE", "0.30")),
        "games": games,
        "warnings": warnings,
    }
    INDEX_INFO_FILE.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    for game_id, entry in games.items():
        print(f"  - {entry['name']} ({game_id}): "
              f"{len(entry['files'])} files, {entry['chunks']} chunks")
    print(f"Done. Index saved to {VECTOR_STORE_DIR} "
          f"({len(documents)} chunks, {len(games)} games).")
    return {"status": "ok", **{k: v for k, v in info.items() if k != "games"},
            "games": {gid: {"name": e["name"], "chunks": e["chunks"], "files": e["files"]}
                      for gid, e in games.items()}}


if __name__ == "__main__":
    try:
        run_ingestion()
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)
