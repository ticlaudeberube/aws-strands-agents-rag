#!/usr/bin/env python
"""Offline RAG evaluation harness for Local Mode, logged to MLflow.

Runs a fixed, tagged question set (``eval/questions.jsonl``) through the real
Local Mode pipeline (``LocalOpenSearchAgent``, Ollama + OpenSearch) and logs, per
question and in aggregate, the signals the pipeline already produces —
grounding score, confidence score, tier used, whether it refused, whether a
caveat fired, latency — plus a pass/fail against each question's
``expected_behavior``. An optional LLM judge adds a semantic faithfulness score.

This is a **dev-loop / CI tool**. It is intentionally isolated from the
runtime: ``mlflow`` lives in the ``eval`` optional-dependency group and is
imported lazily, and nothing here is importable from the serverless/Lambda path.

Usage
-----
    # Install the eval extra once:
    uv pip install -e '.[eval]'        # or: pip install -e '.[eval]'

    # Deterministic run (lexical metrics only — fast, no tokens):
    uv run scripts/eval_local.py

    # Add the LLM-as-judge faithfulness score (slower, uses Ollama):
    uv run scripts/eval_local.py --judge

    # Point at a custom question set / MLflow experiment:
    uv run scripts/eval_local.py --questions eval/questions.jsonl \
        --experiment rag-local-eval

Compare runs in the MLflow UI:
    mlflow ui            # then open http://127.0.0.1:5000

The behaviour classification and scoring are pure functions (``classify_answer``,
``grade``, ``summarize``) so they can be unit-tested without MLflow, Ollama, or
OpenSearch. See ``tests/unit/test_eval_local.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure the project root is importable when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.agents import rag_routing  # noqa: E402

logger = logging.getLogger("eval_local")

# Fixed rejection messages emitted by the graph's failure handlers. Matching
# against these (plus the shared refusal constant) lets the harness detect a
# refusal without the pipeline needing to return a structured flag.
_REJECTION_PREFIXES: tuple[str, ...] = (
    "I can help with questions about vector databases",
    "I detected a security concern",
    rag_routing.NO_GROUNDING_ANSWER[:40],
)


# ---------------------------------------------------------------------------
# Pure scoring / classification (unit-testable, no external deps)
# ---------------------------------------------------------------------------


@dataclass
class AnswerSignals:
    """Derived signals for a single answered question."""

    refused: bool
    caveated: bool
    grounding_score: float
    answer_len: int


def classify_answer(answer: str, sources: list[dict]) -> AnswerSignals:
    """Derive refusal / caveat / grounding signals from a pipeline answer.

    ``refused`` is ``True`` when the answer is empty or matches one of the
    pipeline's fixed refusal/rejection messages. ``caveated`` is ``True`` when
    either anti-hallucination caveat was appended. ``grounding_score`` reuses
    the shared lexical check so the harness and the pipeline agree.
    """
    text = (answer or "").strip()
    refused = not text or any(text.startswith(p) for p in _REJECTION_PREFIXES)
    caveated = (
        rag_routing.LOW_GROUNDING_CAVEAT in answer or rag_routing.LOW_CONFIDENCE_CAVEAT in answer
    )
    grounding = rag_routing.compute_grounding_score(answer, sources)
    return AnswerSignals(
        refused=refused,
        caveated=caveated,
        grounding_score=grounding,
        answer_len=len(text),
    )


def _confidence_from(sources: list[dict], answer: str) -> float:
    """Recompute the pipeline's heuristic confidence for an answer.

    Imported lazily from the agent module so the pure scoring functions above
    stay import-light; falls back to 0.0 if the import is unavailable.
    """
    try:
        from src.agents.strands_graph_agent import _calculate_confidence_score

        return float(_calculate_confidence_score(sources, answer))
    except Exception:  # noqa: BLE001 - confidence is a best-effort signal here
        return 0.0


def _infer_tier(sources: list[dict]) -> str:
    """Infer which retrieval tier produced the answer from the source shapes."""
    if not sources:
        return "none"
    if any((s.get("source_type") == "web_search") for s in sources if isinstance(s, dict)):
        return "websearch"
    if any((s.get("source_type") == "system_message") for s in sources if isinstance(s, dict)):
        return "system"
    return "kb"


def grade(expected_behavior: str, signals: AnswerSignals) -> bool:
    """Return whether the observed behaviour satisfies the expected tag.

    Tags:
    - ``answer``            → a substantive, non-refused answer.
    - ``refuse``            → an honest refusal / rejection.
    - ``refuse_or_caveat``  → either a refusal or an answer carrying a caveat
                              (acceptable for in-domain-but-unanswerable items).
    - ``answer_or_refuse``  → either is acceptable (e.g. competitor / temporal
                              items whose outcome depends on web-search
                              availability). Always passes; recorded for signal.
    """
    if expected_behavior == "answer":
        return not signals.refused
    if expected_behavior == "refuse":
        return signals.refused
    if expected_behavior == "refuse_or_caveat":
        return signals.refused or signals.caveated
    if expected_behavior == "answer_or_refuse":
        return True
    logger.warning("Unknown expected_behavior %r → counting as fail", expected_behavior)
    return False


@dataclass
class QuestionResult:
    """Per-question evaluation record."""

    id: str
    category: str
    expected_behavior: str
    passed: bool
    refused: bool
    caveated: bool
    grounding_score: float
    confidence_score: float
    tier_used: str
    latency_ms: float
    answer_len: int
    judge_faithfulness: float | None = None
    error: str | None = None


def summarize(results: list[QuestionResult]) -> dict[str, float]:
    """Compute aggregate metrics across all per-question results."""
    n = len(results)
    if n == 0:
        return {}
    graded = [r for r in results if r.error is None]
    m = len(graded) or 1
    agg: dict[str, float] = {
        "total_questions": float(n),
        "errored": float(n - len(graded)),
        "pass_rate": sum(1 for r in graded if r.passed) / m,
        "refusal_rate": sum(1 for r in graded if r.refused) / m,
        "caveat_rate": sum(1 for r in graded if r.caveated) / m,
        "avg_grounding_score": sum(r.grounding_score for r in graded) / m,
        "avg_confidence_score": sum(r.confidence_score for r in graded) / m,
        "avg_latency_ms": sum(r.latency_ms for r in graded) / m,
    }
    judged = [r.judge_faithfulness for r in graded if r.judge_faithfulness is not None]
    if judged:
        agg["avg_judge_faithfulness"] = sum(judged) / len(judged)
    # Per-category pass rate.
    cats = {r.category for r in graded}
    for cat in sorted(cats):
        rows = [r for r in graded if r.category == cat]
        agg[f"pass_rate/{cat}"] = sum(1 for r in rows if r.passed) / len(rows)
    return agg


# ---------------------------------------------------------------------------
# LLM judge (optional)
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """You are a strict evaluator of a retrieval-augmented answer.

