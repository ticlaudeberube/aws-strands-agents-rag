# Security and retrieval roadmap

This roadmap tracks follow-up work for PII handling, Bedrock Guardrails, and
document chunking. It is an implementation checklist, not a claim that the
system is compliant or that AWS behavior has been validated.

Items 1, 5, and 12 were closed or reframed and their numbers are not reused. The
other numbers stay the same because other docs cite them.

## 2. Enforce Guardrail use for model inference

**Status:** Not implemented; verify the correct enforcement boundary first.

- Review whether chat-model inference can be denied unless the required
  numbered Guardrail is attached.
- Chat inference no longer sends `guardrailConfig` (the application calls
  `ApplyGuardrail` explicitly), so an IAM condition on
  `bedrock:GuardrailIdentifier` would deny chat calls unless `guardrailConfig` is
  restored. Decide the enforcement boundary first.
- Keep embedding-model invocations separate: they never carry a guardrail, so
  enforcement must not unintentionally break embeddings.
- Prefer a narrowly scoped, testable control for the chat model; evaluate
  account- or organization-level enforcement only with a clear inventory of
  affected workloads and exceptions.
- Test authorized guarded calls, unguarded chat calls, and embedding calls
  before rollout.

**Acceptance:** A policy test proves chat inference cannot bypass the required
Guardrail while configured embedding calls and other explicitly exempt
workloads continue to work.

## 3. Protect sensitive content in logs

**Status:** Partially covered; Lambda log retention is configured, but
PII-specific logging controls need review.

- Inventory application logs, Bedrock model invocation logging, Guardrail
  traces, and any exported logs; confirm which are enabled and whether they
  capture raw prompts, answers, or matched PII.
- Keep Guardrail trace disabled outside controlled debugging, and never log raw
  content or full Guardrail/API responses by default.
- For logs that may contain sensitive content, verify encryption (including
  customer-managed KMS keys where required), least-privilege access, retention,
  and deletion/export policies.
- Add tests or checks that prevent sensitive user content from being written
  to application logs.

**Acceptance:** Logging configuration and representative log output are
reviewed; owners can demonstrate encryption, access controls, and retention
appropriate to the data classification.

## 4. Validate Guardrails in AWS

**Status:** Pending non-production deployment and AWS access.

- Run `terraform plan` for a non-production stage and review the changes: the
  denied topic is removed, so the guardrail updates in place and the version
  resource is replaced (`replace_triggered_by`), which updates the Lambda
  `BEDROCK_GUARDRAIL_VERSION`.
- Deploy a numbered Guardrail version to a non-production environment.
- Confirm Bedrock accepts the OUTPUT `ApplyGuardrail` call that sends only the
  answer (no `query` or `grounding_source` blocks) when no source text exists,
  and that PII and content policies still apply.
- Tune `grounding_threshold` (default `0.7`) from observed results; paraphrased
  answers often fail high thresholds.
- Exercise representative safe queries, out-of-scope queries, prompt attacks, PII
  inputs and outputs, grounded/ungrounded answers, and retrieved documents
  containing indirect prompt-injection attempts.
- Confirm Lambda IAM permissions, configured Guardrail ID/version, refusal
  behavior, logs, latency, and cost.
- Record false positives and false negatives before changing policy strengths
  or thresholds.

**Acceptance:** A repeatable test record identifies the Guardrail version,
region, tested cases, observed actions, and any known gaps. Do not treat unit
tests or Terraform validation as evidence of live service behavior.

## 6. Define document-ingestion PII handling

**Status:** Not implemented; policy decision required before coding.

- Decide which PII types should be rejected, anonymized, or retained for the
  actual document corpus and use case.
- Apply the chosen policy before chunking and embedding, not only to generated
  answers. Avoid persisting raw sensitive values in vectors, cache entries,
  metadata, or application logs unless explicitly required and protected.
- Define cleanup/re-indexing steps for documents, vectors, and semantic-cache
  entries if a PII policy changes or sensitive content is discovered after
  ingestion.
