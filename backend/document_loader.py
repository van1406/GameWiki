"""
document_loader.py
------------------
Scans the knowledge_base/ folder and turns every supported file into LangChain
`Document` objects, then splits them into chunks.

Layout expected:

    knowledge_base/
        gta5/
            missions.txt
            characters.txt
            ...
        minecraft/
            mobs.txt
            ...

Each sub-folder = one game. The folder name becomes the game id used by the API
("gta5", "minecraft", ...). Supported file types: .txt, .pdf, .json.

Every chunk gets metadata so answers can cite their source later:
    game, source (filename), path, doc_type, page (PDF only), title
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Project root (parent of backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".json"}

# Chunking settings (can be overridden with env vars)
CHUNK_SIZE = int(__import__("os").getenv("CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(__import__("os").getenv("CHUNK_OVERLAP", "150"))

# Friendly display names for known games (anything else is auto-titled).
GAME_NAME_OVERRIDES = {
    "gta5": "GTA 5",
    "minecraft": "Minecraft",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def display_name(game_id: str) -> str:
    """Folder id -> nice name, e.g. 'gta5' -> 'GTA 5', 'elden_ring' -> 'Elden Ring'."""
    if game_id in GAME_NAME_OVERRIDES:
        return GAME_NAME_OVERRIDES[game_id]
    return game_id.replace("_", " ").title()


def clean_text(text: str) -> str:
    """Normalize whitespace so chunks are consistent (without touching meaning)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse 3+ blank lines
    return text.strip()


def extract_title(text: str, fallback: str) -> str:
    """Use the first Markdown heading ('# Title') of a file as its display title."""
    for line in text.split("\n")[:10]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip().rstrip("#").strip() or fallback
        if stripped.startswith("#"):
            continue
        if stripped:  # first non-empty line is not a heading
            break
    return fallback


def _make_splitter() -> RecursiveCharacterTextSplitter:
    """Splits on paragraph > line > sentence > word boundaries, keeping chunks readable."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _base_metadata(path: Path, game: str, doc_type: str) -> dict:
    return {
        "game": game,
        "source": path.name,
        "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "doc_type": doc_type,
        "page": None,
        "title": path.stem,
    }


# ---------------------------------------------------------------------------
# Per-format loaders
# ---------------------------------------------------------------------------

def load_txt(path: Path, game: str) -> list[Document]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = clean_text(raw)
    if not text:
        return []
    title = extract_title(text, fallback=path.stem)
    splitter = _make_splitter()
    return [
        Document(page_content=chunk, metadata={**_base_metadata(path, game, "txt"), "title": title})
        for chunk in splitter.split_text(text)
    ]


def load_pdf(path: Path, game: str) -> list[Document]:
    """Load a PDF one page at a time so page numbers are preserved in metadata."""
    from pypdf import PdfReader  # imported lazily: only needed when PDFs exist

    reader = PdfReader(str(path))
    pdf_title = path.stem
    try:
        if reader.metadata and reader.metadata.title:
            pdf_title = str(reader.metadata.title).strip() or path.stem
    except Exception:
        pass

    splitter = _make_splitter()
    docs: list[Document] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        if not text:
            continue
        for chunk in splitter.split_text(text):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        **_base_metadata(path, game, "pdf"),
                        "page": page_number,
                        "title": pdf_title,
                    },
                )
            )
    return docs


def _flatten_json(node, prefix: str = "") -> list[str]:
    """Turn nested JSON into readable 'key: value' lines the RAG can search."""
    lines: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            new_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(value, new_prefix))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            lines.extend(_flatten_json(value, f"{prefix}[{index}]"))
    else:
        lines.append(f"{prefix}: {node}")
    return lines


def load_json(path: Path, game: str) -> list[Document]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
        text = clean_text("\n".join(_flatten_json(data)))
    except json.JSONDecodeError:
        text = clean_text(raw)  # fall back to plain text if the JSON is malformed
    if not text:
        return []
    title = extract_title(text, fallback=path.stem)
    splitter = _make_splitter()
    return [
        Document(page_content=chunk, metadata={**_base_metadata(path, game, "json"), "title": title})
        for chunk in splitter.split_text(text)
    ]


def load_file(path: Path, game: str) -> list[Document]:
    """Dispatch to the right loader based on the file extension."""
    extension = path.suffix.lower()
    if extension == ".txt":
        return load_txt(path, game)
    if extension == ".pdf":
        return load_pdf(path, game)
    if extension == ".json":
        return load_json(path, game)
    return []


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def list_games() -> list[dict]:
    """Every sub-folder of knowledge_base/ that contains at least one supported file."""
    games: list[dict] = []
    if not KNOWLEDGE_BASE_DIR.exists():
        return games
    for game_dir in sorted(p for p in KNOWLEDGE_BASE_DIR.iterdir() if p.is_dir()):
        if game_dir.name.startswith("."):
            continue
        files = sorted(
            p.name
            for p in game_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if files:
            games.append({"id": game_dir.name, "name": display_name(game_dir.name), "files": files})
    return games


def load_all_documents() -> tuple[list[Document], list[str]]:
    """
    Walk knowledge_base/<game>/<files> and return (documents, warnings).
    Unreadable files are reported in `warnings` instead of crashing ingestion.
    """
    documents: list[Document] = []
    warnings: list[str] = []
    if not KNOWLEDGE_BASE_DIR.exists():
        warnings.append(f"Knowledge base folder not found: {KNOWLEDGE_BASE_DIR}")
        return documents, warnings

    for game_dir in sorted(p for p in KNOWLEDGE_BASE_DIR.iterdir() if p.is_dir()):
        if game_dir.name.startswith("."):
            continue
        for path in sorted(game_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                docs = load_file(path, game_dir.name)
                documents.extend(docs)
            except Exception as exc:  # keep going: one bad file must not break ingestion
                warnings.append(f"Failed to load {path.name}: {exc}")
    return documents, warnings