Given the QUESTION, the retrieved CONTEXT, and the ANSWER, rate how faithful the
answer is to the context on a scale of 0.0 to 1.0, where:
- 1.0 = every claim in the answer is directly supported by the context
- 0.5 = partially supported; some claims are not in the context
- 0.0 = the answer makes claims absent from or contradicted by the context

An honest refusal ("I don't have information about that...") when the context is
empty or irrelevant should score 1.0 (it is faithful — it does not fabricate).

Respond with ONLY a single number between 0.0 and 1.0.

QUESTION:
{question}

CONTEXT:
{context}

ANSWER:
{answer}

Faithfulness score (0.0-1.0):"""


def judge_faithfulness(
    ollama_client: Any, model: str, question: str, answer: str, sources: list[dict]
) -> float | None:
    """Return an LLM faithfulness score in [0,1], or ``None`` on any failure.

    Deliberately best-effort: the judge must never break an eval run, so any
    exception or unparseable response yields ``None`` (excluded from the mean).
    """
    context = (
        "\n".join(str(s.get("text") or s.get("snippet") or "") for s in sources).strip()
        or "(no context retrieved)"
    )
    prompt = _JUDGE_PROMPT.format(question=question, context=context[:4000], answer=answer)
    try:
        raw = ollama_client.generate(prompt=prompt, model=model, temperature=0.0)
        return _parse_score(str(raw))
    except Exception as exc:  # noqa: BLE001 - judge is best-effort
        logger.warning("Judge call failed for %r: %s", question[:40], exc)
        return None


def _parse_score(raw: str) -> float | None:
    """Extract the first float in [0,1] from the judge's raw response."""
    import re

    match = re.search(r"\d*\.?\d+", raw)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class EvalConfig:
    questions_path: Path
    experiment: str
    run_name: str | None
    use_judge: bool
    judge_model: str | None
    top_k: int
    tracking_uri: str | None = None
    search_ef: int | None = None
    _extra: dict = field(default_factory=dict)


def load_questions(path: Path) -> list[dict]:
    """Load the JSONL question set, skipping blank lines."""
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


