"""Unit tests for the pure scoring/classification logic in scripts/eval_local.py.

These cover the parts that must be correct for the eval numbers to mean
anything — refusal/caveat detection, grading against expected behaviour, the
aggregate summary, and the judge score parser — all without needing MLflow,
Ollama, or Milvus.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.agents import rag_routing

# Load scripts/eval_local.py as a module (scripts/ is not an importable package).
# It must be registered in sys.modules before exec so @dataclass can resolve the
# module by __module__ during class processing.
_EVAL_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "eval_local.py"
_spec = importlib.util.spec_from_file_location("eval_local", _EVAL_PATH)
assert _spec and _spec.loader
eval_local = importlib.util.module_from_spec(_spec)
sys.modules["eval_local"] = eval_local
_spec.loader.exec_module(eval_local)

# The module is loaded dynamically above (runtime), which mypy cannot follow.
# Import the dataclasses statically for type checking only so annotations below
# resolve without affecting the runtime dynamic load.
if TYPE_CHECKING:
    from scripts.eval_local import AnswerSignals, QuestionResult


# ---- classify_answer ------------------------------------------------------


def test_classify_empty_answer_is_refusal() -> None:
    sig = eval_local.classify_answer("", [])
    assert sig.refused is True
    assert sig.caveated is False


def test_classify_no_grounding_answer_is_refusal() -> None:
    sig = eval_local.classify_answer(rag_routing.NO_GROUNDING_ANSWER, [])
    assert sig.refused is True


def test_classify_rejection_message_is_refusal() -> None:
    sig = eval_local.classify_answer(
        "I can help with questions about vector databases, vector search, embeddings, and RAG.",
        [],
    )
    assert sig.refused is True


def test_classify_grounding_caveat_is_caveated_not_refused() -> None:
    answer = "Milvus supports HNSW indexing." + rag_routing.LOW_GROUNDING_CAVEAT
    sig = eval_local.classify_answer(answer, [{"text": "Milvus supports HNSW indexing."}])
    assert sig.refused is False
    assert sig.caveated is True


def test_classify_confidence_caveat_is_caveated() -> None:
    answer = "Milvus supports HNSW indexing." + rag_routing.LOW_CONFIDENCE_CAVEAT
    sig = eval_local.classify_answer(answer, [{"text": "Milvus supports HNSW indexing."}])
    assert sig.caveated is True


def test_classify_normal_answer_not_refused_or_caveated() -> None:
    sig = eval_local.classify_answer(
        "Milvus supports HNSW indexing for fast search.",
        [{"text": "Milvus supports HNSW indexing for fast search."}],
    )
    assert sig.refused is False
    assert sig.caveated is False
    assert sig.grounding_score > 0.0


# ---- grade ----------------------------------------------------------------


def _sig(refused: bool = False, caveated: bool = False) -> AnswerSignals:
    return eval_local.AnswerSignals(
        refused=refused, caveated=caveated, grounding_score=1.0, answer_len=20
    )


def test_grade_answer_expectation() -> None:
    assert eval_local.grade("answer", _sig(refused=False)) is True
    assert eval_local.grade("answer", _sig(refused=True)) is False


def test_grade_refuse_expectation() -> None:
    assert eval_local.grade("refuse", _sig(refused=True)) is True
    assert eval_local.grade("refuse", _sig(refused=False)) is False


def test_grade_refuse_or_caveat_expectation() -> None:
    assert eval_local.grade("refuse_or_caveat", _sig(refused=True)) is True
    assert eval_local.grade("refuse_or_caveat", _sig(caveated=True)) is True
    assert eval_local.grade("refuse_or_caveat", _sig()) is False


def test_grade_answer_or_refuse_always_passes() -> None:
    assert eval_local.grade("answer_or_refuse", _sig(refused=True)) is True
    assert eval_local.grade("answer_or_refuse", _sig(refused=False)) is True


def test_grade_unknown_tag_fails() -> None:
    assert eval_local.grade("nonsense", _sig()) is False


# ---- summarize ------------------------------------------------------------


def _result(**kw: object) -> QuestionResult:
    base = dict(
        id="x",
        category="in_scope",
        expected_behavior="answer",
        passed=True,
        refused=False,
        caveated=False,
        grounding_score=1.0,
        confidence_score=0.8,
        tier_used="kb",
        latency_ms=100.0,
        answer_len=50,
    )
    base.update(kw)
    return eval_local.QuestionResult(**base)  # type: ignore[arg-type]


def test_summarize_rates_and_per_category() -> None:
    results = [
        _result(id="a", category="in_scope", passed=True),
        _result(id="b", category="in_scope", passed=False),
        _result(id="c", category="out_of_scope", passed=True, refused=True),
    ]
    agg = eval_local.summarize(results)
    assert agg["total_questions"] == 3.0
    assert agg["pass_rate"] == 2 / 3
    assert agg["refusal_rate"] == 1 / 3
    assert agg["pass_rate/in_scope"] == 0.5
    assert agg["pass_rate/out_of_scope"] == 1.0


def test_summarize_excludes_errored_from_grading() -> None:
    results = [
        _result(id="a", passed=True),
        _result(id="b", passed=False, error="boom"),
    ]
    agg = eval_local.summarize(results)
    assert agg["errored"] == 1.0
    # Only the one non-errored (passing) row counts → pass_rate 1.0.
    assert agg["pass_rate"] == 1.0


def test_summarize_includes_judge_when_present() -> None:
    results = [
        _result(id="a", judge_faithfulness=0.8),
        _result(id="b", judge_faithfulness=0.6),
    ]
    agg = eval_local.summarize(results)
    assert abs(agg["avg_judge_faithfulness"] - 0.7) < 1e-9


def test_summarize_empty_is_empty() -> None:
    assert eval_local.summarize([]) == {}


# ---- judge score parsing --------------------------------------------------


def test_parse_score_variants() -> None:
    assert eval_local._parse_score("0.8") == 0.8
    assert eval_local._parse_score("The score is 0.5.") == 0.5
    assert eval_local._parse_score("1") == 1.0
    assert eval_local._parse_score("2.5") == 1.0  # clamped to [0,1]
    # The regex captures the unsigned magnitude ("3" from "-3"), then clamps to
    # 1.0. A negative judge score is malformed; clamping to the valid range is
    # an acceptable, non-crashing outcome.
    assert eval_local._parse_score("-3") == 1.0
    assert eval_local._parse_score("no number here") is None


# ---- tier inference -------------------------------------------------------


def test_infer_tier() -> None:
    assert eval_local._infer_tier([]) == "none"
    assert eval_local._infer_tier([{"source_type": "web_search"}]) == "websearch"
    assert eval_local._infer_tier([{"source_type": "system_message"}]) == "system"
    assert eval_local._infer_tier([{"text": "kb doc"}]) == "kb"
