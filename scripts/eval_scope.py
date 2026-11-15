"""Compare scope classifiers on the labeled set in ``eval/scope_labels.jsonl``.

Methods:
    keyword    The shipped keyword check (``topic_scope.is_question_in_scope``).
               Ignores conversation history.
    embedding  Cosine similarity between the query embedding and allowed-topic
               anchor descriptions, using the Ollama embedding model. For
               follow-ups, the previous user turn is prepended to the query.
    llm        A small Ollama chat model asked to answer IN or OUT, given the
               recent conversation history.

Usage:
    uv run python scripts/eval_scope.py --method keyword
    uv run python scripts/eval_scope.py --method all --embed-model all-minilm \
        --llm-model llama3.2:1b --thresholds 0.3,0.35,0.4,0.45,0.5

The embedding threshold is swept on the same labeled set. Treat the best value
as a starting point, and re-check it on a held-out set before changing the
serving threshold.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.guardrails import ANCHORS  # noqa: E402
from src.agents.topic_scope import is_question_in_scope  # noqa: E402

DEFAULT_LABELS = PROJECT_ROOT / "eval" / "scope_labels.jsonl"


LLM_SYSTEM_PROMPT = (
    "You classify user questions for a knowledge assistant that only answers "
    "questions about vector databases, vector search, embeddings, and "
    "retrieval augmented generation (RAG). Reply with exactly one word: IN if "
    "the latest user question is about those topics (including follow-ups that "
    "refer to earlier turns on those topics), or OUT otherwise."
)


@dataclass
class Example:
    id: str
    question: str
    history: list[dict]
    label: str  # "in" or "out"

    @property
    def is_followup(self) -> bool:
        return bool(self.history)

    def context_query(self) -> str:
        """Latest user turn plus the question, used for embedding."""
        prior_user = [t["content"] for t in self.history if t.get("role") == "user"]
        if prior_user:
            return f"{prior_user[-1]} {self.question}"
        return self.question


def load_examples(path: Path) -> list[Example]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                rows.append(
                    Example(
                        id=row["id"],
                        question=row["question"],
                        history=row.get("history", []),
                        label=row["label"],
                    )
                )
    return rows


def predict_keyword(example: Example) -> bool:
    return is_question_in_scope(example.question)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _embed_ollama(texts: list[str], model: str) -> list[list[float]]:
    import ollama

    embeddings: list[list[float]] = ollama.Client().embed(model=model, input=texts)["embeddings"]
    return embeddings


def _embed_bedrock(texts: list[str], model: str) -> list[list[float]]:
    """Embed with a Bedrock model, one request per text (Titan takes one input each)."""
    import json

    import boto3

    client = boto3.client("bedrock-runtime")
    vectors = []
    for text in texts:
        response = client.invoke_model(
            modelId=model,
            body=json.dumps({"inputText": text}),
            contentType="application/json",
            accept="application/json",
        )
        vectors.append(json.loads(response["body"].read())["embedding"])
    return vectors


def _bedrock_production_client():
    """The serverless embedding client (Titan, 768-dim PCA output), as used at runtime."""
    import os

    from src.config import Settings
    from src.tools.bedrock_client import BedrockClient

    os.environ["DEPLOYMENT_MODE"] = "serverless"
    return BedrockClient(Settings())


def _ollama_production_client():
    """The local embedding client (Ollama, configured embed model), as used at runtime."""
    from src.tools.ollama_client import OllamaClient

    return OllamaClient()


def _embed_with_production_client(client):
    def embed(texts: list[str], _model: str | None) -> list[list[float]]:
        return [client.embed_text(t) for t in texts]

    return embed


def build_embedding_scores(
    examples: list[Example], embed_model: str | None, backend: str = "ollama"
) -> dict[str, float]:
    """Return ``{example.id: max cosine similarity to any anchor}``."""
    if backend == "bedrock-client":
        embed = _embed_with_production_client(_bedrock_production_client())
        embed_model = None  # the client's configured embedding model
    elif backend == "ollama-client":
        embed = _embed_with_production_client(_ollama_production_client())
        embed_model = None
    elif backend == "bedrock":
        embed = _embed_bedrock
    else:
        embed = _embed_ollama
    anchor_vecs = embed(ANCHORS, embed_model)
    query_vecs = embed([e.context_query() for e in examples], embed_model)
    return {
        e.id: max(_cosine(q, a) for a in anchor_vecs)
        for e, q in zip(examples, query_vecs, strict=True)
    }


def predict_llm(example: Example, llm_model: str, client) -> bool:
    messages = [{"role": "system", "content": LLM_SYSTEM_PROMPT}]
    messages.extend({"role": t["role"], "content": t["content"]} for t in example.history[-4:])
    messages.append({"role": "user", "content": example.question})
    response = client.chat(
        model=llm_model,
        messages=messages,
        options={"temperature": 0, "num_predict": 4},
    )
    answer = (response["message"]["content"] or "").strip().upper()
    return answer.startswith("IN")


def score(examples: list[Example], predictions: dict[str, bool]) -> dict[str, float]:
    total = len(examples)
    correct = sum(predictions[e.id] == (e.label == "in") for e in examples)
    ins = [e for e in examples if e.label == "in"]
    outs = [e for e in examples if e.label == "out"]
    follow = [e for e in examples if e.is_followup]
    return {
        "accuracy": correct / total,
        "in_scope_allowed": sum(predictions[e.id] for e in ins) / len(ins),
        "out_of_scope_blocked": sum(not predictions[e.id] for e in outs) / len(outs),
        "followup_accuracy": (
            sum(predictions[e.id] == (e.label == "in") for e in follow) / len(follow)
            if follow
            else float("nan")
        ),
    }


def print_row(name: str, metrics: dict[str, float], ms_per_question: float | None = None) -> None:
    latency = f"  ms/q={ms_per_question:.1f}" if ms_per_question is not None else ""
    print(
        f"{name:<28} acc={metrics['accuracy']:.3f}  "
        f"in_allowed={metrics['in_scope_allowed']:.3f}  "
        f"out_blocked={metrics['out_of_scope_blocked']:.3f}  "
        f"followup_acc={metrics['followup_accuracy']:.3f}{latency}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--method", choices=["keyword", "embedding", "llm", "all"], default="all")
    parser.add_argument("--embed-model", default="all-minilm")
    parser.add_argument(
        "--embed-backend",
        choices=["ollama", "bedrock", "ollama-client", "bedrock-client"],
        default="ollama",
    )
    parser.add_argument("--llm-model", default="llama3.2:1b")
    parser.add_argument("--thresholds", default="0.3,0.35,0.4,0.45,0.5")
    args = parser.parse_args()

    examples = load_examples(args.labels)
    print(f"{len(examples)} labeled questions from {args.labels.name}")
    methods = ["keyword", "embedding", "llm"] if args.method == "all" else [args.method]

    if "keyword" in methods:
        print_row("keyword", score(examples, {e.id: predict_keyword(e) for e in examples}))

    if "embedding" in methods:
        started = time.perf_counter()
        scores = build_embedding_scores(examples, args.embed_model, args.embed_backend)
        elapsed_ms = (time.perf_counter() - started) * 1000 / len(examples)
        for raw in args.thresholds.split(","):
            threshold = float(raw)
            preds = {eid: s >= threshold for eid, s in scores.items()}
            print_row(
                f"emb {args.embed_backend} t={threshold:.2f}",
                score(examples, preds),
                elapsed_ms,
            )

    if "llm" in methods:
        import ollama

        client = ollama.Client()
        started = time.perf_counter()
        preds = {e.id: predict_llm(e, args.llm_model, client) for e in examples}
        elapsed_ms = (time.perf_counter() - started) * 1000 / len(examples)
        print_row(f"llm {args.llm_model}", score(examples, preds), elapsed_ms)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
