# Serverless Deployment Guide (AWS, Terraform)

Status: **infrastructure code complete and validated, NOT yet deployed.**

This guide is the pick-up point for deploying the serverless (AWS) mode of the
Strands Agents RAG application. All Terraform has been written and passes
`terraform validate` / `terraform fmt`, but nothing has been applied to AWS yet
because this environment has no AWS credentials and the Terraform remote-state
backend has not been bootstrapped.

Read this top-to-bottom before your first deploy. The ordering matters.

---

## 0. TL;DR — what's done, what's left

Done:
- Application code for both modes (local Ollama/Milvus/FastAPI + serverless
  Bedrock/OpenSearch/Lambda), selected by `DEPLOYMENT_MODE`.
- Full Terraform stack under `infrastructure/terraform/` (six modules:
  networking, data, compute, api, frontend, observability).
- `terraform validate` + `terraform fmt -check` pass for the whole root module.

Left to do before the app runs in AWS (all covered below):
1. Configure AWS credentials.
2. **Bootstrap the Terraform state backend** (S3 bucket + DynamoDB lock table).
   *This is the "backend bucket doesn't exist yet" item.*
3. Build + package the Lambda deployment artifact(s).
4. `terraform init` (real backend) → `plan` → `apply` per environment.
5. Build the React app with serverless env vars and sync it to S3 + invalidate
   CloudFront.
6. Create the OpenSearch indexes (done by the app at runtime) and load the KB.
7. Enable Bedrock model access in the AWS account/region.

---

## 1. What "the backend bucket doesn't exist yet" means

Terraform records everything it creates in a **state file**. For team/prod use,
that state is stored remotely in **S3**, with a **DynamoDB table** used as a lock
so two applies can't run at once. This project configures that in
`infrastructure/terraform/backend.tf`:

```hcl
terraform {
  backend "s3" {
    bucket         = "strands-rag-tfstate"          # S3 bucket holding the state file
    key            = "serverless-deployment/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "strands-rag-tflock"           # DynamoDB table for state locking
    encrypt        = true
  }
}
```

Chicken-and-egg: Terraform cannot create its own state bucket, because it needs
the bucket to exist *before* it can initialize against it. So the state bucket
and lock table are a **one-time bootstrap** you create first.

> This is NOT the application's document bucket. The app bucket
> (`strands-rag-<stage>-documents`, in the `frontend` module) is created by
> Terraform during `apply`. The *backend* bucket (`strands-rag-tfstate`) must
> pre-exist and only stores Terraform's own state.

All validation so far used `terraform init -backend=false`, which skips the
remote backend entirely and just checks the config locally.

---

## 2. Prerequisites

- **Terraform** >= 1.5 (CI/prod should use >= 1.6; see the note in
  `infrastructure/terraform/versions.tf`). Local env here is 1.5.7.
- **AWS CLI** configured with credentials that can create VPC, Lambda, API
  Gateway, Cognito, DynamoDB, OpenSearch Serverless, ElastiCache, S3,
  CloudFront, WAF, IAM, Secrets Manager, and CloudWatch resources.
- **Node.js + npm** (to build the React frontend).
- **Python 3.12** + the project deps (to package the Lambdas).
- **Amazon Bedrock model access** enabled in your target region for
  `anthropic.claude-3-haiku-20240307-v1:0` and `amazon.titan-embed-text-v1`
  (request access in the Bedrock console — this is per-account/per-region and
  easy to forget).

Pick a region. The backend is written for `us-east-1`; if you change it, update
`backend.tf` and the `aws_region` variable.

---

## 3. Bootstrap the Terraform state backend (one time per account)

Create the state bucket and lock table BEFORE the first `terraform init`.
Easiest path is the AWS CLI:

```bash
AWS_REGION=us-east-1
STATE_BUCKET=strands-rag-tfstate
LOCK_TABLE=strands-rag-tflock

# 1. State bucket (versioned + encrypted)
aws s3api create-bucket \
  --bucket "$STATE_BUCKET" \
  --region "$AWS_REGION"
  # NOTE: for regions other than us-east-1 add:
  #   --create-bucket-configuration LocationConstraint="$AWS_REGION"

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

# 2. DynamoDB lock table (must have a String partition key named LockID)
aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$AWS_REGION"
```

If you prefer this as code, create a tiny separate `infrastructure/terraform/bootstrap/`
config (local state, no backend block) that defines just these two resources,
and `apply` it once. Keep it separate from the main stack so the main stack can
safely use the backend it creates.

The names above MUST match `backend.tf`. If you change them, change both.

---

## 4. Package the Lambda deployment artifact

The `compute` module currently builds a tiny placeholder zip so `validate`/`plan`
work without a real artifact. For a real deploy, build the actual package and
point Terraform at it via the module variables
(`lambda_package_path`, `lambda_source_code_hash`).

Rough shape (adjust to your packaging tooling):

```bash
# From the repo root. Produces a zip containing src/ + installed deps.
mkdir -p build/lambda
pip install -r requirements.txt -t build/lambda        # or use a Lambda layer
cp -r src build/lambda/
( cd build/lambda && zip -r ../lambda.zip . )
```

Then pass the path/hash through root variables (wire these into the `compute`
module inputs if you deploy from CI):

```hcl
# example extra vars at apply time
lambda_package_path     = "build/lambda.zip"
lambda_source_code_hash = filebase64sha256("build/lambda.zip")
```

Both Lambda functions (chat `agentcore_handler.lambda_handler` and indexing
`indexing_handler.lambda_handler`) ship from the same package.

