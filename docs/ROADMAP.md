# Security and retrieval roadmap

This roadmap tracks follow-up work for PII handling, Bedrock Guardrails, and
document chunking. It is an implementation checklist, not a claim that the
system is compliant or that AWS behavior has been validated.

## 1. Cached-answer output checks

**Status:** Implemented and committed (`b6ebb32`).

- Screen each query before semantic-cache lookup.
- Run cached answers through the OUTPUT Guardrail using the current query and
  cached source text.
- Refuse a cache hit when it has no usable source text.
- Verify Guardrail interventions and failures are surfaced safely.

**Acceptance:** Guardrail tests cover safe cached answers, output interventions,
missing cached sources, and API errors; targeted tests and lint pass.

See [ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md) and
[GETTING_STARTED.md](GETTING_STARTED.md#bedrock-guardrails-serverless).

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

## 5. Tune denied-topic policy
**Status:** Superseded. The Bedrock denied topic was removed; topic scope is
enforced by the embedding scope gate (`src/agents/guardrails.py`, calibrated with
`scripts/eval_scope.py`).

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

**Status:** Partly implemented. Scope checks for follow-ups use the prior user
turn (`ScopeGate` in `src/agents/guardrails.py`). Answer generation for
follow-ups is unchanged, so a follow-up can still get a generic answer when the
knowledge base lacks the detail.
- chatbot should be able to accept fuzzy contextuel question using it's context.
- AKA: Are you able to continue chatting about the latest topic using context
- Which responds off topic reponse: I can help with questions about vector databases, vector search, embeddings, and RAG.

## 10. Strengthen the local eval loop

**Status:** Not implemented.

The local MLflow harness ([EVAL_LOCAL.md](EVAL_LOCAL.md)) works, but the judge
defaults to a weak model and nothing runs the eval automatically.

- **Stronger default judge.** `--judge-model` currently falls back to
  `settings.ollama_model` (`qwen2.5:0.5b`), which is too small to grade
  faithfulness reliably; the script only warns about it. Default the judge to a
  larger model (e.g. `llama3.1:8b`), configurable through a setting or env var
  so the pipeline's generation model can stay small. Document that the default
  model must be pulled first (`ollama pull llama3.1:8b`).
- **CI regression gate.** Run the deterministic (no-judge) eval and fail the
  build when `pass_rate/out_of_scope` falls below a set floor.
  - Prerequisite: CI ([ci.yml](../.github/workflows/ci.yml)) runs no OpenSearch
    or Ollama, and the eval needs both even without the judge. Pick one: add
    OpenSearch and Ollama as CI services (slower, needs a seeded index and a
    pulled model), run the gate in a separate scheduled or manual workflow, or
    gate only on the scope check, which doesn't need generation (see
    `scripts/eval_scope.py`).
  - Set the floor from a measured baseline run, not a guess, and record the
    baseline in [EVAL_LOCAL.md](EVAL_LOCAL.md).

**Acceptance:** A judge run without `--judge-model` uses the stronger model and
records it in the MLflow params. A CI or scheduled job fails when the
out-of-scope pass rate drops below the documented floor, and passes on the
current baseline.

## 11. Alert on Guardrail blocks
**Status:** Metric implemented; no alarm or dashboard widget yet.
- Add a CloudWatch alarm or dashboard widget for `answer/guardrail_blocked`
  in `infrastructure/terraform/modules/observability`.
- Set the alarm threshold from the block rate seen during item 4 validation.
- Break out blocks by policy type if the rate is high enough to need tuning
  (requires logging the intervening policy from the `ApplyGuardrail` response).
**Acceptance:** A sustained rise in `answer/guardrail_blocked` raises an alarm,
and the dashboard shows the block rate next to `answer/low_grounding`.

## 12. Commit and review the scope-gate change

**Status:** Partly committed. Commit `659a08b` covers the guardrail hook removal
and an early topic-scope change. The embedding scope gate, the security screen
in `shared_route`, the eval scripts, and the eval data are still staged or
modified.

- Stage only the scope-gate files: `src/agents/guardrails.py`,
  `src/agents/rag_routing.py`, `src/agents/strands_graph_agent.py`,
  `src/agents/local_opensearch_agent.py`, `src/config/settings.py`,
  `scripts/eval_scope.py`, `scripts/serverless_api_server.py`, `eval/`, the
  related tests, and the docs.
- Leave out files that are not part of this change unless they are reviewed:
  `.kiro/settings/mcp.json`, `.env.serverless-local`,
  `infrastructure/terraform/modules/guardrails/main.tf`,
  `src/agents/bedrock_guardrails.py`, and `src/tools/bedrock_client.py`.
- Restart the serverless server on port 8000 after the change so it loads the
  updated startup log message.

**Acceptance:** `git log` shows the scope-gate change as one or more commits, and
`git status` lists only the files left out on purpose.

## 13. Local guardrail parity

**Status:** Proposed; not approved.

Local mode has no input screen for PII or prompt attacks, and no output screen
beyond the grounding check. Serverless has both through Bedrock Guardrails.

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

**Status:** Not decided.

The local stack uses `qwen2.5:0.5b` for both fast and RAG generation. In the
end-to-end check, answers were weak: some rambled, and some repeated a citation
preamble.

- Compare a larger model (for example `llama3.1:8b` or `qwen2.5:3b`) on the
  same queries for answer quality and time per answer on the target desktop.
- Keep the model choice in settings, so local and serverless can differ.

**Acceptance:** A recorded comparison on the target desktop, with a chosen model
and its latency per answer.

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

`src/agents/topic_scope.py` is used only by the offline baseline in
`scripts/eval_scope.py`, and by the `topic_check` graph node. The runtime
does not execute that node.

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

## 21. Recalibrate when the PCA matrix changes

**Status:** Waiting on a decision.

The serverless thresholds were measured with the built-in deterministic PCA
projection, because no matrix file is committed. If `BEDROCK_PCA_MATRIX_URI` is
set to a real matrix, the Titan vectors change.

- Re-run the Titan rows of `scripts/eval_scope.py` on both sets.
- Update the serverless threshold default in `Settings.resolved_scope_threshold`
  if the best value moves.

**Acceptance:** The Titan rows in [EVAL_LOCAL.md](EVAL_LOCAL.md) match the matrix in
use.

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
