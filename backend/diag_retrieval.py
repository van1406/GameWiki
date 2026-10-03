"""Diagnostic: dump raw retrieval candidates (before/after rerank) for phrasings.

Run: python backend/diag_retrieval.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("LLM_PROVIDER", "extractive")

from rag_pipeline import GameWikiRAG, _section_of  # noqa: E402

QUERIES = [
    ("gta5", "What is Trevor's special ability?"),
    ("gta5", "Who is Franklin?"),
    ("gta5", "How do I get rid of a 5 star wanted level?"),
    ("gta5", "best way to lose the cops in GTA 5"),
    ("gta5", "steps to finish the jewel store job"),
    ("gta5", "how do you switch between Michael Franklin and Trevor"),
    ("gta5", "how much money does the jewel store job pay"),
    ("gta5", "what cars can I buy"),
    ("gta5", "how do I make money in GTA 5"),
    ("minecraft", "recipe for a torch"),
    ("minecraft", "how to build a nether portal"),
    ("minecraft", "how to kill the ender dragon"),
    ("minecraft", "how do I get level 30 enchantments"),
    ("minecraft", "how to trade with villagers"),
    ("minecraft", "how does redstone work"),
    ("minecraft", "how to farm wheat"),
    ("minecraft", "what do creepers drop"),
    ("minecraft", "how to get netherite"),
]


def main() -> int:
    rag = GameWikiRAG()
    vs = rag._get_vectorstore()
    for game, q in QUERIES:
        raw = vs.similarity_search_with_score(q, k=40)
        scored = []
        for doc, dist in raw:
            if doc.metadata.get("game") != game:
                continue
            scored.append((rag._to_cosine(dist), _section_of(doc.page_content) or "~", doc.metadata.get("source")))
        scored.sort(key=lambda t: -t[0])
        print(f"\n### ({game}) {q}")
        for s, sec, src in scored[:8]:
            print(f"   {s:.3f}  {src} :: {sec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