async def _answer_with_trace(agent: Any, question: str, top_k: int) -> tuple[str, list[dict]]:
    """Call the agent, wrapping it in an MLflow GenAI trace span.

    Emitting a span makes each question show up under the experiment's
    **Traces** tab (the ``workflowType=genai`` view), not just as run
    metrics. Tracing is best-effort: if MLflow or the span API is unavailable
    we fall back to a plain call so the eval still runs.
    """
    import mlflow  # type: ignore[import-not-found]  # lazy: eval-extra only

    answer: str
    sources: list[dict]

    try:
        span_cm = mlflow.start_span(name="answer_question", span_type="AGENT")
    except Exception:  # noqa: BLE001 - tracing must never break the eval
        answer, sources = await agent.answer_question_no_cache(question=question, top_k=top_k)
        return answer, sources

    with span_cm as span:
        span.set_inputs({"question": question, "top_k": top_k})
        answer, sources = await agent.answer_question_no_cache(question=question, top_k=top_k)
        span.set_outputs({"answer": answer, "num_sources": len(sources)})
        return answer, sources


async def _run_one(agent: Any, item: dict, cfg: EvalConfig, judge_client: Any) -> QuestionResult:
    """Run a single question through the local agent and build its record."""
    question = item["question"]
    start = time.time()
    confidence = 0.0
    tier = "unknown"
    error: str | None = None
    answer: str = ""
    sources: list[dict] = []
    try:
        answer, sources = await _answer_with_trace(agent, question, cfg.top_k)
        # answer_question returns (answer, sources) only, so recompute the same
        # confidence heuristic the pipeline uses and infer the tier from source
        # types (web results carry source_type="web_search").
        confidence = _confidence_from(sources, answer)
        tier = _infer_tier(sources)
    except Exception as exc:  # noqa: BLE001 - record and continue
        error = f"{type(exc).__name__}: {exc}"
        logger.error("Question %s failed: %s", item.get("id"), error)

    latency_ms = (time.time() - start) * 1000
    signals = classify_answer(answer, sources)
    passed = error is None and grade(item["expected_behavior"], signals)

    judge_score: float | None = None
    if cfg.use_judge and error is None and judge_client is not None:
        judge_score = judge_faithfulness(
            judge_client, cfg.judge_model or "", question, answer, sources
        )

    return QuestionResult(
        id=str(item.get("id", "")),
        category=str(item.get("category", "uncategorized")),
        expected_behavior=str(item.get("expected_behavior", "")),
        passed=passed,
        refused=signals.refused,
        caveated=signals.caveated,
        grounding_score=signals.grounding_score,
        confidence_score=confidence,
        tier_used=tier,
        latency_ms=latency_ms,
        answer_len=signals.answer_len,
        judge_faithfulness=judge_score,
        error=error,
    )


def _build_agent(settings: Any) -> Any:
    """Construct the Local Mode agent, raising a clear error if deps are missing."""
    from src.agents.local_opensearch_agent import LocalOpenSearchAgent

    return LocalOpenSearchAgent(settings)


def _resolve_tracking_uri(cfg_uri: str | None) -> str | None:
    """Resolve the MLflow tracking URI: --tracking-uri → env var → default.

    Returns ``None`` to mean "MLflow's default" (the local ``./mlruns`` file
    store). An explicit flag wins; otherwise ``MLFLOW_TRACKING_URI`` is honored
    (which MLflow would read anyway, but resolving it here lets us log it). This
    is how you point the harness at a running tracking server, e.g.
    ``--tracking-uri http://127.0.0.1:5000`` or ``export
    MLFLOW_TRACKING_URI=http://127.0.0.1:5000``.
    """
    if cfg_uri:
        return cfg_uri
    return os.environ.get("MLFLOW_TRACKING_URI") or None


