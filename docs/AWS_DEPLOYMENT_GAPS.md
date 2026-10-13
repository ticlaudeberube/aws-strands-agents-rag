# AWS deployment gaps

What stands between "serverless mode works locally" (see
[SERVERLESS_LOCAL.md](./SERVERLESS_LOCAL.md)) and a working **AWS** deployment.
This complements the deploy runbook in
[infrastructure/terraform/DEPLOYMENT.md](../infrastructure/terraform/DEPLOYMENT.md).

> Status legend: ❌ blocker · ⚠️ confirm/needs action · ✅ done.
> Items marked **(confirm)** have NOT been verified against a live AWS account.

---

## TODO — remaining open items

Consolidated checklist of everything still open (details in the sections below).
Resolved items (#1, #2, #9b) are omitted.

**Deploy blockers**
- [ ] #3 Bootstrap the Terraform remote-state backend (S3 bucket + DynamoDB lock) by hand.
- [ ] #4 Run `terraform plan` / `apply` (nothing is deployed yet).
- [ ] #2 (follow-up) Wire the CI-built `lambda-package` artifact into the actual apply.

**Region / account** — ✅ resolved
- [x] #5 Assigned project Region confirmed as **US East (N. Virginia) =
      `us-east-1`** (AWS Settings), matching the Terraform `aws_region`. Local
      `default` + `cberube` profiles aligned to `us-east-1`.
- [x] #6 Service + model availability verified in `us-east-1` on
      `996428372683`: Bedrock `amazon.nova-lite-v1:0` is ACTIVE, and the
      OpenSearch Serverless + ElastiCache APIs respond (0 resources — available,
      none provisioned yet).
- [ ] #1 (follow-up) Enable the chosen Bedrock model for the deploying account
      (and submit the Anthropic FTU form if switching to Claude).

**Config / secrets / operational**
- [ ] #7 Populate the Tavily + Redis Secrets Manager secrets post-apply.
- [ ] #8 Keep PCA embedding projection consistent (re-index if `bedrock_pca_matrix_uri` changes).
- [ ] #9 Confirm the AOSS data-access policy maps the Lambda execution role.
- [ ] #10 Upload documents to the S3 `documents/` prefix to populate the KB.
- [ ] #11 Note: compute module `count` depends on an apply-time value (can't `-target` it in isolation).
- [ ] #12 Bump Terraform `required_version` to `>= 1.6.0` for CI/prod.

**Testing / hardening (not deploy blockers)**
- [ ] Add unit tests for the untested new code: `BedrockClient` Converse request/response, `DynamoDBClient` local wiring, multi-turn history (`_format_history` / `_apply_history` with both dict shapes + empty/oversized), and the frontend `serverlessChat` adapter mapping.
- [ ] Live end-to-end test of the frontend serverless adapter (#9b) against a deployed API Gateway + Lambda.

**Feature polish (optional, lower priority)**
- [ ] True token streaming via Bedrock `converse_stream` (currently single-chunk).
- [ ] Multi-turn memory in **Local Mode** (currently serverless-path only; see SERVERLESS_LOCAL.md TODO).
- [ ] Serverless-mode nuance: `bypass_cache` has no effect on the Lambda path; force-web passes through.

---

## Blockers — must fix before deploy

### 1. ✅ Bedrock inference model (fixed)
~~The Terraform default `anthropic.claude-3-haiku-20240307-v1:0` is
end-of-life.~~ **Fixed:** all tfvars (`dev`/`staging`/`prod`) and the root +
compute module defaults now use **`amazon.nova-lite-v1:0`** (active, on-demand,
no Anthropic FTU form); prod overrides to `amazon.nova-pro-v1:0`. To use
Anthropic Claude instead, submit the FTU form and set `bedrock_model_override`
to an active profile ID (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`).
Original guidance retained below for reference:
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

### 2. ✅ Converse migration ships in the Lambda package (fixed)
~~The real artifact must be built from `src/`.~~ **Fixed:** added
`infrastructure/lambda/build_lambda_package.sh` (+ `requirements-lambda.txt`)
which builds an arm64 zip from `src/` with the serverless-runtime deps, and a
**build-lambda** CI job that runs it and uploads `lambda.zip` +
`lambda.zip.sha256`. Verified the built zip contains the Converse change, the
handler history wiring, and the multi-turn routing helpers. Pass the artifact to
Terraform via `lambda_package_path` / `lambda_source_code_hash` on apply (see
DEPLOYMENT.md Step 2). Remaining manual step: wire the artifact into the actual
deploy pipeline/apply.

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

### 5. ✅ Project Region (resolved)
The assigned project Region (AWS Settings) is **US East (N. Virginia) =
`us-east-1`**, which matches the Terraform `aws_region` in all tfvars. The local
`~/.aws/config` default profile (previously `ca-central-1`) and the `cberube`
profile are both now set to `us-east-1`, so CLI/Terraform target the right
Region. No SCP region-block risk for a `us-east-1` deploy.

### 6. ✅ Service + model availability (verified in us-east-1)
Verified on account `996428372683` in `us-east-1`: Bedrock
`amazon.nova-lite-v1:0` reports `modelLifecycle.status = ACTIVE`, and the
OpenSearch Serverless (`list-collections`) and ElastiCache
(`describe-cache-clusters`) APIs respond (0 resources — the services are
available and callable, nothing provisioned yet). If the assigned Region turns
out NOT to be `us-east-1` (see #5), re-verify in that Region.

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

### 9b. ✅ Frontend ↔ API response-contract mismatch (fixed)
~~The React app only spoke the OpenAI-style SSE `/v1/chat/completions` contract,
but the deployed Lambda returns the serverless `{answer, sources, tier_used,
session_id, ...}` envelope at `POST /chat`.~~ **Fixed (Option 1 — frontend
adapter):** added `chatbots/react-chatbot/src/config/serverlessChat.js`, and
`App.js` now branches on `isServerlessMode()` to call `POST /chat` with the
serverless body and parse the single-JSON response (mapping `tier_used` →
`cached`/`web_search`/`rag`). A stable per-session id is sent so serverless
multi-turn history accumulates. Local-dev SSE streaming is unchanged. Verified:
production build passes with no warnings (`CI=true npm run build`), and the
adapter correctly parses a simulated serverless Lambda envelope. Still needs a
live end-to-end test against a deployed API Gateway + Lambda once #4 is done.

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

1. ~~Confirm the assigned project Region (#5)~~ — ✅ done (`us-east-1`).
2. ~~Set an active Bedrock model in the tfvars (#1)~~ — ✅ done (Nova). Still
   enable the model for the account if needed; submit the Anthropic FTU form only
   if switching to Claude.
3. ~~Wire CI to build the real Lambda zip (#2)~~ — ✅ done; still wire the
   artifact into the actual apply.
4. **Bootstrap the state backend** (#3), then `plan`/`apply` (#4).
5. Populate **secrets** (#7), confirm the **AOSS data-access policy** (#9), then
   **upload documents** to populate the KB (#10).
