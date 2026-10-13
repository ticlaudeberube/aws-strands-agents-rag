# AWS deployment gaps

What stands between "serverless mode works locally" (see
[SERVERLESS_LOCAL.md](./SERVERLESS_LOCAL.md)) and a working **AWS** deployment.
This complements the deploy runbook in
[infrastructure/terraform/DEPLOYMENT.md](../infrastructure/terraform/DEPLOYMENT.md).

> Status legend: ❌ blocker · ⚠️ confirm/needs action · ✅ done.
> Items marked **(confirm)** have NOT been verified against a live AWS account.

---

## Blockers — must fix before deploy

### 1. ❌ Bedrock inference model is end-of-life / access-gated
The Terraform default `anthropic.claude-3-haiku-20240307-v1:0` has reached
**end-of-life** and is no longer invokable. Pick an active model:
- **Amazon Nova** (e.g. `amazon.nova-lite-v1:0`) — no extra access form; works
  today. (This is what the local setup uses.)
- **Anthropic Claude** (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`) —
  requires the one-time **Anthropic First-Time-Use (FTU) form** per account,
  submitted from the redesigned Bedrock console model catalog (the old "Model
  access" page is retired). Both accounts tested in this project are still
  blocked on this form.

Action: set `bedrock_inference_model_id` (and/or `bedrock_model_override`) in
`infrastructure/terraform/environments/*.tfvars` to an active model, and ensure
the chosen model is enabled for the deploying account + Region.

### 2. ❌ Converse migration must be in the Lambda package
`src/tools/bedrock_client.py` now uses the Bedrock **Converse** API (model-
agnostic). This only reaches Lambda if **CI rebuilds the deployment zip from
`src/`**. The compute module currently builds a **placeholder zip**; the real
artifact must be built and passed via `lambda_package_path` /
`lambda_source_code_hash` (see DEPLOYMENT.md Step 2).

### 3. ❌ Terraform remote-state backend not bootstrapped
`backend.tf` points at an S3 bucket (`strands-rag-tfstate`) + DynamoDB lock
table (`strands-rag-tflock`) that must be **created by hand once** before the
first `terraform init` (chicken-and-egg; Terraform can't create its own state
store). See DEPLOYMENT.md Step 1.

### 4. ❌ Nothing has been deployed
No `terraform plan`/`apply` has run. The whole stack (VPC, OpenSearch
Serverless, ElastiCache, Lambda, API Gateway, Cognito, CloudFront, S3, WAF) is
unprovisioned.

---

## Region / account constraints (new AWS experience)

### 5. ⚠️ (confirm) Project Region mismatch
Everything is pinned to `us-east-1`, but on the managed AWS experience the
**assigned project Region** (from the contact address, viewable in AWS Settings
→ View all projects → Overview → Additional Info → Region) governs where
Regional resources can be created. Local `~/.aws/config` has shown
`ca-central-1` / `us-east-2`. If the assigned Region is not `us-east-1`, the
deploy is **blocked by managed SCPs**. Confirm the assigned Region and set the
Terraform `aws_region` to match.

### 6. ⚠️ (confirm) Service + model availability in the assigned Region
Verify Bedrock (and the chosen model), OpenSearch Serverless, and ElastiCache
are all available in the assigned Region — not every service/model exists in
every Region.

---

## Configuration / secrets gaps

### 7. ⚠️ Secrets Manager values
The compute module creates **empty** Tavily + Redis secrets; populate the real
values out-of-band after apply. In the cloud, `_resolve_tavily_api_key` reads
`SECRETS_TAVILY_API_KEY` from Secrets Manager (locally we bypass this with a
plain `TAVILY_API_KEY` env var).

### 8. ⚠️ PCA embedding projection consistency
`BedrockClient` reduces Titan's 1536-dim embeddings to 768-dim. With
`bedrock_pca_matrix_uri` unset it uses a deterministic built-in projection
(stable across processes). KB documents and queries MUST be embedded with the
**same** projection — if you set/change `bedrock_pca_matrix_uri`, re-index the
knowledge base.

---

## Operational gaps

### 9. ⚠️ (confirm) OpenSearch Serverless data-access policy
Production `OpenSearchClient` uses TLS + SigV4 (`aoss`) — correct for AOSS. The
Lambda role gets `aoss:APIAccessAll` from the compute module, but AOSS also
requires a **data-access policy** mapping the Lambda execution role to the
collection. Verify that policy exists and includes the role, or retrieval/index
calls will 403.

### 9b. ⚠️ (confirm) Frontend ↔ API response-contract mismatch
The React app calls an **OpenAI-style** `/v1/chat/completions` (served by
`api_server.py`), but the deployed **Lambda** behind API Gateway returns the
**serverless** envelope `{answer, sources, tier_used, session_id, latency_ms,
confidence_score, web_search_unavailable}` from a `POST /chat` route. These are
**different contracts**. Locally this is hidden because the GUI runs inside
`api_server.py` (via the shim). On real AWS the frontend talks to API Gateway →
Lambda directly, so either the frontend must consume the serverless shape, or an
adapter/BFF must translate it. Confirm which contract the deployed frontend
expects and reconcile. (Verified by code reading: the Lambda response envelope
is built in `agentcore_handler.lambda_handler`; the React client in
`chatbots/react-chatbot/src/App.js` consumes the OpenAI-style streaming shape.)

### 10. ⚠️ Index + document population
`rag-kb` / `rag-cache` indexes and real documents don't exist until the indexing
pipeline runs. Post-deploy, upload documents to the S3 `documents/` prefix to
trigger the indexing Lambda (S3 `ObjectCreated`). Until then, KB retrieval is
empty.

### 11. ⚠️ Terraform `count` depends on apply-time value
The compute module's S3-trigger `count = local.enable_s3_trigger` depends on
`module.frontend.documents_bucket_id` (known only at apply). A full `apply`
resolves it, but you can't cleanly `-target` the compute module in isolation,
and `sam local --hook-name terraform` can't plan it (see SERVERLESS_LOCAL.md).

### 12. ⚠️ Terraform version drift
`versions.tf` is relaxed to `>= 1.5.0` to validate on the local `v1.5.7`; design
target is `>= 1.6.0`. Bump in CI/prod.

---

## Not gaps (verified working)

- ✅ Serverless **code path** runs end-to-end locally (shared route → Bedrock via
  Converse → OpenSearch k-NN → Redis cache).
- ✅ Titan embeddings invoke successfully (account `996428372683`, `us-east-1`).
- ✅ Terraform `validate` passes for all six modules.
- ✅ `BedrockClient` Converse migration verified against real Bedrock (Nova).
- ✅ The **real Lambda handler** (`agentcore_handler.lambda_handler`) runs
  end-to-end locally with injected local backends (OpenSearch/Redis/DynamoDB +
  real Bedrock) via `scripts/run_lambda_handler_local.py`: HTTP 200 responses,
  **DynamoDB session history load + persist across turns**, and the HTTP 400
  validation path all pass. This exercises production handler behavior the GUI
  shim does not (session persistence, the serverless response envelope).

> Note: DynamoDB session persistence is now validated **locally** (DynamoDB
> Local container). The real tables are still created by `terraform apply` on
> AWS (not yet run — see blocker #4).

---

## Suggested order of attack

1. Confirm the **assigned project Region** (#5) — everything else depends on it.
2. Set an **active Bedrock model** in the tfvars and enable it for the account
   (#1); submit the Anthropic FTU form if going with Claude.
3. Wire **CI to build the real Lambda zip** with the Converse change (#2).
4. **Bootstrap the state backend** (#3), then `plan`/`apply` (#4).
5. Populate **secrets** (#7), confirm the **AOSS data-access policy** (#9), then
   **upload documents** to populate the KB (#10).
