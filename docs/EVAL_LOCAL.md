# Local RAG evaluation harness (MLflow)

`scripts/eval_local.py` runs a fixed, tagged question set through the **Local
Mode** pipeline (Ollama + Milvus) and logs the anti-hallucination signals the
pipeline already produces to [MLflow](https://mlflow.org/), so you can measure
whether a change (e.g. tuning a threshold or a prompt) made the system better or
worse — instead of guessing.

It is a **dev-loop / CI tool only**. `mlflow` lives in the `eval` optional
dependency group and is imported lazily; nothing here is importable from the
runtime/serverless path.

## What it measures

Per question and in aggregate:

- **pass_rate** — fraction of questions whose behaviour matched their
  `expected_behavior` tag (overall and per category).
- **refusal_rate** — fraction that returned an honest refusal.
- **caveat_rate** — fraction whose answer carried a grounding/confidence caveat.
- **avg_grounding_score** — the shared lexical grounding score.
- **avg_confidence_score** — the pipeline's heuristic confidence.
- **avg_latency_ms**.
- **avg_judge_faithfulness** — only when `--judge` is used (see below).

The thresholds in effect (`answer_grounding_threshold`,
`answer_confidence_threshold`, `web_search_fallback_threshold`) and the model id
are logged as run **params**, so two runs with different settings are directly
comparable in the MLflow UI. The full per-question table is attached to each run
as `results.json`.

## Prerequisites

- Local Mode backends running: Ollama and Milvus (see `docs/GETTING_STARTED.md`).
  If Milvus/Ollama are unreachable the run will record per-question errors
  rather than silently passing.
- The `eval` extra installed:

  ```bash
  uv pip install -e '.[eval]'     # or: pip install -e '.[eval]'
  ```

  This pulls in MLflow. The project pins `mlflow>=3.0,<4` (in the `eval` extra
  of `pyproject.toml`), so the harness and the UI run on MLflow 3.x. Keep the
  pin bounded to one major: an MLflow-3 store cannot be read by MLflow 2 and
  vice-versa, so an unbounded range makes CI non-reproducible and can leave a
  store the other major refuses to open.

## MLflow stores: pick one and stay consistent

MLflow runs are written to a **tracking store**, and the eval script and the UI
must point at the **same** store or the UI will show no runs. Two stores are in
play in this repo:

- **File store (`./mlruns`)** — the eval script's default when `--tracking-uri`
  is omitted. Simplest for a quick local loop.
- **SQLite store (`sqlite:///mlflow.db`)** — a single `mlflow.db` file in the
  project root. Preferred when you want the richer MLflow-3 server features and
  a single-file store that's easy to reset (just delete `mlflow.db`).

Whichever you choose, use it for **both** the eval run (`--tracking-uri`) and
the UI (`--backend-store-uri`). Mixing them is the most common reason runs
"disappear."

## Running the evaluation

```bash
# Deterministic run — lexical metrics only (fast, no extra tokens):
uv run scripts/eval_local.py

# Add the optional LLM-as-judge faithfulness score (slower, uses Ollama):
uv run scripts/eval_local.py --judge

# Custom question set / experiment name / run label:
uv run scripts/eval_local.py --questions eval/questions.jsonl \
    --experiment my-eval --run-name baseline

# Log into the SQLite store (so the SQLite-backed UI shows it):
uv run scripts/eval_local.py --tracking-uri sqlite:///mlflow.db
```

Flags:

| Flag             | Default               | Purpose                                              |
|------------------|-----------------------|------------------------------------------------------|
| `--questions`    | `eval/questions.jsonl`| Path to the JSONL question set.                      |
| `--experiment`   | `rag-local-eval`      | MLflow experiment name.                              |
| `--run-name`     | auto                  | Label the run so it's easy to find in the UI.        |
| `--judge`        | off                   | Add the LLM-as-judge faithfulness score (uses Ollama)|
| `--judge-model`  | `settings.ollama_model`| Override the judge model.                           |
| `--top-k`        | `5`                   | Retrieval depth per question.                        |
| `--tracking-uri` | `./mlruns`            | Where to log — match the UI's `--backend-store-uri`. |

Exit codes: `0` on success, `2` if the question file is missing or the `eval`
extra (mlflow) is not installed.

## Browsing runs in the MLflow UI

Always launch via `uv run` so the project venv is used, and match the backend
store to whatever the eval run wrote to:

```bash
# File store (pairs with a plain `uv run scripts/eval_local.py`):
uv run mlflow ui

# SQLite store (pairs with `--tracking-uri sqlite:///mlflow.db`):
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db
```

The server is long-running and blocks the terminal — start it in its own
terminal and stop it with Ctrl-C. It is ready once it logs
`Listening at: http://127.0.0.1:5000`. Earlier startup lines about security
middleware and the job executor backend (`online_scoring_scheduler`,
`trace_archival_scheduler`, etc.) are normal MLflow-3 messages, not errors.

In the UI (`http://127.0.0.1:<port>`):

1. Select the experiment (`rag-local-eval`) in the left sidebar.
2. Each eval invocation is one **run** row — columns show the logged metrics
   (pass_rate, refusal_rate, caveat_rate, avg_grounding_score, …) and params
   (thresholds, model id, top_k).
3. Select two or more runs and **Compare** to see how a change moved the numbers.
4. Open a run → **Artifacts** → `results.json` for the full per-question table.

## Troubleshooting

| Symptom                                   | Cause / fix                                                                                     |
|-------------------------------------------|-------------------------------------------------------------------------------------------------|
| `[Errno 48] Address already in use`       | Port 5000 is taken — on macOS usually the AirPlay Receiver (Control Center). Use another port: `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5001`, or disable System Settings → General → AirDrop & Handoff → AirPlay Receiver. |
| UI opens but shows no runs                | UI and eval pointed at different stores. Point both at the same place (`./mlruns` **or** `sqlite:///mlflow.db`). |
| `mlflow is not installed`                 | Install the eval extra: `uv pip install -e '.[eval]'`.                                           |
| DB/schema or alembic revision error on UI start | The `mlflow.db` was created by a different MLflow major. Stay on the pinned 3.x, or archive/delete `mlflow.db` to start fresh (loses prior runs). |
| `Errored questions` in the summary        | Ollama/Milvus unreachable. Start Local Mode backends (see `docs/GETTING_STARTED.md`).           |

## Typical dev loop

```bash
# 1. Start Local Mode backends (Ollama + Milvus) — see GETTING_STARTED.md
# 2. Baseline:
uv run scripts/eval_local.py --tracking-uri sqlite:///mlflow.db --run-name before
# 3. Change a threshold in src/config/settings.py or a prompt.
# 4. New run:
uv run scripts/eval_local.py --tracking-uri sqlite:///mlflow.db --run-name after
# 5. Compare before vs after:
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5001
```

## The question set

`eval/questions.jsonl` — one JSON object per line:

```json
{"id": "in-scope-001", "question": "What is Milvus?", "category": "in_scope", "expected_behavior": "answer", "notes": "..."}
```

`expected_behavior` tags and how they are graded:

| tag                | passes when                                            |
|--------------------|--------------------------------------------------------|
| `answer`           | a substantive, non-refused answer is returned          |
| `refuse`           | an honest refusal / rejection is returned              |
| `refuse_or_caveat` | the answer is refused **or** carries a caveat          |
| `answer_or_refuse` | either outcome is acceptable (always passes)           |

`answer_or_refuse` is for questions whose correct outcome depends on
web-search availability (competitor / time-sensitive). It always passes but the
refusal/caveat/tier signals are still recorded so you can see what happened.

Categories: `in_scope`, `out_of_scope`, `competitor`, `time_sensitive`,
`unanswerable`. The out-of-scope set includes deliberate regression guards for
the substring-matching fixes (e.g. "renew", "storage", "dragon").

**Curate this set.** The starter questions are a reasonable baseline, but the
numbers are only as meaningful as the questions. Add items that reflect real
usage and known failure modes.

## The LLM judge (`--judge`)

Off by default. When enabled, each answer is scored for faithfulness to its
retrieved context (0.0–1.0) by the configured Ollama model. It is the semantic
counterpart to the cheap lexical grounding score. The judge is best-effort: any
failure or unparseable response yields no score for that question (excluded from
the mean) and never breaks the run. Keep deterministic (no-judge) runs for CI
gates; use `--judge` for periodic deeper reads.

## Interpreting results

- A drop in `pass_rate/out_of_scope` after a change means the topic gate got
  looser (more off-topic leakage).
- A rise in `refusal_rate` on `in_scope` questions means retrieval or the
  grounding threshold is too aggressive.
- `avg_grounding_score` vs `avg_judge_faithfulness` divergence indicates the
  lexical check is mis-estimating (usually heavy paraphrasing) — useful when
  deciding whether to raise/lower `answer_grounding_threshold`.
