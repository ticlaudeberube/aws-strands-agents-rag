# Anti-hallucination design

This document describes the layered defenses this project uses to keep the RAG
agent honest — and how to **measure** whether a change helped or hurt, using a
local MLflow evaluation harness.

It is grounded in the five techniques from the AWS workshop
[*How to Stop AI Agent Hallucinations*](https://github.com/aws-samples/sample-stop-ai-agent-hallucinations-workshop):
honest retrieval, semantic tool selection, multi-agent validation, neurosymbolic
guardrails, and agent steering. The workshop's guidance for a deterministic,
documentation-style domain like this one is to prefer **grounded retrieval and
in-code guardrails** over heavier techniques — which is the posture implemented
here.

## The failure modes we defend against

1. **Fabricated facts** — the model answers a question the knowledge base (KB)
   doesn't cover, inventing numbers, versions, or feature claims.
2. **Answering on weak/empty retrieval** — retrieval returns little or nothing,
   but the model generates a confident answer anyway.
3. **Off-topic leakage** — an out-of-scope query slips past the topic gate and
   reaches the RAG pipeline.
4. **Over-eager cache/web routing** — a query is misclassified (e.g. as
   time-sensitive) and takes the wrong path.
5. **Undetected low quality** — a weak answer is returned to the user with no
   signal that it may be unreliable.

## The layered defenses

Defenses run in order; each is a separate, independently testable layer. The two
answer paths — the shared serverless router (`src/agents/rag_routing.py`,
`route_rag_query`) and the local graph path
(`src/agents/strands_graph_agent.py`, `StrandsGraphRAGAgent.answer_question` →
`rag_worker_node` → `create_answer_generation_tool`) — apply the **same**
grounding logic via shared helpers, so both modes behave consistently.

### Layer 1 — Grounding prompt rule (input to generation)

`RAGPrompts.SYSTEM_INSTRUCTIONS` (`src/agents/prompts.py`) opens with explicit
`GROUNDING RULES`: answer only from the provided context, say plainly when the
context lacks the answer, and never guess or fabricate. Both modes format their
generation prompt from this same constant, so the instruction reaches local
(Ollama) and serverless (Bedrock, via `BedrockClient.format_rag_prompt`)
generation alike.

This is the softest layer — it depends on the model obeying the prompt — which
is exactly why the code-level layers below back it up.

### Layer 2 — Honest refusal on no grounding (pre-generation gate)

When retrieval produces nothing usable, the pipeline returns an honest refusal
instead of generating from empty/placeholder context.

- Shared router: in the web-search fallback branch of `route_rag_query`, when KB
  relevance is below `web_fallback_threshold` **and** web search returns no
  usable sources, it returns `NO_GROUNDING_ANSWER` and never calls the LLM.
- Local path: `generate_answer` checks `rag_routing._has_usable_grounding(sources)`
  before generating; with no usable sources it returns `NO_GROUNDING_ANSWER`
  with `confidence=0.0` and never calls the LLM.

"Usable" means at least one source carries non-empty `text`/`snippet` content.

### Layer 3 — Post-generation grounding + confidence check (output gate)

After an answer is generated, `rag_routing.evaluate_answer_quality(...)` (shared
by both modes) scores it and applies **at most one** caveat, in priority order:

1. **Low grounding** — `compute_grounding_score(answer, sources)` (the fraction
   of the answer's distinct content words, minus stopwords, that also appear in
   the retrieved source text) is below `answer_grounding_threshold`. Appends
   `LOW_GROUNDING_CAVEAT`, pulls confidence down to the grounding score, emits
   the `answer/low_grounding` metric.
2. **Low confidence** — grounding passed but the heuristic confidence
   (`_calculate_confidence_score`: source distance + answer shape) is below
   `answer_confidence_threshold`. Appends `LOW_CONFIDENCE_CAVEAT`, emits
   `answer/low_confidence`.

The two caveats are **mutually exclusive** — a user never sees two stacked
hedges. The grounding check is a cheap, deterministic lexical safety net, not a
semantic judge; it deliberately flags-with-a-caveat rather than hard-blocks,
because a valid paraphrase can score low. (For semantic verification, see the
optional LLM judge in the eval harness below.)

**Soft-steer retry (before the caveat).** When a freshly generated KB answer
fails the grounding check, `route_rag_query` first attempts *one* self-correction
instead of immediately caveating: it re-runs the KB search with a widened
`top_k` (`grounding_retry_top_k_multiplier`, capped at 50) and regenerates,
keeping whichever attempt grounds better. The supporting chunk is often just
outside the original `top_k`, so a cheap deterministic retry recovers it without
a reflection loop. This is the "steer, don't block" technique — the agent adapts
and completes rather than hedging. If the retry still fails the bar, the
caveat/confidence logic above applies exactly as before. The retry emits
`answer/grounding_retry`, runs at most once, and is toggled by
`grounding_retry_enabled` (default on). It lives in the shared router, so both
modes get it; the local single-shot `generate_answer` tool path is unaffected.

### Layer 4 — In-code guardrails (topic + security gates)

Before retrieval, two deterministic gates run (`src/agents/strands_graph_agent.py`):

- **Topic gate** — `_is_question_in_scope` matches domain keywords with
  **word boundaries** (so "rag" matches the acronym but not "sto**rag**e", and
  multi-word keywords like "vector database" match correctly). Off-topic queries
  route to a fixed rejection.
- **Security gate** — `_is_security_attack` pattern-matches jailbreak /
  injection attempts. Risky queries route to a fixed rejection.

These are enforced in code (not only in prompts), matching the workshop's
"neurosymbolic guardrail" technique. Word-boundary matching eliminates the
substring false positives that previously let off-topic queries through; genuine
whole-word ambiguity (e.g. "rag doll") is caught downstream by Layer 2/3 when the
KB has no relevant content.

> **Note — two gating paths.** `answer_question` (async local entrypoint) uses
> LLM-based topic/security agents as the primary gate, falling back to the
> in-code functions on error; the graph-node functions use the in-code checks
> directly. Both are live. See the metrics below to observe which outcomes
> occur in practice.

### Layer 4b — Hard block at the tool-call boundary (framework hook)

The node-level security gate above runs *inside* a gating path. To make the
security block hold **regardless of which path ran** — the gap the "two gating
paths" note describes — a Strands `BeforeToolCallEvent` hook
(`SecurityGuardrailHook`, `src/agents/guardrail_hooks.py`) is attached to the
`RAGWorker` agent. Strands fires it immediately before *any* tool the agent
selected is executed; when the pending tool's input matches a known
jailbreak/injection pattern (reusing `_is_security_attack`, the single source of
truth), the hook sets `event.cancel_tool` and the tool never runs — the model
receives an error-status result instead.

This is the article's **hard block vs soft steer** distinction applied here: a
security/injection attempt is a *hard* block the LLM cannot route around (it is
enforced by the framework before the tool runs), as opposed to the Layer 3
caveats, which *soft*-hedge an answer the agent still returns. The hook fails
**open** on a detector exception (logged loudly) because the node-level gates
remain in place upstream — a detector bug should not blanket-block legitimate
traffic. Covered by `tests/unit/test_agents/test_guardrail_hooks.py`.

### Layer 5 — Correct routing classification

`is_time_sensitive_query` (`src/agents/rag_routing.py`) classifies temporal
queries with **word-boundary** matching, so "renew" / "newcomer" no longer
trigger a time-sensitive cache bypass while "new" / "newest" / "latest" still
do. The local `_is_time_sensitive_query` delegates to this shared function, so
both modes classify identically (single source of truth).

## Configuration

All thresholds live in `src/config/settings.py` and are env-overridable:

| Setting | Env var | Default | Controls |
|---|---|---|---|
| `answer_grounding_threshold` | `ANSWER_GROUNDING_THRESHOLD` | `0.35` | Min grounding fraction before the low-grounding caveat fires (Layer 3). |
| `answer_confidence_threshold` | `ANSWER_CONFIDENCE_THRESHOLD` | `0.45` | Heuristic-confidence floor before the low-confidence caveat fires (Layer 3). |
| `grounding_retry_enabled` | `GROUNDING_RETRY_ENABLED` | `true` | Enable the one-shot widened-retrieval retry on weak grounding (Layer 3). |
| `grounding_retry_top_k_multiplier` | `GROUNDING_RETRY_TOP_K_MULTIPLIER` | `2` | Factor applied to `top_k` on the grounding retry (capped at 50). |
| `web_search_fallback_threshold` | `WEB_SEARCH_FALLBACK_THRESHOLD` | `0.15` | KB relevance below which web search runs; feeds the Layer 2 refusal. |
| `response_cache_threshold` | `RESPONSE_CACHE_THRESHOLD` | `0.92` | Semantic-cache hit similarity. |

Thresholds should be **tuned with data**, not by intuition — see the eval
harness below.

### Runtime tuning without a redeploy (serverless)

In serverless mode the six thresholds above are **compile-time defaults** that
can be overridden at runtime from a DynamoDB table, so an operator can retune
grounding without shipping code. Set `DYNAMODB_THRESHOLDS_TABLE` (Terraform
provisions `…-thresholds` and wires the env var + a read-only IAM grant) and add
one item per knob:

```json
{ "name": "answer_grounding_threshold", "value": 0.45 }
```

`ThresholdStore` (`src/tools/threshold_store.py`) reads the table **once at
Lambda cold start** (the graph is a warm-context singleton), coerces each
`value` to the setting's type, and overrides the matching default for the life
of the container; the change takes effect on the next cold start. Only the six
names above are tunable — any other row is ignored. Every failure mode (table
unset, missing, scan error, malformed row, or Local Mode) falls back to the
`settings.py` value, so the feature is purely additive. Model IDs, table names,
and other infra config are deliberately **not** tunable this way — they must
change through a deploy.

## Observability (serverless)

The shared router emits warning metrics through the injected `metric_emitter`
(`MetricsEmitter.emit_named` in `src/tools/cloudwatch_metrics.py`), published to
the `StrandsRAG/{Stage}` CloudWatch namespace (and as EMF log lines as a
backstop):

- `answer/low_grounding` (Count) — answers flagged as poorly supported.
- `answer/low_confidence` (Count) — answers with a weak retrieval match.
- `answer/grounding_retry` (Count) — the soft-steer retrieval retry fired. A
  rising `grounding_retry` with a flat `low_grounding` means the retry is
  recovering answers; both rising means the KB likely lacks the content.

Each serverless response body also returns `confidence_score` and
`grounding_score` per request (`agentcore_handler.py`). Chart `answer/low_grounding`
against request volume and alarm on spikes as an early KB/retrieval-degradation
signal. Local Mode applies the same caveats and logs them, but has no CloudWatch
emitter (expected for local dev).

### OpenTelemetry traces (AgentCore / ADOT)

The custom metrics above tell you *how often* a defense fired; OpenTelemetry
tracing tells you *per invocation what happened*. The serverless Lambda package
(`infrastructure/lambda/requirements-lambda.txt`) includes `strands-agents[otel]`
and `aws-opentelemetry-distro`, and the compute module sets
`AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` on the chat Lambda (toggle:
`enable_otel`, default on). With that, AgentCore auto-instruments Strands and
emits invocation logs, per-tool-call traces (which tool ran, input/output,
latency), and guardrail blocks to CloudWatch — no custom instrumentation code.
This makes the Layer 4b hard blocks and the `answer/grounding_retry` path
directly observable in a trace, complementing the aggregate metrics. X-Ray
active tracing (and the role's X-Ray write permission) is already enabled, so
traces have a sink.

**Dependency isolation (vs MLflow).** OpenTelemetry lives *only* in the
serverless Lambda package — never in the base project deps or the `eval`
extra. MLflow 3 (local eval harness) also pulls in OpenTelemetry for its GenAI
tracing, so the two OTel-consuming toolchains are kept in **separate
environments** (serverless Lambda vs. local eval venv) to avoid a dependency
resolver clash. They never run in the same process: MLflow traces Local Mode
eval runs to a local MLflow server; ADOT traces Lambda invocations to
CloudWatch. Keep them separate when installing.

## Measuring with local MLflow

Code-level defenses tell you the system *can* be honest; they don't tell you
whether a change made it *more* honest across your corpus. The local MLflow
evaluation harness closes that loop.

### Why MLflow, and why local

- **It answers "did my change help?"** Run a fixed, tagged question set through
  the pipeline, log grounding/confidence/refusal/caveat/tier/latency plus a
  pass/fail per question, and compare runs. Tuning `answer_grounding_threshold`
  from 0.35 → 0.45 becomes a measured before/after, not a guess.
- **It's a regression gate.** The deterministic (lexical-only) run is fast and
  reproducible, suitable for CI: fail the build if, say, out-of-scope pass rate
  drops (topic gate got looser).
- **It's isolated and free.** `mlflow` lives in the `eval` optional-dependency
  group, is imported lazily, and is never reachable from the runtime/serverless
  path. Local mode runs fully offline (Ollama + Milvus), so there is no AWS
  dependency or cost. (Managed MLflow on SageMaker/Databricks exists, but is
  unnecessary for the dev loop.)

### Benefits summary

- Turns threshold/prompt tuning into evidence-backed decisions.
- Catches anti-hallucination regressions automatically (CI gate).
- Separates the strong deterministic signal (lexical grounding) from an optional
  semantic read (LLM judge), so you choose cost vs depth per run.
- Produces a per-run audit trail (`results.json`) of exactly what the agent did.

### How to run

Full operational detail — install, flags, question-set schema, grading tags,
the optional LLM judge, and how to interpret results — is in
**[EVAL_LOCAL.md](EVAL_LOCAL.md)**. In brief:

```bash
uv pip install -e '.[eval]'              # install the eval extra once
uv run scripts/eval_local.py             # deterministic, lexical metrics only
uv run scripts/eval_local.py --judge --judge-model llama3.1:8b   # add LLM judge
uv run mlflow ui --port 5001             # compare runs at http://127.0.0.1:5001
```

> On macOS port 5000 is usually taken by the AirPlay Receiver, hence `--port
> 5001`. If the UI shows no runs, the eval and the UI are pointed at different
> tracking stores — see the store/port notes in **[EVAL_LOCAL.md](EVAL_LOCAL.md)**.

The judge defaults to `settings.ollama_model` (`qwen2.5:0.5b`), which is weak as
an evaluator — point `--judge-model` at a larger installed model (e.g.
`llama3.1:8b`) for meaningful faithfulness scores. Keeping the pipeline's
generation model small while judging with a larger one is the right split: the
thing being graded should not also be the grader.

### What "good" looks like

- High `pass_rate/out_of_scope` + high `refusal_rate` on unanswerable items =
  the gates and the refusal path are working.
- Low `refusal_rate` on `in_scope` items = retrieval and the grounding threshold
  aren't too aggressive.
- `avg_grounding_score` (lexical) diverging from `avg_judge_faithfulness`
  (semantic) usually means heavy paraphrasing — a signal to reconsider
  `answer_grounding_threshold` rather than trust the lexical number alone.

## Where each workshop technique landed

| Technique | Status here | Layer |
|---|---|---|
| Honest retrieval / no-results | Implemented | Layers 1–3 |
| Neurosymbolic guardrails | Implemented (+ framework-level hard block) | Layers 4, 4b |
| Agent steering (self-correct) | Implemented — one-shot widened-retrieval retry, then caveat/refuse (not a full reflection loop) | Layer 3 |
| Semantic tool selection | Not implemented (2-tool pipeline; low value) | — |
| Multi-agent validation | Not implemented; optional LLM judge covers offline eval | eval harness |

## Tests

- `tests/unit/test_agents/test_rag_routing_grounding.py` — refusal gate,
  grounding score, grounding/confidence caveat mutual exclusivity, word-boundary
  temporal matching.
- `tests/unit/test_agents/test_local_generation_grounding.py` — local-path
  parity (refusal + caveats).
- `tests/unit/test_agents/test_guardrail_hooks.py` — the Layer 4b hard-block
  hook: cancels tool calls on a detected attack, allows safe input, fails open
  on detector error.
- `tests/unit/test_tools/test_cloudwatch_answer_metrics.py` — the `answer/*`
  metrics reach CloudWatch end-to-end.
- `tests/unit/test_eval_local.py` — the eval harness scoring/grading logic.
