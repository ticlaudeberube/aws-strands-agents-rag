# Requirements Document

## Introduction

This feature covers the serverless AWS deployment of the existing Strands Agents RAG application. The local stack (Ollama + Milvus + FastAPI + React chatbot) must be ported to a fully managed, cost-efficient serverless architecture on AWS using: Lambda + AgentCore + Bedrock + OpenSearch Serverless + API Gateway + DynamoDB + ElastiCache Redis + Cognito + CloudFront + S3. The existing `agentcore_handler.py` Lambda entrypoint is the execution target. All existing capabilities — 4-layer caching, Tavily web search fallback, three-tier answer routing, and the React chatbot frontend — must be preserved and adapted for the stateless, distributed cloud environment.

---

## Glossary

- **AgentCore**: AWS AgentCore runtime that orchestrates the Strands agent execution, tool invocation, and state management inside Lambda.
- **Bedrock**: AWS Bedrock managed LLM service replacing local Ollama (model: Claude 3 Haiku for fast inference, Claude 3 Sonnet for generation).
- **CloudFront_Distribution**: AWS CloudFront CDN that serves the React frontend assets from S3.
- **Cognito_User_Pool**: Amazon Cognito service managing user authentication and JWT token issuance.
- **DynamoDB_Session_Table**: DynamoDB table storing multi-turn conversation history, session metadata, and optional cache entries with TTL.
- **DynamoDB_Analytics_Table**: DynamoDB table (with GSI) storing per-query analytics for popular question tracking.
- **ElastiCache_Redis**: AWS ElastiCache Redis cluster providing the distributed embedding cache (Layer 2) and search result cache (Layer 3).
- **IaC**: Infrastructure as Code — Terraform configuration (HCL) defining all cloud resources declaratively.
- **Lambda_Handler**: The `src/agents/agentcore_handler.py` AWS Lambda function entrypoint that processes chat requests.
- **OpenSearch_Collection**: Amazon OpenSearch Serverless vector collection replacing local Milvus, storing document embeddings and the semantic response cache (Layer 4).
- **RAG_Pipeline**: The three-tier answer routing pipeline (Cache → KB → Web Search) adapted for stateless Lambda execution.
- **React_Frontend**: The existing React chatbot UI deployed to S3 + CloudFront instead of local FastAPI static serving.
- **Redis_Cache**: ElastiCache Redis cluster backing Layer 2 (embedding cache) and Layer 3 (search result cache) of the distributed cache strategy.
- **S3_Document_Bucket**: Amazon S3 bucket storing source documents, embedding snapshots, and React frontend build artifacts.
- **Terraform_Configuration**: Terraform HCL configuration (root module, child modules, variables, and provider definitions) defining Lambda functions, API Gateway, DynamoDB, and supporting resources, with remote state stored in an S3 backend and locked via DynamoDB.
- **Secrets_Manager**: AWS Secrets Manager storing Tavily API key, Redis credentials, OpenSearch access policies, and other runtime secrets.
- **Tavily_Client**: The existing Tavily web search integration (Layer 3 fallback) adapted to call the Tavily API from Lambda.
- **TopicChecker**: The Strands agent node that validates whether an incoming query is in-scope (about vector databases, RAG, embeddings, etc.).
- **SecurityChecker**: The Strands agent node that detects prompt injection, jailbreaks, and malicious query intent.
- **RAGWorker**: The Strands agent node that performs semantic retrieval from OpenSearch and answer generation via Bedrock.
- **VPC**: AWS Virtual Private Cloud that houses Lambda, ElastiCache Redis, and OpenSearch Serverless in private subnets.
- **WAF**: AWS Web Application Firewall attached to API Gateway for rate limiting and DDoS protection.

---

## Requirements

### Requirement 1: Lambda Entrypoint and AgentCore Integration

**User Story:** As a backend developer, I want the existing `agentcore_handler.py` Lambda entrypoint to fully implement the AgentCore RAG pipeline, so that chat requests from API Gateway are processed end-to-end in a serverless function.

#### Acceptance Criteria