async def run_eval(cfg: EvalConfig) -> dict[str, float]:
    """Execute the full eval, log to MLflow, and return the aggregate metrics."""
    import mlflow  # type: ignore[import-not-found]  # lazy: eval-extra only

    from src.config.settings import Settings

    # Load .env so MLFLOW_TRACKING_URI (and any other config) is available to
    # _resolve_tracking_uri below, regardless of import ordering elsewhere.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # python-dotenv is a runtime dep, but stay defensive
        pass

    settings = Settings()
    # Override the HNSW search-time beam width for this run when sweeping ef.
    # Read at search time by the vector store, so setting it before the agent is
    # built applies to every retrieval in the run.
    if cfg.search_ef is not None:
        settings.vectordb_search_ef = cfg.search_ef
    items = load_questions(cfg.questions_path)
    logger.info("Loaded %d questions from %s", len(items), cfg.questions_path)

    agent = _build_agent(settings)
    judge_client = agent.ollama_client if cfg.use_judge else None
    judge_model = cfg.judge_model or getattr(settings, "ollama_model", None)
    cfg.judge_model = judge_model

    # A judge no stronger than the generator cannot meaningfully grade it (the
    # thing being graded should not also be the grader). Warn when the judge is
    # enabled but falls back to the pipeline's own generation model, and point
    # the operator at a larger model via --judge-model.
    if cfg.use_judge and judge_model == getattr(settings, "ollama_model", None):
        logger.warning(
            "LLM judge is using the pipeline's generation model (%s); scores will be "
            "weak. Pass a larger model, e.g. --judge-model llama3.1:8b, for a "
            "meaningful faithfulness grade.",
            judge_model,
        )

    tracking_uri = _resolve_tracking_uri(cfg.tracking_uri)
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    logger.info("MLflow tracking store: %s", mlflow.get_tracking_uri())
    mlflow.set_experiment(cfg.experiment)

    results: list[QuestionResult] = []
    with mlflow.start_run(run_name=cfg.run_name):
        # Log the config that defines this run so runs are comparable.
        mlflow.log_params(
            {
                "questions": cfg.questions_path.name,
                "num_questions": len(items),
                "use_judge": cfg.use_judge,
                "judge_model": judge_model if cfg.use_judge else "none",
                "top_k": cfg.top_k,
                "vectordb_search_ef": settings.vectordb_search_ef,
                "grounding_threshold": settings.answer_grounding_threshold,
                "confidence_threshold": settings.answer_confidence_threshold,
                "web_fallback_threshold": settings.web_search_fallback_threshold,
                "ollama_model": getattr(settings, "ollama_model", "unknown"),
            }
        )

        for item in items:
            res = await _run_one(agent, item, cfg, judge_client)
            results.append(res)
            # Per-question metric (step-indexed) for drill-down in the UI.
            mlflow.log_metric("passed", 1.0 if res.passed else 0.0, step=len(results))
            logger.info(
                "[%s] %s pass=%s refused=%s caveat=%s ground=%.2f%s",
                res.category,
                res.id,
                res.passed,
                res.refused,
                res.caveated,
                res.grounding_score,
                (
                    f" judge={res.judge_faithfulness:.2f}"
                    if res.judge_faithfulness is not None
                    else ""
                ),
            )

        agg = summarize(results)
        mlflow.log_metrics(agg)

        # Attach the full per-question table as an artifact for auditing.
        table = [r.__dict__ for r in results]
        mlflow.log_dict({"results": table}, "results.json")

    _print_summary(agg, results)
    return agg


def _print_summary(agg: dict[str, float], results: list[QuestionResult]) -> None:
    """Human-readable console summary."""
    print("\n" + "=" * 68)
    print("RAG LOCAL EVAL SUMMARY")
    print("=" * 68)
    for key in sorted(agg):
        print(f"  {key:28} {agg[key]:.3f}")
    failed = [r for r in results if r.error is None and not r.passed]
    if failed:
        print("\nFailed questions:")
        for r in failed:
            print(
                f"  - [{r.category}] {r.id} (expected {r.expected_behavior}, "
                f"refused={r.refused}, caveat={r.caveated})"
            )
    errored = [r for r in results if r.error is not None]
    if errored:
        print("\nErrored questions:")
        for r in errored:
            print(f"  - {r.id}: {r.error}")
    print("=" * 68 + "\n")