- Define access, retention, deletion, and any separately protected mapping
  needed if pseudonymization must be reversible.
- Test that redaction does not remove identifiers or technical values needed
  for retrieval.

**Acceptance:** Ingestion tests prove the chosen PII policy, including both
expected redaction and preservation of non-sensitive technical content.

## 7. Align chunk sizing with embedding tokenization

**Status:** Not implemented.

- Confirm the tokenizer and maximum input size for each configured embedding
  model.
- Replace or supplement whitespace-based counting in
  [chunking.py](../src/indexing/chunking.py) with model-compatible token counts,
  or a conservative validated bound if tokenizer support is unavailable.
- Preserve overlap/semantic boundaries as appropriate and verify all chunks
  fit the embedding model's input limit.
- Re-index existing documents if the chunking strategy changes.

**Acceptance:** Tests count chunks using the configured model's tokenizer (or
validated conservative limit), cover long and unusual text, and demonstrate
that chunks remain within the model's limit.

## 8. Complete Cognito sign-in for the browser client

**Status:** Implemented in Terraform and the React client; live AWS sign-in
validation remains pending a non-production deployment.

The implementation and deployment instructions are in place. Remaining work
requires a non-production AWS deployment:

- [ ] Review and apply the Terraform plan; confirm the Cognito domain, public
  app-client OAuth settings, and deployed frontend callback/sign-out URL.
- [ ] Build and deploy the React frontend, then verify hosted sign-in/sign-up
  completes the OAuth callback and the UI reflects signed-in state.
- [ ] Verify `POST /chat` succeeds with a valid access token and API Gateway
  rejects missing, invalid, and expired JWTs before invoking Lambda.
- [ ] Verify token refresh/re-authentication and sign-out behavior against the
  deployed user pool and app client.

**Acceptance:** An unauthenticated browser can sign in through Cognito and
complete the hosted-login OAuth callback; the client sends a valid access token
to `POST /chat`; missing or invalid tokens are rejected by API Gateway; expired
sessions refresh or return the user to sign-in; sign-out clears the session;
local development remains unauthenticated and has no Cognito sign-in controls.

## 9. Context engineering

**Status:** Implemented for the local API, the CLI, and the shared serverless
route. Live serverless behavior is not validated; it waits on item 8.

- A follow-up such as "What can I do with it?" after "What is a vector database?"
  is answered in context, not refused as off topic.
- Retrieval embeds the most recent `FOLLOWUP_USER_TURNS` user questions joined to the current one. Every cache
  layer is skipped for follow-ups.
- Generation sees a transcript of recent turns in both modes.
- The local API forwards prior `messages` turns, the CLI keeps its own turns, and
  serverless reads DynamoDB session history. All three feed the same shared route
  (`src/agents/rag_routing.py`), with helpers in `src/agents/history.py`.