1. WHEN API Gateway receives a POST request to `/chat`, THE Lambda_Handler SHALL parse the request body and extract the `question`, `session_id`, and optional `force_web_search` fields.
2. WHEN the Lambda_Handler is invoked, THE AgentCore SHALL initialize the TopicChecker, SecurityChecker, and RAGWorker Strands agents with Bedrock as the LLM provider.
3. WHEN a request is processed, THE Lambda_Handler SHALL retrieve conversation history from the DynamoDB_Session_Table using the provided `session_id` before invoking the AgentCore.
4. WHEN the RAG_Pipeline completes, THE Lambda_Handler SHALL persist the question and answer to the DynamoDB_Session_Table with a TTL of 24 hours.
5. IF the Lambda_Handler encounters an unhandled exception, THEN THE Lambda_Handler SHALL return an HTTP 500 response with a structured error body containing `error_code` and `message` fields, and log the full stack trace to CloudWatch.
6. THE Lambda_Handler SHALL complete execution within 30 seconds for cache-hit responses and within 90 seconds for full RAG pipeline responses, staying within the Lambda timeout limit.

---

### Requirement 2: Three-Tier Answer Routing (Stateless Adaptation)

**User Story:** As a product owner, I want the three-tier answer routing (Cache → KB → Web Search) preserved in the serverless architecture, so that response latency and quality are maintained without in-memory state.

#### Acceptance Criteria

1. WHEN a query arrives, THE RAG_Pipeline SHALL first check the distributed cache (ElastiCache_Redis Layer 2/3 and OpenSearch_Collection Layer 4) before invoking Bedrock.
2. WHEN a cached response with non-empty content is found with semantic similarity ≥ 0.92, THE RAG_Pipeline SHALL return the cached answer without calling Bedrock.
3. WHEN the query contains temporal keywords (e.g., "latest", "recent", "2024", "today", "trending"), THE RAG_Pipeline SHALL bypass the cache and perform a fresh OpenSearch vector search.
4. WHEN the KB search result has average relevance below 0.15, THE RAG_Pipeline SHALL automatically invoke the Tavily_Client web search fallback and return web-sourced results.
5. WHEN a cached response entry exists but contains an empty answer, THE RAG_Pipeline SHALL trigger Tavily_Client web search and return the web results.
6. WHEN `force_web_search` is set to `true` in the request, THE RAG_Pipeline SHALL bypass cache and KB and invoke Tavily_Client directly.
7. THE TopicChecker SHALL reject out-of-scope queries and return a structured rejection response without invoking the RAGWorker, achieving early exit for at least 60% of invalid queries.
8. THE SecurityChecker SHALL reject queries containing prompt injection patterns and return a structured rejection response without invoking the RAGWorker.

---

### Requirement 3: Distributed Cache Strategy (4-Layer)

**User Story:** As a performance engineer, I want the 4-layer cache adapted for distributed Lambda execution, so that cache hits remain fast across stateless invocations.

#### Acceptance Criteria

1. THE Redis_Cache SHALL store query embedding vectors (Layer 2) with a TTL of 3600 seconds, accessible to all Lambda invocations in the same VPC.
2. THE Redis_Cache SHALL store OpenSearch search result payloads (Layer 3) with a TTL of 86400 seconds.
3. THE OpenSearch_Collection SHALL store the semantic response cache entries (Layer 4) as a dedicated index with cosine similarity scoring.
4. WHEN a query embedding is requested, THE RAG_Pipeline SHALL check the Redis_Cache before calling Bedrock embedding API, returning the cached embedding if a key match exists.
5. WHEN an OpenSearch search result is cached and the query embedding matches within a 0.05 L2 distance, THE RAG_Pipeline SHALL return the cached search results from Redis_Cache without querying OpenSearch.
6. IF the Redis_Cache is unavailable, THEN THE RAG_Pipeline SHALL proceed without Layer 2 and Layer 3 caching and log a CloudWatch warning metric `cache/redis_unavailable`.
7. IF the OpenSearch_Collection is unreachable, THEN THE RAG_Pipeline SHALL skip Layer 4 semantic cache and proceed directly to KB vector search, logging a CloudWatch warning metric `cache/opensearch_unavailable`.

