# Local RAG evaluation harness (MLflow)

`scripts/eval_local.py` runs a fixed, tagged question set through the **Local
Mode** pipeline (Ollama + OpenSearch) and logs the anti-hallucination signals the
pipeline already produces to [MLflow](https://mlflow.org/), so you can measure
whether a change (e.g. tuning a threshold or a prompt) made the system better or
worse — instead of guessing.

It is a **dev-loop / CI tool only**. `mlflow` lives in the `eval` optional
dependency group and is imported lazily; nothing here is importable from the
runtime/serverless path.

## Quick reference (recommended setup)

The project is configured so the eval logs **runs and GenAI traces to a local
MLflow server by default** — no flags needed.

1. **One-time:** `.env` sets the tracking target (copied from `.env.example`):

   ```bash
   MLFLOW_TRACKING_URI=http://127.0.0.1:5000
   ```

   The harness loads `.env` automatically. Comment this line out to fall back to
   the local `./mlruns` file store instead.

2. **Start the MLflow server** (serves the UI at the same address). Port 5000
   collides with macOS AirPlay Receiver — use another port if needed:

   ```bash
   uv run mlflow ui --port 5000          # or --port 5001 to avoid AirPlay
   # for a persistent SQLite-backed store add: --backend-store-uri sqlite:///mlflow.db
   ```

3. **Run the eval** (picks up the server from `.env` — no `--tracking-uri`):

   ```bash
   uv run scripts/eval_local.py --run-name my-change
   ```

   The startup log prints the resolved store (`MLflow tracking store:
   http://127.0.0.1:5000`) and the run URL.

4. **View results** at `http://127.0.0.1:5000`:
   - **Experiments → rag-local-eval** → run rows with metrics/params.
   - **Traces** tab (`/experiments/<id>/traces?workflowType=genai`) → one
     GenAI trace per question.

To override for a single run (e.g. a throwaway file store) pass
`--tracking-uri ...`; the flag always wins over `.env`.

> `mlflow ui` and `mlflow server` are the same app on MLflow 3.x — `mlflow ui`
> fully supports the GenAI Traces view, so there's no need to run both.

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
`answer_confidence_threshold`, `web_search_fallback_threshold`), the
`vectordb_search_ef` recall knob, and the model id are logged as run **params**,
so two runs with different settings are directly comparable in the MLflow UI.
The full per-question table is attached to each run as `results.json`.

## Tuning HNSW recall (`ef` sweep)

The HNSW search-time beam width (`ef`, set by `VECTORDB_SEARCH_EF`) is the main
recall-vs-latency dial: higher `ef` searches more of the graph (better recall,
more latency). To see the tradeoff for your corpus instead of guessing, sweep it:

```bash
uv run scripts/eval_local.py --sweep-ef 32,64,128,256
```

This runs one MLflow run per value (named `ef-sweep-ef32`, `-ef64`, …), each
logging `vectordb_search_ef` as a param, and prints a comparison table of
`pass_rate` / `avg_grounding_score` (recall proxies) against `avg_latency_ms`.

Read it this way: pass_rate / grounding rising with `ef` means recall was being
left on the table — raise the default. A flat curve means `ef` isn't your
constraint. **Caveat:** `avg_latency_ms` is end-to-end (embedding + retrieval +
generation), so `ef` only moves the retrieval slice; at a small corpus
(~thousands of chunks) HNSW search is sub-millisecond and the latency column
will likely be flat — which is itself the useful finding that the vector index
is not the bottleneck.

## Prerequisites

- Local Mode backends running: Ollama and OpenSearch (see `docs/GETTING_STARTED.md`).
  If OpenSearch/Ollama are unreachable the run will record per-question errors
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

MLflow runs and traces are written to a **tracking store**, and the eval script
and the UI/server must point at the **same** store or the UI will show nothing.
The harness resolves the store in this order (first match wins):

1. `--tracking-uri` flag
2. `MLFLOW_TRACKING_URI` — set in `.env` (the configured default) or exported
3. fallback: local `./mlruns` file store

The resolved store is logged at startup (`MLflow tracking store: ...`), so you
can always see where a run went. Three stores are in play in this repo:

- **Tracking server (`http://127.0.0.1:5000`)** — the configured default via
  `.env`. Started with `uv run mlflow ui` (which also serves the web UI at the
  same address). This is the only store that powers the **GenAI Traces** view
  (`/experiments/<id>/traces?workflowType=genai`). The harness and the UI are
  the same address, so they can't drift apart.
- **File store (`./mlruns`)** — the fallback when `MLFLOW_TRACKING_URI` is unset.
  Simplest for a quick offline loop; browse with `uv run mlflow ui` launched
  from the project root (so it reads the same `./mlruns`).
- **SQLite store (`sqlite:///mlflow.db`)** — a single `mlflow.db` file in the
  project root; easy to reset (delete the file). Use it for both the run
  (`--tracking-uri sqlite:///mlflow.db`) and the UI
  (`uv run mlflow ui --backend-store-uri sqlite:///mlflow.db`).

Whichever you choose, the run and whatever serves the UI must agree. Mixing them
(e.g. a run written to `./mlruns` but a UI reading `mlflow.db`) is the most
common reason runs "disappear." Pointing both at the server sidesteps this
because there's a single address.

## GenAI traces

Each question is wrapped in an MLflow **trace span** (`answer_question`,
span type `AGENT`) capturing the question/top-k as inputs and the answer plus
source count as outputs. When the harness points at a tracking server, these
appear under the experiment's **Traces** tab — the
`workflowType=genai` view. Tracing is best-effort: if the span API is
unavailable the eval falls back to a plain call and still runs. The file and
SQLite stores record runs/metrics but the GenAI Traces UI is a server feature.

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

# Log runs AND GenAI traces into a running tracking server:
uv run scripts/eval_local.py --tracking-uri http://127.0.0.1:5000
# ...or set it once for the shell:
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
uv run scripts/eval_local.py
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
| `--tracking-uri` | flag → `MLFLOW_TRACKING_URI` → `./mlruns` | Where to log. Use `http://127.0.0.1:5000` for a server (needed for GenAI traces), or `sqlite:///mlflow.db`. |

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
| UI opens but shows no runs                | UI and eval pointed at different stores. Point both at the same place, or point the eval at your server with `--tracking-uri http://127.0.0.1:5000`. The eval logs its resolved store at startup. |
| Traces tab is empty / no GenAI traces     | Traces need a tracking **server**. Run with `--tracking-uri http://127.0.0.1:5000` (or `MLFLOW_TRACKING_URI`); file/SQLite stores don't serve the GenAI Traces view. |
| Connection refused to `127.0.0.1:5000`    | No server is running there. Start one (`mlflow server --host 127.0.0.1 --port 5000 ...`) before pointing the eval at it, or use a file/SQLite store instead. On macOS, port 5000 may be AirPlay — use another port. |
| `mlflow is not installed`                 | Install the eval extra: `uv pip install -e '.[eval]'`.                                           |
| DB/schema or alembic revision error on UI start | The `mlflow.db` was created by a different MLflow major. Stay on the pinned 3.x, or archive/delete `mlflow.db` to start fresh (loses prior runs). |
| `Errored questions` in the summary        | Ollama/OpenSearch unreachable. Start Local Mode backends (see `docs/GETTING_STARTED.md`).       |

## Typical dev loop

```bash
# 1. Start Local Mode backends (Ollama + OpenSearch) — see GETTING_STARTED.md
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
