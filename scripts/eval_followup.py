"""Measure follow-up retrieval across query strategies.

For each case in ``eval/followup_pairs.jsonl`` the script runs the KB search once
per strategy and records a hit when a returned chunk contains one of the case's
expected terms (case-insensitive). Strategies:

- ``raw``: the question alone.
- ``join_last_turn``: the last user question joined to the question (one hop).
- ``join_recent_turns``: the last user questions joined, as used by the router
  (``FOLLOWUP_USER_TURNS``).

Hit rates are reported for follow-ups, follow-ups with two or more prior user
turns (``follow_up_multi``), and topic switches.

    uv run python scripts/eval_followup.py
    uv run python scripts/eval_followup.py --json

Requires Ollama (embedding model) and the local OpenSearch KB.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.history import (  # noqa: E402
    FALLBACK_USER_TURNS,
    normalize_turns,
    retrieval_text,
)

DEFAULT_PAIRS = PROJECT_ROOT / "eval" / "followup_pairs.jsonl"
DEFAULT_TOP_K = 5
FOLLOW_UP = "follow_up"
TOPIC_SWITCH = "topic_switch"
FOLLOW_UP_MULTI = "follow_up_multi"
MULTI_HOP_MIN_USER_TURNS = 2

RAW = "raw"
JOIN_LAST_TURN = "join_last_turn"
JOIN_RECENT_TURNS = "join_recent_turns"
STRATEGIES = (RAW, JOIN_LAST_TURN, JOIN_RECENT_TURNS)


@dataclass(frozen=True)
class Pair:
    """One labeled conversation step."""

    id: str
    category: str
    history: list[dict[str, str]]
    question: str
    expected_terms: list[str]


def load_pairs(path: Path) -> list[Pair]:
    """Read labeled cases from a JSONL file, skipping blank lines."""
    pairs: list[Pair] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pairs.append(
                Pair(
                    id=row["id"],
                    category=row["category"],
                    history=row.get("history", []),
                    question=row["question"],
                    expected_terms=row["expected_terms"],
                )
            )
    return pairs


def retrieval_query(pair: Pair, joined: bool) -> str:
    """Return the search text for a case, with or without the prior-turn join."""
    if joined:
        return retrieval_text(pair.question, pair.history)
    return pair.question


def is_hit(chunk_texts: list[str], expected_terms: list[str]) -> bool:
    """Return True when any chunk contains any expected term (case-insensitive)."""
    lowered_chunks = [text.lower() for text in chunk_texts]
    return any(term.lower() in chunk for term in expected_terms for chunk in lowered_chunks)


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Return per-category hit rates for the raw and joined search text."""
    summary: dict[str, dict[str, float]] = {}
    for category in (FOLLOW_UP, TOPIC_SWITCH):
        subset = [row for row in rows if row["category"] == category]
        if not subset:
            continue
        count = len(subset)
        summary[category] = {
            "cases": float(count),
            "raw_hit_rate": sum(row["raw_hit"] for row in subset) / count,
            "joined_hit_rate": sum(row["joined_hit"] for row in subset) / count,
        }
    return summary


def decide(summary: dict[str, dict[str, float]]) -> str:
    """Return the keep/revise decision for the join from the summary."""
    follow_up = summary.get(FOLLOW_UP)
    switch = summary.get(TOPIC_SWITCH)
    if follow_up is None or switch is None:
        return "insufficient data: both categories are required"
    improves = follow_up["joined_hit_rate"] > follow_up["raw_hit_rate"]
    keeps_switches = switch["joined_hit_rate"] >= switch["raw_hit_rate"]
    if improves and keeps_switches:
        return "keep join: improves follow-ups without lowering topic-switch hits"
    return "revise join: restrict it to short or pronoun-containing questions"


def evaluate(pairs: list[Pair], search: Any, top_k: int, index: str) -> list[dict[str, Any]]:
    """Run raw and joined searches for every case and record the hits.

    ``search`` is a callable ``(text, top_k, index) -> list[str]`` that embeds
    the text and returns the chunk texts from the KB.
    """
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        raw_text = retrieval_query(pair, joined=False)
        joined_text = retrieval_query(pair, joined=True)
        raw_chunks = search(raw_text, top_k, index)
        joined_chunks = search(joined_text, top_k, index)
        rows.append(
            {
                "id": pair.id,
                "category": pair.category,
                "raw_query": raw_text,
                "joined_query": joined_text,
                "raw_hit": is_hit(raw_chunks, pair.expected_terms),
                "joined_hit": is_hit(joined_chunks, pair.expected_terms),
            }
        )
    return rows