---

### Requirement 4: Vector Search via OpenSearch Serverless

**User Story:** As a data engineer, I want the Milvus vector search replaced with Amazon OpenSearch Serverless, so that vector retrieval is fully managed and scales automatically without infrastructure management.

#### Acceptance Criteria

1. THE OpenSearch_Collection SHALL store document embeddings with 768-dimensional vectors (matching the existing `nomic-embed-text:v1.5` embedding dimension) in a k-NN index using cosine similarity.
2. WHEN a vector search is performed, THE RAGWorker SHALL query the OpenSearch_Collection with a top-k of 10 by default and return documents ranked by cosine similarity score.
3. THE OpenSearch_Collection SHALL support separate indexes for the knowledge base documents and the semantic response cache (Layer 4).
4. WHEN `top_k` is specified in the request and the value is between 1 and 50 inclusive, THE RAGWorker SHALL use the provided value for the vector search. IF `top_k` exceeds 50 or is less than 1, THEN THE Lambda_Handler SHALL reject the request with HTTP 400 and an error body containing `error_code: "INVALID_TOP_K"` before invoking the RAGWorker.
5. THE OpenSearch_Collection SHALL be configured within the VPC and accessible only to Lambda via VPC endpoint, with no public internet access.
6. WHERE HNSW_INDEX_TYPE is configured, THE OpenSearch_Collection SHALL apply the HNSW algorithm with `m=30` and `ef_construction=200` to match the existing Milvus HNSW configuration.

---

### Requirement 5: LLM Inference via AWS Bedrock

**User Story:** As a cloud architect, I want Ollama replaced with AWS Bedrock for LLM inference, so that the system uses a fully managed, serverless LLM service without self-hosted model infrastructure.

#### Acceptance Criteria

1. THE RAGWorker SHALL call Bedrock to generate answer text using `anthropic.claude-3-haiku-20240307-v1:0` as the default inference model.
2. THE RAGWorker SHALL call Bedrock to generate query embeddings using `amazon.titan-embed-text-v1` as the embedding model, producing 1536-dimensional vectors.
3. WHEN the Bedrock embedding model returns vectors of 1536 dimensions and OpenSearch is configured for 768-dimensional vectors, THE RAG_Pipeline SHALL apply dimensionality reduction to align vector dimensions before indexing or querying.
4. WHERE Bedrock_Model_Override is configured, THE RAGWorker SHALL use the specified model ID instead of the default, allowing production tuning without code changes.
5. IF Bedrock returns a throttling error (HTTP 429), THEN THE RAGWorker SHALL retry the call up to 3 times with exponential backoff starting at 500ms.
6. THE RAGWorker SHALL include the retrieved document context in the Bedrock prompt, formatted with source titles and content chunks matching the existing prompt template structure.

---

### Requirement 6: API Gateway and Request Routing

**User Story:** As a frontend developer, I want an API Gateway to expose the Lambda-backed REST endpoints, so that the React chatbot can send requests over HTTPS with authentication.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose a REST endpoint `POST /chat` that invokes the Lambda_Handler synchronously and returns the response.
2. THE API_Gateway SHALL expose a REST endpoint `GET /health` that returns HTTP 200 with `{"status": "healthy"}` without invoking the Lambda_Handler.
3. THE API_Gateway SHALL enforce Cognito_User_Pool JWT authorization on the `/chat` endpoint, rejecting unauthenticated requests with HTTP 401.
4. THE API_Gateway SHALL apply a rate limit of 100 requests per second per API key and return HTTP 429 for requests exceeding the limit.
5. THE API_Gateway SHALL enable CORS for the CloudFront_Distribution origin domain, allowing `Content-Type` and `Authorization` headers.
6. IF the Lambda_Handler returns an error response, THEN THE API_Gateway SHALL propagate the error body and HTTP status code unchanged to the client.

---

