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
- Keep embedding-model invocations separate: they may not use the same
  `guardrailConfig` flow, so enforcement must not unintentionally break
  embeddings.
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

- Deploy a numbered Guardrail version to a non-production environment.
- Exercise representative safe queries, denied topics, prompt attacks, PII
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

**Status:** Pending representative in-scope/out-of-scope examples.

- Test valid questions about RAG, vector databases, embeddings, and coding
  integrations alongside genuinely unrelated questions.
- Review false positives caused by the `OffTopicGeneralChatter` topic examples.
- Adjust the topic definition/examples only from observed test results, then
  publish a new numbered Guardrail version and repeat the tests.

**Acceptance:** Representative valid domain questions pass, selected unrelated
questions are blocked, and the known boundary cases are documented.

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
