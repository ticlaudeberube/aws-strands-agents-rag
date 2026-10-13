# AWS Strands Agents RAG

A dual-mode RAG system that currently supports both local development and AWS serverless deployment.

- Local: FastAPI + Ollama + a vector DB (currently Milvus)
- Serverless AWS: Lambda + AgentCore + Bedrock + OpenSearch Serverless

## Start here

- [docs/HOW_TO.md](docs/HOW_TO.md) — practical setup and usage guide
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — setup steps for both modes
- [docs/SERVERLESS_LOCAL.md](docs/SERVERLESS_LOCAL.md) — run serverless mode locally (real Bedrock + local OpenSearch/Redis), CLI and GUI
- [docs/AWS_DEPLOYMENT_GAPS.md](docs/AWS_DEPLOYMENT_GAPS.md) — what stands between local serverless and a real AWS deploy
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — runtime architecture and routing
- [docs/API_SERVER.md](docs/API_SERVER.md) — API contract and endpoints
- [docs/CHATBOT_GUI_FEATURES.md](docs/CHATBOT_GUI_FEATURES.md) — frontend feature reference
- [docs/INDEX.md](docs/INDEX.md) — active doc index

## Quick start

### Local mode

```bash
cd docker
docker-compose up -d
cd ..
python api_server.py
```

### Serverless mode

```bash
export DEPLOYMENT_MODE=serverless
# fill in AWS / Bedrock / OpenSearch values in .env
```

To exercise serverless mode **locally** (real Bedrock + local OpenSearch/Redis,
no AWS deploy), see [docs/SERVERLESS_LOCAL.md](docs/SERVERLESS_LOCAL.md).

The AWS infrastructure is defined as Terraform under
[`infrastructure/terraform/`](infrastructure/terraform/). It has been written and
validated but **not yet deployed** — a one-time remote-state backend bootstrap
(an S3 state bucket + DynamoDB lock table) is required before the first
`terraform init`. The full prerequisites, backend bootstrap, and
deploy/teardown workflow are documented in
[infrastructure/terraform/DEPLOYMENT.md](infrastructure/terraform/DEPLOYMENT.md).

## Core runtime flow

```text
User query
  -> TopicChecker
  -> SecurityChecker
  -> RAGWorker
     -> retrieval backend
     -> answer + sources
```

## Supported modes

| Mode | Use case | Active stack |
|------|----------|--------------|
| Local | development and debugging | FastAPI, Ollama, vector DB (currently Milvus) |
| Serverless AWS | production deployment | Lambda, AgentCore, Bedrock, OpenSearch |

The source of truth for mode selection is `DEPLOYMENT_MODE` in `.env` and `src/config/settings.py`.

See [docs/HOW_TO.md](docs/HOW_TO.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the verified setup and architecture.

## Deploying to AWS

The serverless infrastructure (Terraform) and its deployment runbook live in
[infrastructure/terraform/DEPLOYMENT.md](infrastructure/terraform/DEPLOYMENT.md).
Start there before attempting a cloud deploy — it covers AWS prerequisites, the
required remote-state backend bootstrap, Lambda packaging, and the
`init → plan → apply` workflow.
