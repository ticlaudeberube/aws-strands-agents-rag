# Governance: local MLflow vs production

How changes to answer behavior (thresholds, guardrails, models, infrastructure)
are measured, reviewed, and deployed. Local development uses MLflow runs as the
record of evidence. Production uses no MLflow; its controls are Guardrails,
a runtime thresholds table, Terraform, and access and logging controls.

Design details live in [ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md). The
harness itself is documented in [EVAL_LOCAL.md](EVAL_LOCAL.md). This page covers
who decides what and how a change moves from local to production.

## Summary

| Concern | Local (dev loop) | Production (serverless) |
|---------|------------------|-------------------------|
| Evidence of quality | MLflow runs from `scripts/eval_local.py` | None recorded in the repo |
| Where results live | `./mlruns`, `sqlite:///mlflow.db`, or an MLflow server | Not applicable |
| Answer thresholds | Env vars and `src/config/settings.py` | DynamoDB thresholds table, read at cold start |
| Safety filter | Not applied | Bedrock Guardrail (ID and version from env vars) |
| Approval | Human review of runs in the MLflow UI | None enforced in code |
| Automated gate | None (roadmap item 10) | None (roadmap item 10) |
| Change record | MLflow run history | Terraform state and plan output; CloudTrail if DynamoDB data events are enabled |

## Local: MLflow as the evidence record

`scripts/eval_local.py` runs a tagged question set through Local Mode. Each run
logs:

- Parameters: the settings used for the run.
- Metrics: grounding, confidence, refusal, caveat, tier, latency, and pass rate.
- Artifacts: `results.json` with per-question results.
- GenAI traces, when the tracking store is a server (`http://127.0.0.1:5000`).

Use the MLflow UI to compare runs before and after a change. A threshold or
prompt change counts as an improvement only when its run beats the previous
baseline on the same question set.

Rules:

- `mlflow` is an optional `eval` dependency and is imported lazily. Runtime and
  Lambda code must never import it (see `pyproject.toml`, and the OpenTelemetry
  split in [ANTI_HALLUCINATION.md](ANTI_HALLUCINATION.md#observability-serverless)).
- Local runs are not evidence for production on their own. They use Local Mode
  models (Ollama and OpenSearch), not the Bedrock models in the Lambda.
- Keep one tracking store per comparison. Runs in `./mlruns` are invisible to a
  UI that reads `mlflow.db`.

## Production: controls

| Control | Where | What it does |
|---------|-------|--------------|
| Bedrock Guardrail | `modules/guardrails` | Blocks unsafe or off-policy content. The app reads `BEDROCK_GUARDRAIL_ID` and `BEDROCK_GUARDRAIL_VERSION`. |
| Guardrail metric | `src/agents/rag_routing.py` | Emits `answer/guardrail_blocked` to CloudWatch. Alarm pending (roadmap item 11). |
| Runtime thresholds | DynamoDB `<stage>-thresholds` | Read once at cold start. The app's IAM role has only `GetItem` and `Scan` on this table. |
| Infrastructure review | Terraform | `plan` shows every change before `apply`. State is versioned in S3 with DynamoDB locking. |
| Access | Cognito user pool | Invite-only sign-in. The API rejects requests without a valid token. See [AUTHENTICATION.md](AUTHENTICATION.md). |
| Logs and tracing | CloudWatch, X-Ray, ADOT | Lambda logs, error alarm, and traces. |

The app writes only to the session and analytics tables. It never writes to the
thresholds table.

### Changing a production threshold

No code enforces this procedure. Until automation exists, follow these steps:

1. Run `scripts/eval_local.py` with the candidate values, and record the run
   name and metrics.
2. Compare the run with the current baseline on the same question set.
3. Get a second person to review the comparison.
4. Update the item in the thresholds table. Record the change in the same
   place as the review, such as the pull request or ticket.
5. Check the next analytics output, or the guardrail metric, for regressions.

Thresholds that are not in the table fall back to the defaults in
`src/config/settings.py`.

## Known gaps

- No automated gate between a dev run and a production change. Roadmap item 10
  covers a CI regression gate.
- Threshold writes have no approval step or audit trail in the repo.
- No registry for models or prompts. Changes are tracked through git and
  Terraform, not by version number.
- The guardrail alarm does not exist yet (roadmap item 11).
- Managed MLflow (SageMaker or Databricks) is not used. It would need a
  runtime integration, which the repo currently forbids.

## Decisions that would change this page

- Adding a CI gate, or running the eval on a schedule (roadmap item 10).
- Writing thresholds through a pipeline instead of by hand.
- Moving MLflow to a shared server or managed service.
