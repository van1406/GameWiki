"""
rag_pipeline.py
---------------
The heart of GameWiki AI. Two clearly separated stages:

    1) RETRIEVAL   — embed the question, search FAISS, filter by game and by a
                     similarity threshold, and collect the top chunks.
    2) GENERATION  — hand the retrieved context + question to an LLM that is
                     instructed to answer ONLY from that context.

If retrieval finds nothing relevant, the pipeline never calls the LLM and
returns the standard "not found" message. This is the main hallucination guard.

LLM configuration (all via environment variables, never hard-coded keys):
    LLM_PROVIDER   openai | ollama | extractive   (default: openai)
    LLM_API_KEY    API key for the provider
    LLM_MODEL      model name                      (default depends on provider)
    LLM_API_BASE   OpenAI-compatible base URL      (default depends on provider)

`extractive` is a free offline fallback: it answers by quoting the top retrieved
chunk verbatim, so the app still works end-to-end without any API key.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path

import requests

from document_loader import PROJECT_ROOT, display_name, list_games
from embeddings import get_embeddings

VECTOR_STORE_DIR = PROJECT_ROOT / "vector_store"
INDEX_INFO_FILE = VECTOR_STORE_DIR / "index_info.json"

# The exact sentence returned when retrieval finds nothing relevant.
FALLBACK_ANSWER = (
    "I couldn't find reliable information about this in the current game knowledge base."
)

SYSTEM_PROMPT = (
    "You are GameWiki AI, a game knowledge assistant.\n"
    "Answer using ONLY the supplied context. "
    f"If the context does not contain enough information to answer the question, say: "
    f'"{FALLBACK_ANSWER}"\n'
    "Do not invent mission steps, item statistics, locations, characters, crafting "
    "recipes, mobs, vehicles, weapons, or any other game information. "
    "Never use outside knowledge — if the answer is not in the context, it does not exist.\n"
    "Answer naturally and directly, like a helpful game guide: give the actual steps, "
    "objectives, locations, or facts the question asks for, in plain conversational "
    "language. Do not quote raw document blocks, do not mention how the answer was "
    "produced, and never refer to AI, models, prompts, scores, chunks, embeddings, or "
    "any system internals. Never use the word \"model\" anywhere in your answer — say "
    "\"car\", \"vehicle\" or \"version\" instead. "
    "The user should only see the useful game answer. "
    "Keep answers concise and factual; use short numbered steps or bullet points when "
    "the context describes a process."
)


class IndexMissingError(Exception):
    """Raised when the FAISS index has not been built yet."""


class LLMError(Exception):
    """Raised when the LLM could not be reached or returned an unusable response."""


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------

_DEFAULT_BASES = {
    "openai": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "ollama": ("http://localhost:11434/v1", "llama3.2"),
}


def llm_info() -> dict:
    """Small status dict used by GET /health."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    if provider == "extractive":
        return {"provider": provider, "model": None, "configured": True}
    default_base, default_model = _DEFAULT_BASES.get(provider, _DEFAULT_BASES["openai"])
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base = os.getenv("LLM_API_BASE", "").strip() or default_base
    # Ollama runs locally and does not need a key.
    configured = bool(api_key) or provider == "ollama"
    return {
        "provider": provider,
        "model": os.getenv("LLM_MODEL", "").strip() or default_model,
        "api_base": base,
        "configured": configured,
    }


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call an OpenAI-compatible chat completions endpoint (Groq, OpenRouter, Ollama...)."""
    info = llm_info()
    provider = info["provider"]
    api_key = os.getenv("LLM_API_KEY", "").strip()

    if provider not in _DEFAULT_BASES and provider != "extractive":
        raise LLMError(
            f"Unknown LLM_PROVIDER '{provider}'. Use 'openai', 'ollama' or 'extractive'."
        )
    if provider == "openai" and not api_key:
        raise LLMError(
            "LLM_API_KEY is not set. Copy .env.example to .env and add your free API key "
            "(e.g. from https://console.groq.com), or set LLM_PROVIDER=extractive to run "
            "without an API key."
        )

    payload = {
        "model": info["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,  # deterministic: we want facts, not creativity
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "700")),
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))

    # Free tiers are rate-limited (HTTP 429). Retry with a backoff instead of
    # failing the user's question on a transient limit.
    max_attempts = 4
    response = None
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                f"{info['api_base'].rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            # Transient connection failures (DNS blip, refused socket) get the
            # same backoff treatment as rate limits; timeouts still fail fast.
            if isinstance(exc, requests.ConnectionError) and attempt < max_attempts - 1:
                time.sleep(min(3.0 * (2 ** attempt), 60.0))
                continue
            raise LLMError(f"Could not reach the LLM at {info['api_base']}: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            if attempt < max_attempts - 1:
                delay = 3.0 * (2 ** attempt)  # 3s, 6s, 12s
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                time.sleep(min(delay, 60.0))
                continue
        break

    if response.status_code != 200:
        detail = response.text[:300]
        raise LLMError(f"LLM request failed (HTTP {response.status_code}): {detail}")

    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Unexpected response from the LLM: {exc}") from exc
    if not content:
        raise LLMError("The LLM returned an empty response.")
    return content


def _join_overlap(first: str, second: str) -> str:
    """Append `second` to `first`, collapsing duplicated chunk overlap."""
    max_len = min(len(first), len(second))
    for k in range(max_len, 0, -1):
        if first.endswith(second[:k]):
            return first + second[k:]
    return first + "\n" + second


def _polish_answer(text: str) -> str:
    """Turn a raw chunk into answer text: drop every '=== Heading ===' marker and
    metadata line (Game:/Category:) so only the useful content remains."""
    title: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^===\s*(.+?)\s*===$", stripped)
        if match:
            if title is None:
                title = match.group(1)  # first heading doubles as the answer title
            continue  # later headings would be raw document markers
        if re.match(r"^(Game|Category):\s*\S", stripped):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    if title:
        return f"{title}\n\n{body}".strip()
    return body


def _extractive_answer(results: list[tuple]) -> str:
    """Offline fallback: present the retrieved section as a clean, natural answer.

    Joins chunks of the same section (overlapping chunks are de-duplicated) so long
    mission walkthroughs come out complete instead of truncated.
    """
    top_doc, _score = results[0]
    section = _section_of_doc(top_doc)
    parts = [top_doc.page_content]
    if section is not None:
        for doc, _s in results[1:]:
            if (
                doc.metadata.get("source") == top_doc.metadata.get("source")
                and _section_of_doc(doc) == section
            ):
                parts.append(doc.page_content)

    text = parts[0]
    for part in parts[1:]:
        # Continuation chunks repeat the section heading — drop it before joining
        # so the overlap merge and the final answer stay clean.
        part = re.sub(r"^===\s*.+?\s*===\s*\n?", "", part)
        text = _join_overlap(text, part)
    if len(text) > 2800:
        text = text[:2800].rsplit(" ", 1)[0] + " ..."
    return _polish_answer(text)


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

def _section_of(chunk_text: str) -> str | None:
    """Find the '=== Section Name ===' heading a chunk belongs to (if any)."""
    match = re.search(r"^===\s*(.+?)\s*===", chunk_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _section_of_doc(doc) -> str | None:
    """Section of a document: metadata set at ingestion time, with the
    in-text heading as a fallback (PDFs and older indexes)."""
    section = (doc.metadata or {}).get("section")
    if section:
        return str(section)
    return _section_of(doc.page_content)


def _build_context(results: list[tuple]) -> tuple[str, list[str]]:
    """Join retrieved chunks into one context string, keeping source labels."""
    blocks: list[str] = []
    for doc, _score in results:
        meta = doc.metadata
        label = f"{meta.get('game', '?')}/{meta.get('source', '?')}"
        if meta.get("page"):
            label += f" (page {meta['page']})"
        section = _section_of_doc(doc)
        if section:
            label += f" — {section}"
        blocks.append(f"[Source: {label}]\n{doc.page_content}")
    return "\n\n---\n\n".join(blocks), blocks


def _build_sources(results: list[tuple]) -> list[dict]:
    """Deduplicate sources by (file, page), collecting the sections used."""
    sources: list[dict] = []
    index_by_key: dict[tuple, int] = {}
    for doc, _score in results:
        meta = doc.metadata
        key = (meta.get("source"), meta.get("page"))
        section = _section_of_doc(doc)
        if key not in index_by_key:
            index_by_key[key] = len(sources)
            sources.append(
                {
                    "file": meta.get("source"),
                    "page": meta.get("page"),
                    "title": meta.get("title"),
                    "game": meta.get("game"),
                    "sections": [section] if section else [],
                }
            )
        else:
            entry = sources[index_by_key[key]]
            if section and section not in entry["sections"]:
                entry["sections"].append(section)
    return sources


# ---------------------------------------------------------------------------
# Lexical re-ranking (works WITH the embedding search, never instead of it)
# ---------------------------------------------------------------------------
#
# Dense embeddings are great at paraphrases but weak at small distinguishing
# words ("5-star" vs "4-star", "Trevor" vs "Franklin"). After FAISS similarity
# search and the unchanged relevance threshold, surviving candidates are
# re-weighted by how much of the question's distinctive vocabulary they cover:
# terms that appear in only a few candidates (IDF) count much more than terms
# that appear in every candidate. This only reorders already-relevant chunks.

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "in", "on", "at", "to",
    "for", "with", "from", "by", "is", "are", "was", "were", "be", "been", "am",
    "do", "does", "did", "done", "can", "could", "should", "would", "will",
    "shall", "may", "might", "must", "i", "you", "he", "she", "it", "we",
    "they", "me", "my", "your", "his", "her", "its", "our", "their", "this",
    "that", "these", "those", "what", "which", "who", "whom", "whose", "when",
    "where", "why", "how", "not", "no", "so", "than", "then", "there", "here",
    "about", "into", "over", "under", "again", "very", "just", "also", "up",
}


# Extra weight given when the question's terms appear in the section heading
# (identifies "5-Star" vs "1-Star" or "Trevor" vs "Franklin" at a glance).
_HEADING_WEIGHT = 0.15


def _normalize_token(token: str) -> str:
    """Very light stemmer applied to BOTH the question and the chunks so that
    craft/crafting/crafted, remove/removed, trade/trading all line up."""
    if token.isdigit():
        return token
    t = token
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("ing"):
        t = t[:-3]
    elif len(t) > 3 and t.endswith("ed"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("es"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    if len(t) > 3 and t.endswith("e"):
        t = t[:-1]
    return t


def _token_set(text: str) -> set[str]:
    """Normalized content tokens of a text (stopwords removed, numbers kept)."""
    tokens = set()
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if raw in _STOPWORDS:
            continue
        norm = _normalize_token(raw)
        if not norm or norm in _STOPWORDS:
            continue
        if len(norm) < 2 and not norm.isdigit():
            continue  # drop fragments like "s" from "Trevor's"
        tokens.add(norm)
    return tokens


def _content_tokens(text: str) -> set[str]:
    """Tokens used for lexical matching, ignoring document metadata lines
    ("Game: GTA 5" / "Category: ...") that are identical across chunks and
    would otherwise drown out the words that actually distinguish sections."""
    cleaned = "\n".join(
        line for line in text.splitlines()
        if not re.match(r"^\s*(Game|Category):\s*\S", line)
    )
    return _token_set(cleaned)


def _lexical_scores(
    question: str, chunk_texts: list[str], headings: list[str | None]
) -> tuple[list[float], list[float]]:
    """IDF-weighted lexical scores for each candidate.

    Returns (body_coverage, heading_coverage), both in 0..1:
      * body_coverage    — fraction of the question's distinctive terms the
        chunk contains (terms in every candidate contribute nothing).
      * heading_coverage — the same fraction counted only in the chunk's
        '=== Section ===' heading, which strongly identifies the section a
        question is really about ("5-Star" vs "1-Star", "Trevor" vs "Franklin").

    Returns all-zeros when the question shares no content terms with the
    candidates.
    """
    if not chunk_texts:
        return [], []
    query_tokens = _content_tokens(question)
    if not query_tokens:
        return [0.0] * len(chunk_texts), [0.0] * len(chunk_texts)
    chunk_tokens = [_content_tokens(text) for text in chunk_texts]
    n = len(chunk_tokens)
    idf: dict[str, float] = {}
    for term in query_tokens:
        df = sum(1 for tokens in chunk_tokens if term in tokens)
        if df:
            weight = math.log(n / df)  # term in every candidate -> 0
            if weight > 0:
                idf[term] = weight
    total = sum(idf.values())
    if total <= 0:
        return [0.0] * n, [0.0] * n
    body = [
        sum(w for t, w in idf.items() if t in tokens) / total
        for tokens in chunk_tokens
    ]
    heading_tokens = [_content_tokens(heading or "") for heading in headings]
    heading = [
        sum(w for t, w in idf.items() if t in tokens) / total
        for tokens in heading_tokens
    ]
    return body, heading


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

class GameWikiRAG:
    """Loads the FAISS index once and answers questions about a single game."""

    def __init__(self) -> None:
        self._vectorstore = None
        self.min_score = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.30"))
        self.top_k = int(os.getenv("RETRIEVAL_TOP_K", "4"))
        # Strength of the lexical re-ranking bonus (0 = pure cosine ranking).
        self.lexical_weight = float(os.getenv("RETRIEVAL_LEXICAL_WEIGHT", "0.45"))

    # -- retrieval stage -----------------------------------------------------

    @staticmethod
    def index_available() -> bool:
        return (VECTOR_STORE_DIR / "index.faiss").exists()

    def _get_vectorstore(self):
        if self._vectorstore is None:
            if not self.index_available():
                raise IndexMissingError(
                    "Vector index not found. Run 'python backend/ingest.py' first."
                )
            from langchain_community.vectorstores import FAISS

            self._vectorstore = FAISS.load_local(
                str(VECTOR_STORE_DIR),
                get_embeddings(),
                allow_dangerous_deserialization=True,
            )
        return self._vectorstore

    @staticmethod
    def _to_cosine(l2_squared: float) -> float:
        """For unit vectors: squared L2 distance d = 2(1 - cos) => cos = 1 - d/2."""
        cosine = 1.0 - float(l2_squared) / 2.0
        return max(-1.0, min(1.0, cosine))

    def retrieve(self, game: str, question: str) -> list[tuple]:
        """
        Return [(Document, cosine_score)] for `game` only, above the relevance
        threshold, sorted by relevance descending, at most top_k items.

        Stage 1 is unchanged: embed the question, FAISS similarity search, drop
        other games, drop everything below the cosine threshold (this is the
        hallucination gate and it always uses the RAW cosine score).
        Stage 2 only re-orders the survivors with an IDF-weighted lexical
        coverage bonus, so paraphrases land on the right section while the
        threshold semantics stay exactly as before.
        """
        vectorstore = self._get_vectorstore()
        search_k = max(self.top_k * 10, 40)
        raw = vectorstore.similarity_search_with_score(question, k=search_k)

        survivors: list[tuple] = []
        for doc, distance in raw:
            if doc.metadata.get("game") != game:
                continue  # never mix games
            cosine = self._to_cosine(distance)
            if cosine < self.min_score:
                continue  # drop unrelated chunks before they reach the LLM
            survivors.append((doc, cosine))

        if not survivors:
            return []

        body_cov, head_cov = _lexical_scores(
            question,
            [doc.page_content for doc, _ in survivors],
            [_section_of_doc(doc) for doc, _ in survivors],
        )
        ranked = []
        for (doc, cosine), b_cov, h_cov in zip(survivors, body_cov, head_cov):
            # Weakly-relevant chunks only get a part of the bonus: the lexical
            # signal may re-order well-matching chunks, but it can never lift a
            # barely-eligible chunk above clearly better-matching ones.
            gate = min(1.0, max(0.0, (cosine - self.min_score) / 0.2))
            bonus = gate * (self.lexical_weight * b_cov + _HEADING_WEIGHT * h_cov)
            ranked.append((doc, cosine, cosine + bonus))
        ranked.sort(key=lambda item: -item[2])
        return [(doc, cosine) for doc, cosine, _ in ranked[: self.top_k]]

    # -- generation stage ----------------------------------------------------

    def generate(self, game: str, question: str, results: list[tuple]) -> str:
        """Answer `question` using ONLY the retrieved chunks."""
        context, _blocks = _build_context(results)
        info = llm_info()
        provider = info["provider"]

        if provider == "extractive" or (provider == "openai" and not info["configured"]):
            # Offline fallback (explicit extractive mode or no API key configured):
            # present the retrieved content directly as the answer, with no meta
            # commentary. Bad keys / network failures still raise LLMError -> 503.
            return _extractive_answer(results)

        game_name = display_name(game)
        user_prompt = (
            f"Game: {game_name}\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer using only the context above."
        )
        return _call_llm(SYSTEM_PROMPT, user_prompt)

    # -- full pipeline -------------------------------------------------------

    def ask(self, game: str, question: str) -> dict:
        """Retrieve + generate. Returns answer, sources and retrieval status."""
        results = self.retrieve(game, question)

        if not results:
            # Nothing relevant -> no LLM call, no invented answer.
            return {
                "game": game,
                "question": question,
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "found": False,
                "retrieved_chunks": 0,
            }

        answer = self.generate(game, question, results)

        return {
            "game": game,
            "question": question,
            "answer": answer,
            "sources": _build_sources(results),
            "found": True,
            "retrieved_chunks": len(results),
        }


# ---------------------------------------------------------------------------
# Ingestion info (used by /health and /ingest)
# ---------------------------------------------------------------------------

def read_index_info() -> dict | None:
    if not INDEX_INFO_FILE.exists():
        return None
    try:
        return json.loads(INDEX_INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ingested_games() -> list[str]:
    info = read_index_info()
    if not info:
        return []
    ingested = [g["id"] for g in list_games()]
    known = set(info.get("games", {}).keys())
    return [g for g in ingested if g in known]
