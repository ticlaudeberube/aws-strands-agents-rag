# Serverless Deployment (Terraform)

Infrastructure-as-code for the **serverless** deployment mode of the Strands
Agents RAG application (Lambda + AgentCore + Bedrock + OpenSearch Serverless +
API Gateway + DynamoDB + ElastiCache Redis + Cognito + CloudFront + S3).

> This document is a pick-up-later guide. It explains the remote-state
> bootstrap (the part that is **not** created automatically), the prerequisites,
> and the full deploy/teardown workflow. Nothing here has been applied to AWS
> yet — the Terraform has only been validated locally.

---

## TL;DR — current status

- All six Terraform modules are written and **`terraform validate` passes**.
- **Nothing has been deployed to AWS.** No `terraform plan`/`apply` has run.
- No AWS credentials are configured in this environment.
- The **Terraform remote-state backend does not exist yet** (see below). This is
  the one manual bootstrap step you must do before the first real `init`.

To just check the config compiles (no AWS needed):

```bash
cd infrastructure/terraform
terraform fmt -check -recursive
terraform init -backend=false     # skips the remote state backend
terraform validate
```

---

## What "the backend bucket doesn't exist yet" means

Terraform tracks every resource it manages in a **state file**
(`terraform.tfstate`). For team/production use, that state is stored
**remotely** so there is a single shared source of truth and runs are locked
against each other. This project uses an **S3 backend with a DynamoDB lock
table**, configured in [`backend.tf`](./backend.tf):

```hcl
terraform {
  backend "s3" {
    bucket         = "strands-rag-tfstate"              # stores terraform.tfstate
    key            = "serverless-deployment/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "strands-rag-tflock"               # state lock
    encrypt        = true
  }
}
```

**The chicken-and-egg problem:** Terraform cannot create its own state bucket,
because it needs the bucket to exist *before* it can store state in it. So the
state bucket (`strands-rag-tfstate`) and the lock table (`strands-rag-tflock`)
must be created **once, by hand, as a bootstrap step**, before you ever run
`terraform init` against the real backend.

> ⚠️ Do **not** confuse this with the application S3 bucket. The
> `strands-rag-<stage>-documents` bucket (documents + React build) IS created by
> Terraform during `apply` — see `modules/frontend`. The **backend** bucket
> (`strands-rag-tfstate`) is Terraform's own bookkeeping and must pre-exist.

That is why every validation so far used `terraform init -backend=false`: the
`-backend=false` flag tells Terraform to skip connecting to the (nonexistent)
remote state bucket and only validate the configuration locally.

---

## Prerequisites (to actually deploy)

1. **AWS credentials** with permission to create the resources (VPC, Lambda,
   API Gateway, Cognito, DynamoDB, OpenSearch Serverless, ElastiCache,
   CloudFront, S3, Secrets Manager, WAF, CloudWatch, IAM).
   ```bash
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_REGION=us-east-1
   # or: aws configure / an AWS profile
   ```
2. **Terraform**. Installed here is `v1.5.7`; `versions.tf` is currently relaxed
   to `required_version >= 1.5.0`. The design target is `>= 1.6.0` — bump this in
   CI/prod. The aws provider is pinned `~> 5.95`.
3. **Amazon Bedrock model access** enabled in the target region for
   `anthropic.claude-3-haiku-20240307-v1:0` and `amazon.titan-embed-text-v1`
   (and Claude 3 Sonnet if `bedrock_model_override` is used in prod).
4. The **Lambda deployment package(s)** built. The compute module uses a
   placeholder zip for `validate`; a real deploy supplies the built artifact via
   the `lambda_package_path` / `lambda_source_code_hash` variables (see
   `modules/compute`). CI should build the zip from `src/`.
5. The **Tavily API key** and any **Redis credentials** to put into the Secrets
   Manager secrets created by the compute module (values are managed
   out-of-band, not stored in Terraform state).

---

## Step 1 — Bootstrap the remote state backend (one time)

Create the state bucket and lock table **before** the first `init`. Pick ONE of
the options below.

### Option A — AWS CLI (quickest)

```bash
REGION=us-east-1
STATE_BUCKET=strands-rag-tfstate
LOCK_TABLE=strands-rag-tflock

# S3 bucket for state (versioned + encrypted)
aws s3api create-bucket \
  --bucket "$STATE_BUCKET" \
  --region "$REGION" \
  $( [ "$REGION" = "us-east-1" ] || echo --create-bucket-configuration LocationConstraint="$REGION" )

aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# DynamoDB table for state locking (partition key MUST be named LockID)
aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"
```

### Option B — a tiny separate "bootstrap" Terraform config