def prior_user_turns(pair: Pair) -> int:
    """Return how many user turns precede the current question."""
    return sum(1 for role, _ in normalize_turns(pair.history) if role == "user")


def strategy_query(
    pair: Pair,
    strategy: str,
    join_turns: int = FALLBACK_USER_TURNS,
) -> str:
    """Return the search text for one strategy.

    ``join_turns`` is the number of recent user questions in the ``join_recent_turns``
    strategy (the router's ``FOLLOWUP_USER_TURNS``).
    """
    if strategy == RAW:
        return pair.question
    if strategy == JOIN_LAST_TURN:
        return retrieval_text(pair.question, pair.history, turns=1)
    if strategy == JOIN_RECENT_TURNS:
        return retrieval_text(pair.question, pair.history, turns=join_turns)
    raise ValueError(f"unknown strategy: {strategy}")


def evaluate_strategies(
    pairs: list[Pair],
    search: Callable[[str, int, str], list[str]],
    top_k: int,
    index: str,
    join_turns: int = FALLBACK_USER_TURNS,
) -> list[dict[str, Any]]:
    """Run every strategy for every case and record hits and the query text used."""
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        row: dict[str, Any] = {
            "id": pair.id,
            "category": pair.category,
            "prior_user_turns": prior_user_turns(pair),
        }
        for strategy in STRATEGIES:
            text = strategy_query(pair, strategy, join_turns)
            row[f"{strategy}_query"] = text
            row[f"{strategy}_hit"] = is_hit(search(text, top_k, index), pair.expected_terms)
        rows.append(row)
    return rows


def _bucket(row: dict[str, Any]) -> str:
    """Group a row into follow-up, multi-hop follow-up, or topic-switch."""
    if row["category"] == FOLLOW_UP and row["prior_user_turns"] >= MULTI_HOP_MIN_USER_TURNS:
        return FOLLOW_UP_MULTI
    return str(row["category"])


def summarize_strategies(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Return case counts and hit rate per strategy for each bucket."""
    summary: dict[str, dict[str, float]] = {}
    for bucket in (FOLLOW_UP, FOLLOW_UP_MULTI, TOPIC_SWITCH):
        subset = [row for row in rows if _bucket(row) == bucket]
        if not subset:
            continue
        count = len(subset)
        stats: dict[str, float] = {"cases": float(count)}
        for strategy in STRATEGIES:
            stats[f"{strategy}_hit_rate"] = sum(row[f"{strategy}_hit"] for row in subset) / count
        summary[bucket] = stats
    return summary


def _print_table(rows: list[dict[str, Any]], summary: dict[str, dict[str, float]]) -> None:
    header = f"{'id':8} {'bucket':16} " + " ".join(f"{s:>18}" for s in STRATEGIES)
    print(header)
    for row in rows:
        cells = " ".join(f"{str(row[f'{s}_hit']):>18}" for s in STRATEGIES)
        print(f"{row['id']:8} {_bucket(row):16} {cells}")
    print()
    for bucket, stats in summary.items():
        rates = ", ".join(f"{s} {stats[f'{s}_hit_rate']:.2%}" for s in STRATEGIES)
        print(f"{bucket}: {int(stats['cases'])} cases, {rates}")


def _build_search() -> Callable[[str, int, str], list[str]]:
    """Create the live embedding and KB search callable from project settings."""
    from src.config.settings import get_settings
    from src.tools.ollama_client import OllamaClient
    from src.tools.opensearch_client import OpenSearchClient

    settings = get_settings()
    ollama = OllamaClient(host=settings.ollama_host)
    opensearch = OpenSearchClient.for_local(settings)

    def search(text: str, top_k: int, index: str) -> list[str]:
        vector = ollama.embed_text(text)
        sources = opensearch.knn_search(index, vector, top_k, query_text=text)
        return [str(source.get("text", "")) for source in sources]

    return search


def main(argv: list[str] | None = None) -> int:
    """Run the follow-up retrieval eval and print the table or JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--index", type=str, default=None)
    parser.add_argument(
        "--join-turns",
        type=int,
        default=None,
        help="User questions joined in join_recent_turns (default: FOLLOWUP_USER_TURNS)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args(argv)

    from src.config.settings import get_settings

    settings = get_settings()
    index = args.index or settings.opensearch_kb_index
    join_turns = args.join_turns or settings.followup_user_turns
    pairs = load_pairs(args.pairs)
    rows = evaluate_strategies(
        pairs,
        _build_search(),
        args.top_k,
        index,
        join_turns,
    )
    summary = summarize_strategies(rows)

    if args.json:
        print(
            json.dumps(
                {"rows": rows, "summary": summary},
                indent=2,
            )
        )
    else:
        _print_table(rows, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