### Requirement 7: User Authentication via Cognito

**User Story:** As a security engineer, I want user authentication managed by Amazon Cognito, so that only authenticated users can access the chat API and frontend.

#### Acceptance Criteria

1. THE Cognito_User_Pool SHALL support user sign-up with email and password, enforcing a minimum password length of 12 characters, at least one uppercase letter, one number, and one special character.
2. WHEN a user signs in successfully, THE Cognito_User_Pool SHALL issue a JWT access token with a 1-hour expiry.
3. THE API_Gateway SHALL validate Cognito JWT tokens on every `/chat` request and reject expired or malformed tokens with HTTP 401.
4. THE React_Frontend SHALL use the Cognito Hosted UI or Amplify Auth for the sign-in flow and store the JWT token in memory (not localStorage) to prevent XSS token theft.
5. IF a Cognito JWT token is expired or malformed, THEN THE React_Frontend SHALL automatically attempt to refresh the session using the Cognito refresh token. IF the refresh token is also invalid or absent, THEN THE React_Frontend SHALL redirect the user to the sign-in page.

---

### Requirement 8: React Frontend Deployment via CloudFront and S3

**User Story:** As a frontend engineer, I want the React chatbot deployed to CloudFront + S3, so that users access the UI globally with low latency over HTTPS without a running FastAPI server.

#### Acceptance Criteria

1. THE React_Frontend build artifacts SHALL be uploaded to the S3_Document_Bucket under a dedicated `/frontend/` prefix and served via CloudFront_Distribution.
2. THE CloudFront_Distribution SHALL enforce HTTPS-only access and redirect HTTP requests to HTTPS.
3. THE CloudFront_Distribution SHALL be configured with a default TTL of 86400 seconds for static assets and `no-store` cache-control for `index.html` to ensure fresh deployments are reflected immediately.
4. THE React_Frontend SHALL read the API Gateway endpoint URL from a build-time environment variable `REACT_APP_API_URL`, eliminating hardcoded localhost references.
5. WHILE the request path does not match a known static asset extension (`.js`, `.css`, `.png`, `.ico`, `.svg`, `.woff2`), THE CloudFront_Distribution SHALL serve `index.html` to support single-page application client-side routing.

---

### Requirement 9: Document Indexing Pipeline

**User Story:** As a knowledge engineer, I want an automated document indexing pipeline that loads source documents into OpenSearch Serverless, so that the knowledge base is populated and kept up to date in the cloud environment.

#### Acceptance Criteria

1. WHEN a document file is uploaded to the S3_Document_Bucket under the `/documents/` prefix, THE Indexing_Pipeline SHALL automatically trigger processing via an S3 event notification.
2. THE Indexing_Pipeline SHALL split each document into chunks with a maximum length of 400 tokens, matching the existing `MAX_CHUNK_LENGTH` configuration.
3. THE Indexing_Pipeline SHALL generate embeddings for each chunk using the Bedrock embedding model and index the resulting vectors into the OpenSearch_Collection knowledge base index.
4. WHEN the Indexing_Pipeline detects a document whose S3 object key and ETag match an already-indexed entry in DynamoDB_Analytics_Table, THE Indexing_Pipeline SHALL skip all re-indexing operations (no embedding calls, no OpenSearch writes) and THEN log a CloudWatch info event `indexing/document_skipped`. IF the skip action was not enforced prior to logging (i.e., the document was re-indexed before or during the log event), THEN THE Indexing_Pipeline SHALL emit a CloudWatch error metric `indexing/skip_enforcement_failure` and treat the occurrence as a defect.
5. THE Indexing_Pipeline SHALL record the document title, S3 URI, chunk count, and index timestamp in the DynamoDB_Analytics_Table for auditing.

---

### Requirement 10: Tavily Web Search Integration

**User Story:** As an end user, I want Tavily web search to work in the serverless environment exactly as it does locally, so that current information and fallback answers are available when the knowledge base is insufficient.

#### Acceptance Criteria