Create `infrastructure/terraform/bootstrap/main.tf` with **local** state (no
backend block) that defines just the `aws_s3_bucket` (+ versioning, encryption,
public-access-block) and the `aws_dynamodb_table` (hash key `LockID`), then
`terraform apply` it once. This keeps the bootstrap reproducible in code. It is
intentionally a separate root module so it is not managed by the main stack it
underpins. (Not yet written — a TODO if you prefer this over Option A.)

> The DynamoDB lock table's partition key **must** be named `LockID` — that is a
> hard requirement of the Terraform S3 backend.

---

## Step 2 — Build the Lambda package

The compute module validates against a placeholder zip. For a real deploy, build
the deployment artifact from `src/` (chat handler
`agentcore_handler.lambda_handler` + indexing handler
`indexing_handler.lambda_handler`) and pass it in. Example (adjust to your
packaging/CI):

```bash
# illustrative — wire this into CI
pip install -r requirements.txt -t build/
cp -r src build/
( cd build && zip -r ../lambda.zip . )
# then pass -var "lambda_package_path=../../lambda.zip" (+ source_code_hash) on apply
```

---

## Step 3 — Init, plan, apply

```bash
cd infrastructure/terraform

# Connect to the real remote backend (bucket/table from Step 1 must exist)
terraform init

# Review the plan for the chosen environment
terraform plan  -var-file=environments/dev.tfvars

# Apply
terraform apply -var-file=environments/dev.tfvars
```

Per-environment variables live in `environments/{dev,staging,prod}.tfvars`
(stage name, Bedrock model IDs, Redis node type, OpenSearch capacity, VPC CIDR).

### After apply — post-deploy steps
- Put the real secret values into the Secrets Manager secrets (Tavily key, Redis
  creds) created by the compute module.
- Build the React app with the serverless env vars and sync it to the frontend
  bucket:
  ```bash
  cd chatbots/react-chatbot
  REACT_APP_API_URL="https://<api_endpoint>" \
  REACT_APP_USER_POOL_ID="<user_pool_id>" \
  REACT_APP_USER_POOL_CLIENT_ID="<user_pool_client_id>" \
  REACT_APP_AWS_REGION="us-east-1" \
    npm run build
  aws s3 sync build/ "s3://<documents_bucket_id>/frontend/"
  # then invalidate CloudFront if needed
  ```
  (`api_endpoint`, `user_pool_id`, `user_pool_client_id`, `cloudfront_domain`,
  and `documents_bucket_id` are Terraform **outputs**.)
- Upload source documents to `s3://<documents_bucket_id>/documents/` to trigger
  the indexing Lambda, which creates the OpenSearch `rag-kb` / `rag-cache`
  indexes on first use.

---

## Teardown

```bash
cd infrastructure/terraform
terraform destroy -var-file=environments/dev.tfvars
```

The bootstrap state bucket/lock table from Step 1 are **not** managed by this
config, so remove them separately when fully decommissioning (empty the versioned
state bucket first).

---

## Module layout

| Path | Purpose |
|------|---------|
| `backend.tf` | S3 remote state + DynamoDB lock (bootstrap required) |
| `versions.tf` | Terraform + aws provider version pins |
| `variables.tf` / `outputs.tf` | Root inputs/outputs |
| `environments/*.tfvars` | Per-environment values (dev/staging/prod) |
| `modules/networking` | VPC, private subnets, VPC endpoints, security groups |
| `modules/data` | DynamoDB tables, OpenSearch Serverless collection, ElastiCache Redis |
| `modules/compute` | Lambda chat + indexing functions, least-privilege IAM |
| `modules/api` | API Gateway (HTTP API), Cognito user pool + JWT authorizer, WAF |
| `modules/frontend` | S3 bucket (documents + frontend), CloudFront distribution |
| `modules/observability` | CloudWatch log groups, errors/total alarm, X-Ray |

---

## Known deviations / TODO before production

- **Terraform version**: `required_version` is relaxed to `>= 1.5.0` to validate
  on the local `v1.5.7`. Design target is `>= 1.6.0` — bump in CI/prod.
- **AWS provider pin**: `~> 5.95` (design mentioned `~> 5.60`), raised to satisfy
  the registry VPC module's floor. Still within the 5.x line.
- **Remote-state bootstrap**: Option B (`bootstrap/` config) is not yet written;
  Option A (CLI) is the current path.
- **Lambda packaging**: real artifact build/`source_code_hash` wiring is a
  CI responsibility; the module validates with a placeholder zip.

See the full spec for context:
[requirements](../../.kiro/specs/serverless-deployment/requirements.md) ·
[design](../../.kiro/specs/serverless-deployment/design.md) ·
[tasks](../../.kiro/specs/serverless-deployment/tasks.md)
