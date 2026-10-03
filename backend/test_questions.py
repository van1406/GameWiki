"""
test_questions.py — end-to-end checks for the required GTA 5 / Minecraft /
Forza Horizon 6 questions.

Run:  python backend/test_questions.py             (retrieval + configured LLM)
      python backend/test_questions.py --extractive (offline, retrieval only)

For every question it verifies:
  * retrieval finds something relevant (found == True)
  * the right knowledge-base file is among the sources
  * the answer never leaks pipeline internals (RAG, FAISS, embeddings, Groq,
    API keys, similarity scores, chunk counts, raw document boilerplate)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

if "--extractive" in sys.argv:
    os.environ["LLM_PROVIDER"] = "extractive"

from rag_pipeline import FALLBACK_ANSWER, GameWikiRAG  # noqa: E402

# (game, question, expected source file substring or None)
QUESTIONS: list[tuple[str, str, str | None]] = [
    # --- GTA 5 ---
    ("gta5", "How do I remove a 5-star wanted level?", "wanted_level.txt"),
    ("gta5", "Who is Franklin?", "characters.txt"),
    ("gta5", "What is the Jewel Store Job?", "heists.txt"),
    ("gta5", "How do I complete the Jewel Store Job?", "mission"),
    ("gta5", "How do I switch characters?", "characters.txt"),
    ("gta5", "What is Trevor's special ability?", "characters.txt"),
    # --- Minecraft (required final tests) ---
    ("minecraft", "How do I craft a torch?", "crafting.txt"),
    ("minecraft", "How do I craft a diamond sword?", "crafting.txt"),
    ("minecraft", "How do I find diamonds?", None),
    ("minecraft", "How do I survive the first night?", "progression.txt"),
    ("minecraft", "How do I make a Nether portal?", None),
    ("minecraft", "How do I find a Nether fortress?", None),
    ("minecraft", "How do I defeat the Ender Dragon?", None),
    ("minecraft", "How does enchanting work?", None),
    ("minecraft", "How does villager trading work?", None),
    ("minecraft", "How do I get an Elytra?", None),
    ("minecraft", "How do I fight a Creeper?", "mobs.txt"),
    # --- Minecraft (practical how-to coverage) ---
    ("minecraft", "How do I find a stronghold?", None),
    ("minecraft", "How do I get blaze rods?", None),
    ("minecraft", "How do I brew potions?", "potions.txt"),
    ("minecraft", "How do I get villagers?", "villagers.txt"),
    ("minecraft", "How do I get Netherite?", None),
    ("minecraft", "How do I make a farm?", "farming.txt"),
    ("minecraft", "Where do Endermen spawn?", "mobs.txt"),
    ("minecraft", "What workstation does a librarian need?", "villagers.txt"),
    ("minecraft", "How do I automate a farm?", "farming.txt"),
    ("minecraft", "How do I build a redstone door?", "redstone.txt"),
    ("minecraft", "How do I ride a horse?", "transportation.txt"),
    ("minecraft", "How do I find an ocean monument?", "structures.txt"),
    ("minecraft", "What does the Warden drop?", "mobs.txt"),
    # --- Forza Horizon 6 (practical how-to coverage) ---
    ("forza_horizon_6", "How do I unlock Legend Island?", "campaign"),
    ("forza_horizon_6", "How do I get a new car?", "cars.txt"),
    ("forza_horizon_6", "How do I buy cars?", None),
    ("forza_horizon_6", "How do I tune my car?", "tuning"),
    ("forza_horizon_6", "How do I upgrade my car?", "upgrades"),
    ("forza_horizon_6", "How do I join a Convoy?", "multiplayer"),
    ("forza_horizon_6", "What are Touge Battles?", "races"),
    ("forza_horizon_6", "How do I participate in Drag Meets?", "races"),
    ("forza_horizon_6", "How does the Festival Playlist work?", "festival_playlist"),
    ("forza_horizon_6", "How do I earn reward cars?", "rewards"),
    ("forza_horizon_6", "What is EventLab?", "eventlab"),
    ("forza_horizon_6", "How does CoLab work?", "eventlab"),
    ("forza_horizon_6", "Where is Tokyo City?", "locations"),
    ("forza_horizon_6", "What is the Horizon Festival?", "overview"),
    ("forza_horizon_6", "What are Wristbands?", "progression"),
    ("forza_horizon_6", "How do I progress through the campaign?", "campaign"),
    ("forza_horizon_6", "How do Car Meets work?", "car_meets"),
    ("forza_horizon_6", "How do I customize my garage?", "houses_and_garages"),
    ("forza_horizon_6", "How do I get Aftermarket Cars?", "cars.txt"),
    # --- Forza Horizon 6 (car recommendations) ---
    ("forza_horizon_6", "What is the best sedan in FH6?", "car_recommendations"),
    ("forza_horizon_6", "What is the best SUV?", "car_recommendations"),
    ("forza_horizon_6", "What is the best sports car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best supercar?", "car_recommendations"),
    ("forza_horizon_6", "What is the best hypercar?", "car_recommendations"),
    ("forza_horizon_6", "What is the best JDM car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best muscle car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best drift car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best rally car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best off-road car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best drag car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best car for street racing?", "car_recommendations"),
    ("forza_horizon_6", "What is the best beginner car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best AWD car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best RWD car?", "car_recommendations"),
    ("forza_horizon_6", "What is the best car for Tokyo City?", "car_recommendations"),
    ("forza_horizon_6", "What is the best car for Touge?", "car_recommendations"),
    ("forza_horizon_6", "What is the best value car?", "car_recommendations"),
    # --- guardrails (must stay safe) ---
    ("gta5", "Who is the president of France?", "FALLBACK"),
    ("gta5", "How do I craft a diamond pickaxe?", "FALLBACK"),
    # --- game isolation (FH6 vs GTA 5 vs Minecraft) ---
    ("gta5", "What are Wristbands?", "FALLBACK"),
    ("gta5", "How does CoLab work?", "FALLBACK"),
    ("minecraft", "What is the best drift car?", "FALLBACK"),
    ("minecraft", "How does the Festival Playlist work?", "FALLBACK"),
    ("minecraft", "How do I participate in Drag Meets?", "FALLBACK"),
    ("forza_horizon_6", "How do I remove a 5-star wanted level?", "FALLBACK"),
    ("forza_horizon_6", "How do I craft a diamond sword?", "FALLBACK"),
]

import re  # noqa: E402

# Each pattern is searched (case-insensitive) in the user-facing answer text.
LEAK_PATTERNS = [
    r"\brag\b",
    r"\bfaiss\b",
    r"\bembedd?ings?\b",
    r"\bgroq\b",
    r"\bapi[ _-]?key\b",
    r"\bsimilarity\b",
    r"\bcosine\b",
    r"\bllm\b",
    r"\bchunks?\b",
    r"system prompt|the prompt|prompted",
    r"\bretriev(ed|al)\b",
    r"\bvector(s|store)?\b",
    r"\bindex",
    r"\bbackend\b",
    r"\bmodel\b",
    r"\bopenai\b",
    r"source:",  # '[Source: ...]' block labels from the context
    r"===",  # raw section markers
    r"^game:",  # raw document metadata lines
    r"^category:",
]


def leaks(text: str) -> list[str]:
    if not text.strip():
        return ["<empty answer>"]
    if text.strip() == FALLBACK_ANSWER:
        return []  # the fixed safe fallback is allowed verbatim
    lowered = text.lower()
    return [p for p in LEAK_PATTERNS if re.search(p, lowered, flags=re.MULTILINE)]


def main() -> int:
    rag = GameWikiRAG()
    live = os.getenv("LLM_PROVIDER", "openai").lower().strip() != "extractive"
    # Free LLM tiers rate-limit requests per minute — pace the live run.
    pace = float(os.getenv("TEST_QUESTION_DELAY", "8" if live else "0"))
    rows = []
    ok = True

    for index, (game, question, expected) in enumerate(QUESTIONS):
        if index and pace:
            time.sleep(pace)
        try:
            result = rag.ask(game, question)
        except Exception as exc:  # LLM errors etc. -> report as failure, keep going
            ok = False
            rows.append((False, game, question, f"ERROR: {exc}", None))
            continue
        files = [s.get("file") or "" for s in result.get("sources", [])]
        sections = [sec for s in result.get("sources", []) for sec in s.get("sections", [])]

        if expected == "FALLBACK":
            passed = result.get("found") is False and result.get("answer") == FALLBACK_ANSWER
            detail = "fallback returned"
        else:
            found_ok = result.get("found") is True
            src_ok = expected is None or any(expected in f for f in files)
            passed = found_ok and src_ok
            detail = f"files={files} sections={sections[:4]}"

        leaks_found = leaks(result.get("answer", ""))
        if leaks_found:
            passed = False
            detail += f"  LEAK:{leaks_found}"

        ok = ok and passed
        rows.append((passed, game, question, detail, result.get("top_score")))

    print("=" * 78)
    for passed, game, question, detail, score in rows:
        mark = "PASS" if passed else "FAIL"
        score_s = f"{score:.3f}" if isinstance(score, float) else "-"
        print(f"[{mark}] ({game}) {question}")
        print(f"        score={score_s}  {detail}")
    print("=" * 78)
    print("ALL PASS" if ok else "SOME TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