1. THE Tavily_Client SHALL retrieve the Tavily API key from Secrets_Manager at Lambda cold start and cache it in the Lambda execution environment for the duration of the warm invocation.
2. WHEN the RAG_Pipeline triggers Tavily web search, THE Tavily_Client SHALL complete the Tavily API call within 10 seconds and return results.
3. IF Tavily returns no results or times out, THEN THE RAG_Pipeline SHALL return the best available KB answer with a `web_search_unavailable` flag in the response metadata.
4. THE Tavily_Client SHALL pass the `WEB_SEARCH_FALLBACK_THRESHOLD` of 0.15 to determine automatic fallback, matching the existing local behavior.
5. WHEN web search results are returned, THE Lambda_Handler SHALL include `sources` with URLs and timestamps in the response body, matching the existing response schema.

---

### Requirement 11: Infrastructure as Code (Terraform)

**User Story:** As a DevOps engineer, I want all AWS resources defined in a Terraform configuration, so that the entire serverless deployment can be provisioned, updated, and torn down repeatably.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL define all required resources: Lambda_Handler, API Gateway, Cognito_User_Pool, DynamoDB_Session_Table, DynamoDB_Analytics_Table, ElastiCache_Redis, OpenSearch_Collection, S3_Document_Bucket, CloudFront_Distribution, Secrets_Manager secrets, VPC, subnets, and security groups.
2. THE Terraform_Configuration SHALL parameterize environment-specific values (stage name, Bedrock model ID, Redis node type, OpenSearch capacity) via Terraform variables and workspaces (or per-environment `tfvars` files) so that the same configuration deploys to `dev`, `staging`, and `prod` environments without code changes.
3. WHEN `terraform apply` is executed with valid AWS credentials and variables after a `terraform plan` has been reviewed, THE Terraform_Configuration SHALL provision all resources without manual AWS Console intervention.
4. THE Terraform_Configuration SHALL configure the Lambda_Handler with a VPC configuration connecting it to the private subnets containing ElastiCache_Redis and the VPC endpoint for OpenSearch Serverless.
5. THE Terraform_Configuration SHALL grant the Lambda_Handler execution role only the minimum IAM permissions required: Bedrock `InvokeModel`, DynamoDB CRUD on both tables, ElastiCache read/write, OpenSearch Serverless HTTP access, S3 read on the document bucket, Secrets_Manager read on Tavily and cache secrets.
6. THE Terraform_Configuration SHALL configure DynamoDB_Session_Table and DynamoDB_Analytics_Table with `PAY_PER_REQUEST` billing mode and TTL enabled on the `ttl` attribute.
7. THE Terraform_Configuration SHALL store Terraform state in a remote backend using an S3 bucket for state storage and a DynamoDB table for state locking, so that the deployment is safe for concurrent team use.
8. THE Terraform_Configuration SHALL pin provider versions and module versions using `required_providers` and explicit version constraints.

---

### Requirement 12: Observability and Monitoring

**User Story:** As a site reliability engineer, I want comprehensive observability built into the serverless deployment, so that cache hit rates, latency, errors, and costs can be monitored and alerted on.

#### Acceptance Criteria

1. THE Lambda_Handler SHALL emit structured JSON logs to CloudWatch with fields: `request_id`, `session_id`, `tier_used` (cache/kb/websearch), `latency_ms`, `cache_hit`, and `error_code` (if applicable).
2. THE Lambda_Handler SHALL emit custom CloudWatch metrics for: `cache/hit_rate`, `cache/miss_rate`, `rag/latency_p50`, `rag/latency_p99`, `websearch/invocation_count`, and `errors/total`.
3. THE Terraform_Configuration SHALL configure a CloudWatch alarm that triggers when `errors/total` exceeds 10 in a 5-minute window.
4. THE Lambda_Handler SHALL use AWS X-Ray active tracing for end-to-end distributed tracing of each request through API Gateway, Lambda, Bedrock, Redis, and OpenSearch.
5. WHEN Lambda cold start occurs, THE Lambda_Handler SHALL log a `cold_start=true` field in the structured log entry to allow cold start frequency monitoring.