> Serverless-only Python deps that must be in the package:
> `boto3` (usually present in the Lambda runtime), `opensearch-py`, `redis`,
> `msgpack`, `numpy`. These are lazily imported so local mode never needs them,
> but the Lambda package does.

---

## 5. Deploy the infrastructure

```bash
cd infrastructure/terraform

# First real init — connects to the S3 backend created in step 3.
terraform init

# Review the plan for your environment.
terraform plan -var-file=environments/dev.tfvars

# Apply.
terraform apply -var-file=environments/dev.tfvars
```

Repeat with `environments/staging.tfvars` / `environments/prod.tfvars` for other
stages. (If you use one state bucket for all stages, give each stage a distinct
backend `key` or use Terraform workspaces so their states don't collide.)

Useful outputs after apply:
- `api_endpoint` — API Gateway base URL (POST /chat, GET /health)
- `cloudfront_domain` — the SPA URL
- `user_pool_id`, `user_pool_client_id` — Cognito, for the React build
- `documents_bucket_id` — S3 bucket for KB documents + frontend assets
- `opensearch_collection_endpoint` — for app config / index creation

---

## 6. Post-deploy application steps

### 6a. Secrets
Populate the Secrets Manager secrets created by the `compute` module (values are
intentionally NOT stored in Terraform state):
- Tavily API key secret
- Redis credentials secret (if used)

```bash
aws secretsmanager put-secret-value \
  --secret-id <tavily-secret-name-from-output-or-console> \
  --secret-string 'YOUR_TAVILY_KEY'
```

### 6b. OpenSearch indexes
The two indexes (`rag-kb`, `rag-cache`, 768-dim cosine HNSW m=30/ef_construction=200)
are created by the application at runtime via `OpenSearchClient.ensure_indexes()`,
not by Terraform (OpenSearch Serverless doesn't support index mappings in TF).
They are created on first use / first indexing run.

### 6c. Load the knowledge base
Upload documents to the documents bucket under the `documents/` prefix — this
triggers the indexing Lambda (S3 ObjectCreated) which chunks, embeds via Bedrock,
and indexes into `rag-kb`:

```bash
aws s3 cp ./some-doc.pdf s3://<documents_bucket_id>/documents/
```

### 6d. Build + deploy the React frontend
Build with the serverless env vars (so there are no localhost references and
Cognito auth is enabled), then sync to the `frontend/` prefix and invalidate
CloudFront:

```bash
cd chatbots/react-chatbot

REACT_APP_API_URL="https://<api_endpoint>" \
REACT_APP_USER_POOL_ID="<user_pool_id>" \
REACT_APP_USER_POOL_CLIENT_ID="<user_pool_client_id>" \
REACT_APP_AWS_REGION="us-east-1" \
REACT_APP_AUTH_ENABLED="true" \
npm run build

aws s3 sync build/ s3://<documents_bucket_id>/frontend/ --delete
aws cloudfront create-invalidation --distribution-id <cloudfront_distribution_id> --paths '/*'
```

### 6e. Create a user
Sign-up/sign-in flows through the Cognito user pool. Create a test user via the
Cognito console or `aws cognito-idp admin-create-user`.

---

## 7. Known deviations / gotchas (carried from the build)

1. **Terraform version floor**: `versions.tf` sets `required_version >= 1.5.0`
   (design asked for >= 1.6.0) because the build environment had 1.5.7. Bump to
   `>= 1.6.0` for CI/prod.
2. **AWS provider pin**: pinned `~> 5.95` (design mentioned `~> 5.60`) to satisfy
   the registry VPC module's `>= 5.79` floor. Still the 5.x line.
3. **Bedrock embedding dimension**: Titan returns 1536-dim; the OpenSearch index
   is 768-dim to match the local `nomic-embed-text:v1.5` dimension. A
   deterministic PCA projection (built-in, or a matrix from
   `BEDROCK_PCA_MATRIX_URI`) reduces 1536→768. If you change embedding models,
   revisit this.
4. **WAF rate limit**: Req 6.4 says "100 rps". API Gateway stage throttling is
   the primary 100-rps enforcement; the WAF rate-based rule is defense-in-depth
   over a 60s window (~6000 req/IP/min). Tune to taste.
5. **Lambda packaging**: placeholder zip is used for validation. A real artifact
   (step 4) is required before apply actually runs working functions.
6. **No `terraform apply` has ever run** — the very first apply will create ~all
   resources and may take a while (CloudFront + OpenSearch Serverless + Redis are
   the slow ones).

---

## 8. Teardown

```bash
cd infrastructure/terraform
terraform destroy -var-file=environments/dev.tfvars
```

Empty the S3 documents bucket first if `destroy` complains about a non-empty
bucket. The bootstrap state bucket/lock table (step 3) are NOT managed by this
stack; delete them manually if you want them gone.

---

## 9. File map

```
infrastructure/terraform/
├── backend.tf          # S3 remote state + DynamoDB lock (bootstrap required)
├── versions.tf         # terraform + aws provider pins
├── variables.tf        # root inputs (stage, region, models, node types, ...)
├── main.tf             # composes the six modules
├── outputs.tf          # api_endpoint, cloudfront_domain, user_pool_*, ...
├── environments/       # dev.tfvars, staging.tfvars, prod.tfvars
└── modules/
    ├── networking/     # VPC, subnets, VPC endpoints, security groups
    ├── data/           # DynamoDB tables, OpenSearch Serverless, ElastiCache Redis
    ├── compute/        # chat + indexing Lambdas, least-privilege IAM, secrets
    ├── api/            # HTTP API Gateway, Cognito, WAF
    ├── frontend/       # S3 (docs + SPA), CloudFront
    └── observability/  # CloudWatch log groups + errors/total alarm, X-Ray notes
```