- Eval: `eval/followup_pairs.jsonl` and `scripts/eval_followup.py`. Baseline in
  [EVAL_LOCAL.md](EVAL_LOCAL.md#follow-up-retrieval-scriptseval_followuppy).

**Acceptance results:**

- Unit tests (406 at the time of this change) cover the history helpers, the routing cache skip and
  joined retrieval, facade and endpoint forwarding, the serverless handler and
  shim, and the CLI turn helper.
- Retrieval eval (local Ollama and OpenSearch, top 5): follow-up hit rate went
  from 41.67% raw to 100% joined over 12 cases. Topic-switch hit rate stayed at
  83.33% in both modes over 6 cases. The join is kept.
- Live integration test (`tests/integration/test_followup_conversation.py`)
  passes: a two-turn request to the local API returns an in-scope answer.
- Live CLI check: a piped two-question session answers the follow-up from the
  knowledge base and stays on the vector database topic.
- React UI: the first browser run failed. The streaming branch of
  `/v1/chat/completions` (`stream: true`, used by the UI) did not pass history, so
  "What is it used for?" was rejected as off topic. Fixed in `api_server.py`, with
  regression tests for the stream flag. Re-run the UI check after the fix.
- Known miss: `sw-01` ("What is HNSW?" after "What is Milvus?") fails in both
  modes. The join does not cause it; the baseline raw query also misses.
- Follow-up history depth: `FOLLOWUP_USER_TURNS` sets how many recent user
  questions the router joins. Code default 3; local `.env` and
  `.env.serverless-local` set 10, which measured 6 of 6 on long-history cases
  against 2 of 6 at 3. A model-based condenser was removed: on the 26-case eval
  neither prompt version beat the join without a regression. Results and the
  decision are in [EVAL_LOCAL.md](EVAL_LOCAL.md#multi-hop-condenser-evaluation).

## 10. Strengthen the local eval loop
**Status:** Not implemented. The LLM judge was removed. It was slow, used a weak
judge model, and was not needed for the current decisions.

The local MLflow harness ([EVAL_LOCAL.md](EVAL_LOCAL.md)) works, but nothing runs
the eval automatically.

- **CI regression gate.** Run the deterministic eval and fail the build when
  `pass_rate/out_of_scope` falls below a set floor.
  - Prerequisite: CI ([ci.yml](../.github/workflows/ci.yml)) runs no OpenSearch
    or Ollama, and the eval needs both. Pick one: add OpenSearch and Ollama as CI
    services (slower, needs a seeded index and a pulled model), run the gate in a
    separate scheduled or manual workflow, or gate only on the scope check, which
    doesn't need generation (see `scripts/eval_scope.py`).
  - Set the floor from a measured baseline run, not a guess, and record the
    baseline in [EVAL_LOCAL.md](EVAL_LOCAL.md).

**Acceptance:** A CI or scheduled job fails when the out-of-scope pass rate drops
below the documented floor, and passes on the current baseline.

## 11. Alert on Guardrail blocks
**Status:** Metric implemented; no alarm or dashboard widget yet.
- Add a CloudWatch alarm or dashboard widget for `answer/guardrail_blocked`
  in `infrastructure/terraform/modules/observability`.
- Set the alarm threshold from the block rate seen during item 4 validation.
- Break out blocks by policy type if the rate is high enough to need tuning
  (requires logging the intervening policy from the `ApplyGuardrail` response).
**Acceptance:** A sustained rise in `answer/guardrail_blocked` raises an alarm,
and the dashboard shows the block rate next to `answer/low_grounding`.

## 12. Remove the tracked serverless env file that holds a Tavily key
**Status:** Open. `.env.serverless-local` is tracked by git and contains a live
`TAVILY_API_KEY`. The scope-gate and eval commits it used to track are done
(`9a9703a`, `69588c8`).

Removing the file from the index does not remove the key from git history, so the
key must be rotated.

**Acceptance:** The Tavily key is rotated. `.env.serverless-local` is ignored by
`.gitignore` and untracked (`git ls-files .env.serverless-local` prints nothing).

## 13. Local guardrail parity

**Status:** Proposed; not approved.

Local mode has no PII screen on input or output, and no equivalent of the Bedrock
content filters. It runs the same regex prompt-attack check as serverless, and the
grounding check on output. Serverless adds Bedrock Guardrails.

- Add a `GUARDRAIL_PROVIDER` setting (`auto`, `bedrock`, or `local`).
- Implement a local provider on the Ollama client that exposes the same
  `screen_input` and `apply_output_guardrail` methods that `route_rag_query`
  already calls, so routing does not change.
- Start with regex PII redaction for the entity types in
  `src/agents/bedrock_guardrails.py`. Add an optional prompt-injection scanner
  (LLM Guard, ONNX) behind a flag, off by default, after benchmarking it on the
  target desktop.
- Document the differences: Bedrock content filters have no exact local
  equivalent. Topic scope is already the same in both modes (embedding scope gate).

**Acceptance:** With `GUARDRAIL_PROVIDER=local`, PII in a query or answer is
redacted, and the refusal behavior matches serverless on a shared set of
prompts. Unit tests cover both providers.

## 14. Screen jailbreak phrases on word boundaries

**Status:** Not implemented.

Only the command phrases use word boundaries now (`COMMAND_PHRASES` in
`src/agents/guardrails.py`). The jailbreak phrases still match as substrings, so
`hack` matches `hackathon` and `disregard` can match ordinary text.

- Change the jailbreak matching to word boundaries, as was done for command
  phrases.
- Check the change against the security test cases in
  `tests/unit/test_agents/test_strands_graph_agent.py` and against a set of
  benign questions that contain these words.

**Acceptance:** Known attack phrases are still blocked, and benign questions that
contain `hack` or `disregard` as part of another word are not blocked.

## 15. Improve the local answer model
**Status:** Default is `llama3.2:1b`, read from `OLLAMA_MODEL`. The latest clean
benchmark favors `llama3.2:3b` on pass rate, at about 1.8 times the latency.

Clean runs (`clean-eval` experiment, procedure in [EVAL_LOCAL.md](EVAL_LOCAL.md)),
22 questions each:

| Model | Pass rate | Failures | Caveat rate | Grounding | Latency |
|---|---|---|---|---|---|
| `llama3.2:3b` | 0.955 | 1 (`competitor-003`) | 0.091 | 0.262 | 23.6 s |
| `llama3.2:1b` | 0.909 | 2 | 0.136 | 0.237 | 13.4 s |

One run per model. The gap is about one question, which is within run-to-run noise.

Still open:
- Decide the default: `llama3.2:3b` for pass rate, or `llama3.2:1b` for latency.
  Run each model again to measure the noise.
- The model-based query condenser was removed. On the 26-case eval it did not beat
  the join baseline. See [EVAL_LOCAL.md](EVAL_LOCAL.md#multi-hop-condenser-evaluation). The per-node
  presets in `src/agents/node_config.py` no longer carry a model field, because no
  call path read it.
- Keep the model choice in settings, so local and serverless can differ.

**Acceptance:** A chosen default, backed by repeated clean runs, with its latency
per answer recorded in [EVAL_LOCAL.md](EVAL_LOCAL.md).

## 16. Screen retrieved chunks for indirect prompt injection

**Status:** Not implemented; not approved.

Retrieved OpenSearch chunks reach the model without screening. A document in the
corpus could carry instructions that the model follows.

- Screen retrieved text in the routing step, before generation, with the
  pattern check and, if item 13 lands, the optional scanner.
- Add test cases that place injection text in an indexed document.

**Acceptance:** A chunk containing an injected instruction is dropped or
flagged before generation, and tests cover it.

## 17. Retire the keyword scope path

**Status:** Not implemented.

`src/agents/topic_scope.py` is used by the offline baseline in `scripts/eval_scope.py`,
by `guardrails.keyword_in_scope` (called only from the `topic_check` graph node, which
the runtime does not execute), and for `OUT_OF_SCOPE_ANSWER` in `rag_routing.py`.

- Decide whether to delete the node and its tests, or keep the keyword module as
  baseline-only with a clear label.

**Acceptance:** One of the two options is applied, and the graph config and tests
match it.

## 18. Expand the held-out scope set

**Status:** Not implemented.

`eval/scope_heldout.jsonl` has 29 questions, of which 5 are follow-ups. One miss
moves accuracy by about 3 points, so the thresholds are not yet well tested.

- Add 30 to 50 questions with realistic phrasing, including follow-ups and
  near-miss out-of-scope questions.
- Re-run the thresholds on the expanded set before changing them.

**Acceptance:** The held-out set has at least 60 questions, and the production
thresholds are re-confirmed or changed with recorded numbers.

## 19. Measure scope-gate latency and cold start

**Status:** Not measured for serverless.

- Measure the extra Titan call for each follow-up.
- Measure the eight anchor embeddings that run once per Lambda container.

**Acceptance:** Recorded p50 and p95 latency for follow-ups, and the added cold
start time, are written to [EVAL_LOCAL.md](EVAL_LOCAL.md) or the deployment docs.

## 20. Alert on scope-gate failures

**Status:** Not implemented.

The scope gate fails closed. If the embedding service is down, every query is
rejected, and nothing reports it.

- Log scope-gate errors as a metric, for example `scope/embedding_error`, and
  add an alarm in `infrastructure/terraform/modules/observability`.

**Acceptance:** A forced embedding failure raises the alarm.

## 21. Evaluate a fitted PCA projection (candidate)

**Status:** Candidate, not adopted. The evaluation scripts and the fitted matrix
were removed from the repo. The raw Titan vectors remain in `data/pca/`
(gitignored, 4.9 MB, including `titan_raw_chunks.npz`), so the evaluation can be
rebuilt without re-calling Bedrock for the chunks.

The serverless projection is a random orthogonal matrix. A matrix fitted by
SVD on the corpus (the top 768 right singular vectors of 636 Titan chunk vectors
from `document_loaders/milvus_docs/en`) measured as follows:

- Neighbour recall@10 against full 1536-dim cosine, on held-out chunks: random
  0.918 and 0.921; fitted PCA 0.994 and 0.996. The two splits were a random chunk
  split (159 queries) and a split by source document (152 chunks, 56 files).
- Retrieval recall@5 over 8 in-scope questions, in a local test index: random
  0.875, fitted PCA 1.000. The sample is small.
- Scope gate accuracy at threshold 0.35 over 76 labeled questions: random 0.868,
  fitted PCA 0.855, a difference of one question out of 76. The best accuracy for either projection was 0.934, at thresholds 0.24 (random) and
  0.25 (PCA).

The fitted matrix has rank 635 on 636 chunks. The earlier held-out fit reached
rank 476 and left 292 of 768 output columns as random completion. A larger corpus
would give the fit a fuller basis.

**Why it is not in use:** The fitted projection improved retrieval recall, but the
gain was measured on a small sample of 8 questions. The scope gate, the
production control for out-of-scope queries, did not improve (0.855 against 0.868).
Adopting the fit changes every stored vector and forces a full re-index. The fit
also depends on the corpus, so each document change would require a refit and
another re-index. The random projection already meets the current scope-gate
calibration, so the gain did not justify that cost. Revisit when the evaluation
shows a clear improvement on the scope gate, or when the corpus grows enough to
make the fit stable.

**Adopting it requires:**
- Re-indexing every document in `rag-kb` and `rag-cache`, because every stored
  vector changes.
- Loading the same matrix file in local and serverless through
  `BEDROCK_PCA_MATRIX_URI`, and bundling it in the Lambda package.
- Refitting and re-indexing whenever the corpus changes, since the fit depends on
  the documents.
- Re-running the scope-gate evaluation (`eval/scope_labels.jsonl` and
  `eval/scope_heldout.jsonl`) and updating the serverless threshold in
  `Settings.resolved_scope_threshold` if the best value moves.

**Acceptance:** Scope gate accuracy and retrieval recall on the labeled sets are
at least as good as the random projection, measured with the same harness on the
same chunks, before any production index is rebuilt. The Titan rows in
[EVAL_LOCAL.md](EVAL_LOCAL.md) match the matrix in use.

**Note:** The fit and evaluation scripts were deleted, so the harness must be
rewritten before this candidate can be measured again. Drop the leftover local test
indexes with `curl -X DELETE localhost:9200/rag-kb-ctl-rand,rag-kb-ctl-pca` if
they still exist.

## Operational notes

- Bedrock Guardrails protect configured runtime paths; they do not automatically
  sanitize stored documents, embeddings, caches, or logs.
- PII anonymization changes the returned content, not necessarily the original
  content in model invocation logs. Review CloudWatch logging, encryption,
  retention, and least-privilege access before handling regulated data.
- The current Bedrock policy covers selected PII entity types only. Add custom
  entity patterns only when requirements and representative tests justify them.
- Track implementation and live AWS validation separately: a passing local
  suite does not establish deployed behavior.
