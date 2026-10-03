"""
test_pipeline.py — quick end-to-end check of the RAG pipeline (no server needed).

Run:  python backend/test_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("LLM_PROVIDER", "extractive")  # works without an API key

from rag_pipeline import FALLBACK_ANSWER, GameWikiRAG  # noqa: E402


def show(title: str, result: dict) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])


def main() -> int:
    rag = GameWikiRAG()

    r1 = rag.ask("gta5", "How do I complete The Jewel Store Job?")
    show("1. GTA 5 heist walkthrough (expected: found, cites missions.txt)", r1)

    r2 = rag.ask("gta5", "Who is the president of France?")
    show("2. Hallucination guard (expected: not-found message, sources: [])", r2)

    r3 = rag.ask("minecraft", "How do I craft a diamond pickaxe?")
    show("3. Minecraft crafting (expected: found, cites crafting.txt)", r3)

    r4 = rag.ask("gta5", "How do I craft a diamond pickaxe?")
    show("4. Game isolation (expected: not-found — Minecraft info must not leak)", r4)

    checks = [
        ("heist question found", r1.get("found") is True),
        ("heist sources cite missions.txt", any(s["file"] == "missions.txt" for s in r1["sources"])),
        ("unrelated question returns fallback", r2.get("answer") == FALLBACK_ANSWER and not r2["sources"]),
        ("minecraft question found", r3.get("found") is True),
        ("minecraft sources cite crafting.txt", any(s["file"] == "crafting.txt" for s in r3["sources"])),
        ("gta5 does not answer minecraft question", r4.get("answer") == FALLBACK_ANSWER),
    ]
    print(f"\n{'-' * 70}\nRESULTS")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print(f"\nChunks used: heist={r1.get('retrieved_chunks')} "
          f"minecraft={r3.get('retrieved_chunks')}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