def _parse_args(argv: list[str] | None = None) -> EvalConfig:
    parser = argparse.ArgumentParser(description="Offline RAG eval harness (Local Mode → MLflow).")
    parser.add_argument(
        "--questions",
        type=Path,
        default=_PROJECT_ROOT / "eval" / "questions.jsonl",
        help="Path to the JSONL question set.",
    )
    parser.add_argument("--experiment", default="rag-local-eval", help="MLflow experiment name.")
    parser.add_argument("--run-name", default=None, help="Optional MLflow run name.")
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Enable the optional LLM-as-judge faithfulness score (slower, uses Ollama).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Model id for the judge (defaults to settings.ollama_model). For a "
            "meaningful grade, pass a model larger than the pipeline's generation "
            "model, e.g. llama3.1:8b."
        ),
    )
    parser.add_argument("--top-k", type=int, default=5, help="Retrieval top-k per question.")
    parser.add_argument(
        "--sweep-ef",
        default=None,
        help=(
            "Comma-separated HNSW search ef values to sweep (e.g. '32,64,128,256'). "
            "Runs one MLflow run per value so you can compare the recall-vs-latency "
            "tradeoff for your corpus. Omit for a single run at the configured ef. "
            "Note: avg_latency_ms is end-to-end (embedding + retrieval + generation), "
            "so it only partially reflects the retrieval slice ef actually affects."
        ),
    )
    parser.add_argument(
        "--tracking-uri",
        default=None,
        help=(
            "MLflow tracking URI. Resolution order: this flag → MLFLOW_TRACKING_URI "
            "env var → local ./mlruns. Point at a running server with e.g. "
            "http://127.0.0.1:5000, or a file store with sqlite:///mlflow.db."
        ),
    )
    args = parser.parse_args(argv)

    sweep_ef: list[int] = []
    if args.sweep_ef:
        try:
            sweep_ef = [int(v.strip()) for v in args.sweep_ef.split(",") if v.strip()]
        except ValueError as exc:
            parser.error(f"--sweep-ef must be a comma-separated list of integers: {exc}")
        if any(v < 1 for v in sweep_ef):
            parser.error("--sweep-ef values must be positive integers.")

    return EvalConfig(
        questions_path=args.questions,
        experiment=args.experiment,
        run_name=args.run_name,
        use_judge=args.judge,
        judge_model=args.judge_model,
        top_k=args.top_k,
        tracking_uri=args.tracking_uri,
        _extra={"sweep_ef": sweep_ef},
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = _parse_args(argv)
    if not cfg.questions_path.exists():
        print(f"Question set not found: {cfg.questions_path}", file=sys.stderr)
        return 2
    sweep_ef: list[int] = cfg._extra.get("sweep_ef", [])
    try:
        if sweep_ef:
            _run_ef_sweep(cfg, sweep_ef)
        else:
            asyncio.run(run_eval(cfg))
    except ModuleNotFoundError as exc:
        if exc.name == "mlflow":
            print(
                "mlflow is not installed. Install the eval extra:\n"
                "  uv pip install -e '.[eval]'   (or: pip install -e '.[eval]')",
                file=sys.stderr,
            )
            return 2
        raise
    return 0


def _run_ef_sweep(base_cfg: EvalConfig, ef_values: list[int]) -> None:
    """Run the eval once per HNSW ``ef`` value and print a comparison table.

    Each value is a separate MLflow run (tagged via the ``vectordb_search_ef``
    param), so the recall-vs-latency tradeoff is comparable side-by-side in the
    UI. The per-run config is a shallow copy of ``base_cfg`` with ``search_ef``
    and a descriptive ``run_name`` set.
    """
    print(f"\nSweeping HNSW search ef over {ef_values} ({len(ef_values)} runs)\n")
    rows: list[tuple[int, dict[str, float]]] = []
    for ef in ef_values:
        run_cfg = EvalConfig(
            questions_path=base_cfg.questions_path,
            experiment=base_cfg.experiment,
            run_name=(base_cfg.run_name or "ef-sweep") + f"-ef{ef}",
            use_judge=base_cfg.use_judge,
            judge_model=base_cfg.judge_model,
            top_k=base_cfg.top_k,
            tracking_uri=base_cfg.tracking_uri,
            search_ef=ef,
        )
        agg = asyncio.run(run_eval(run_cfg))
        rows.append((ef, agg))

    # Compact comparison across the sweep (recall proxies + end-to-end latency).
    print("\n" + "=" * 68)
    print("EF SWEEP COMPARISON (higher pass/grounding = better recall)")
    print("=" * 68)
    header = f"  {'ef':>5}  {'pass_rate':>10}  {'avg_grounding':>14}  {'avg_latency_ms':>15}"
    print(header)
    for ef, agg in rows:
        print(
            f"  {ef:>5}  {agg.get('pass_rate', 0.0):>10.3f}  "
            f"{agg.get('avg_grounding_score', 0.0):>14.3f}  "
            f"{agg.get('avg_latency_ms', 0.0):>15.1f}"
        )
    print(
        "\nNote: avg_latency_ms is end-to-end (embedding + retrieval + generation).\n"
        "ef only affects the retrieval slice, so expect small latency movement\n"
        "at this corpus size — a flat curve means the vector index is not your\n"
        "bottleneck.\n" + "=" * 68 + "\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
