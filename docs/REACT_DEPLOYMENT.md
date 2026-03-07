# React Chatbot Deployment Guide

Comprehensive guide for deploying the React chatbot in different environments: Docker, Local, and Serverless with AgentCore.

## Overview

The React chatbot can be deployed as:
1. **Local Development** - `npm start` (development server)
2. **Docker Container** - Built and run in isolation
3. **Static Hosting** - Nginx/S3 (production)
4. **Serverless with AgentCore** - AWS Lambda + CloudFront

---

## 1. Local Development

### Quick Start

```bash
# Navigate to react app
cd chatbots/react-chatbot

# Install dependencies
npm install

# Start development server (port 3000 by default)
npm start
```

**Configuration:**
```bash
# .env (chatbots/react-chatbot/.env)
REACT_APP_API_PORT=8000
REACT_APP_API_HOST=localhost
```

If API is on different port:
```bash
# Terminal
REACT_APP_API_PORT=8001 npm start
```

### Prerequisites
- Node.js 14+ and npm 6+
- Backend API running (`python api_server.py` or Docker)

### Development Server
- Runs on `http://localhost:3000`
- Hot reload on file changes
- CORS proxy built-in (through React Scripts)

### Testing API Connection
```bash
# In React app console or terminal
curl http://localhost:8000/health
```

---

## 2. Docker Deployment

### 2A. Multi-Stage Docker Build (Recommended)

Create [docker/Dockerfile.react](docker/Dockerfile.react) for production:

```dockerfile
# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY chatbots/react-chatbot/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY chatbots/react-chatbot/src ./src
COPY chatbots/react-chatbot/public ./public

# Build React app
RUN npm run build

# Production stage - serve with Nginx
FROM nginx:alpine

# Copy nginx config
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built app from builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Copy .env to container for runtime config
COPY chatbots/react-chatbot/.env /usr/share/nginx/html/.env

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

### 2B. Nginx Configuration

Create [docker/nginx.conf](docker/nginx.conf):

```nginx
server {
    listen 3000;
    server_name _;

    root /usr/share/nginx/html;
    index index.html index.htm;

    # Serve static files with caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API proxy (optional - for CORS handling)
    location /api/ {
        proxy_pass http://host.docker.internal:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Streaming support
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # React Router: serve index.html for all non-static requests
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
    }
}
```

### 2C. Update docker-compose.yml

Add React service to [docker/docker-compose.yml](docker/docker-compose.yml):

```yaml
services:
  # ... existing services (milvus, minio, etcd, rag-api) ...

  # React Chatbot UI
  react-chatbot:
    container_name: rag-react
    build:
      context: ..
      dockerfile: docker/Dockerfile.react
    environment:
      - REACT_APP_API_PORT=8000
      - REACT_APP_API_HOST=host.docker.internal
    ports:
      - "3000:3000"
    depends_on:
      rag-api:
        condition: service_healthy
    mem_limit: 512m
    memswap_limit: 512m
    cpus: 1.0
    init: true
    networks:
      - rag-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### 2D. Build and Run

```bash
# Build React Docker image
docker build -f docker/Dockerfile.react -t rag-react:latest .

# Run with docker-compose (includes all services)
cd docker
docker compose up -d

# Verify
docker ps | grep rag-react
curl http://localhost:3000
```

### Docker Production Considerations

- **Base Image:** nginx:alpine (11MB vs 1GB+ for node:latest)
- **Multi-stage:** Only includes production dependencies
- **Health Checks:** Ensures container readiness
- **Resource Limits:** 512MB RAM, 1 CPU (adjust as needed)
- **Restart Policy:** Auto-restart on failure

---

## 3. Serverless Deployment with AgentCore

### 3A. Architecture Overview

```
┌─────────────────┐
│  React App      │ (Static HTML/JS)
│  (CloudFront)   │──┐
└─────────────────┘  │
                     │
                     ├──→ API Gateway + Lambda
                     │    (AgentCore-wrapped handler)
                     │
                     └──→ CloudFront
                          (Distribution)
```

### 3B. Lambda Handler with AgentCore

Create [serverless/lambda_handler.py](serverless/lambda_handler.py):

```python
"""
AWS Lambda handler for RAG Agent using AgentCore framework.
Serves as the backend for the serverless React chatbot deployment.
"""

import json
import os
import logging
from typing import Any, Dict
from datetime import datetime

# AgentCore imports
try:
    from agent_framework import AgentCore, Tool, Context
    AGENTCORE_AVAILABLE = True
except ImportError:
    AGENTCORE_AVAILABLE = False
    logging.warning("AgentCore not available - falling back to standard mode")

# RAG imports
from src.agents.strands_rag_agent import StrandsRAGAgent
from src.config.settings import get_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Global agent instance (reused across Lambda invocations)
_agent = None
_agentcore_agent = None

def initialize_agent():
    """Initialize RAG agent on cold start."""
    global _agent, _agentcore_agent

    if _agent is None:
        settings = get_settings()
        _agent = StrandsRAGAgent(settings)
        logger.info("✓ StrandsRAGAgent initialized")

        if AGENTCORE_AVAILABLE:
            _agentcore_agent = AgentCore(
                agent_name="RAGAgent",
                description="Retrieval-Augmented Generation agent for knowledge base queries",
                agent_instance=_agent
            )
            logger.info("✓ AgentCore wrapper initialized")

    return _agent

def format_response(body: Dict[str, Any], status_code: int = 200) -> Dict:
    """Format Lambda response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGINS", "*"),
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

def lambda_handler(event, context):
    """
    Main Lambda handler for RAG Agent API.

    Supports:
    - Health checks: GET /health
    - Chat completions: POST /v1/chat/completions
    - Streaming: Server-Sent Events (SSE)
    """

    try:
        # Parse request
        http_method = event.get("httpMethod", "GET")
        path = event.get("path", "/")
        body = json.loads(event.get("body", "{}")) if event.get("body") else {}

        # CORS preflight
        if http_method == "OPTIONS":
            return format_response({})

        # Initialize agent on first request
        agent = initialize_agent()

        # Health check endpoint
        if path == "/health" and http_method == "GET":
            return format_response({
                "status": "ok",
                "model": "rag-agent-serverless",
                "timestamp": datetime.utcnow().isoformat(),
                "agentcore_available": AGENTCORE_AVAILABLE,
            })

        # Chat completions endpoint
        if path == "/v1/chat/completions" and http_method == "POST":
            return handle_chat_completion(agent, body, context)

        # 404 - Not found
        return format_response({"error": "Endpoint not found"}, 404)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return format_response(
            {"error": str(e), "type": type(e).__name__},
            500
        )

def handle_chat_completion(agent, request_body: Dict, lambda_context) -> Dict:
    """Handle chat completion requests (non-streaming)."""

    try:
        # Extract request parameters
        messages = request_body.get("messages", [])
        collection = request_body.get("collection_name", "milvus_rag_collection")
        stream = request_body.get("stream", False)

        # Get user question (last message)
        if not messages:
            return format_response({"error": "No messages provided"}, 400)

        user_message = messages[-1].get("content", "")

        if not user_message:
            return format_response({"error": "Empty message"}, 400)

        logger.info(f"Processing query: {user_message[:100]}...")

        # Generate answer
        answer, sources = agent.answer_question(
            collection_name=collection,
            question=user_message,
            top_k=5
        )

        # Format response (compatible with OpenAI format)
        response = {
            "id": f"chatcmpl-{lambda_context.request_id}",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "model": "rag-agent-serverless",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_message.split()),
                "completion_tokens": len(answer.split()),
                "total_tokens": len(user_message.split()) + len(answer.split()),
            },
            "sources": sources if sources else [],
        }

        if not stream:
            return format_response(response)

        # Streaming response (chunked)
        return handle_streaming_response(answer, sources, lambda_context)

    except Exception as e:
        logger.error(f"Chat completion error: {e}", exc_info=True)
        return format_response({"error": str(e)}, 500)

def handle_streaming_response(answer: str, sources: list, lambda_context) -> Dict:
    """
    Handle streaming responses.
    Note: Lambda doesn't support true streaming (response buffering required).
    Consider API Gateway with WebSocket for real streaming.
    """

    # For Lambda, return chunked response as multiple completion objects
    chunks = [answer[i:i+50] for i in range(0, len(answer), 50)]

    response_body = {
        "id": f"chatcmpl-{lambda_context.request_id}",
        "object": "text_completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": "rag-agent-serverless",
        "chunks": chunks,
        "full_text": answer,
        "sources": sources,
    }

    return format_response(response_body)
```

### 3C. AWS SAM Template

Create [serverless/template.yaml](serverless/template.yaml) for deployment:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2013-08-31

Description: 'Serverless RAG Agent with React Chatbot Frontend'

Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, staging, prod]
    Description: Deployment environment

  MilvusHost:
    Type: String
    Default: milvus.example.com
    Description: External Milvus host (must be accessible from Lambda)

  OllamaHost:
    Type: String
    Default: ollama.example.com
    Description: External Ollama host (must be accessible from Lambda)

Globals:
  Function:
    Runtime: python3.11
    Timeout: 60
    MemorySize: 3008
    Environment:
      Variables:
        MILVUS_HOST: !Ref MilvusHost
        OLLAMA_HOST: !Ref OllamaHost
        ALLOWED_ORIGINS: '*'

Resources:
  # Lambda execution role
  LambdaExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        - arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole

  # Lambda function for RAG API
  RAGAgentFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub 'rag-agent-${Environment}'
      CodeUri: ./
      Handler: lambda_handler.lambda_handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Description: RAG Agent API handler
      Tags:
        Environment: !Ref Environment
        Project: RAG-Chatbot

  # API Gateway
  RAGAgentAPI:
    Type: AWS::Serverless::Api
    Properties:
      StageName: !Ref Environment
      Name: !Sub 'rag-agent-api-${Environment}'
      Description: RAG Agent API Gateway
      Cors:
        AllowMethods: "'GET,POST,OPTIONS'"
        AllowHeaders: "'Content-Type'"
        AllowOrigin: "'*'"

  # Lambda integration
  RAGAgentIntegration:
    Type: AWS::ApiGateway::Resource
    Properties:
      RestApiId: !Ref RAGAgentAPI
      ParentId: !GetAtt RAGAgentAPI.RootResourceId
      PathPart: '{proxy+}'

  # API Gateway methods
  ApiGatewayMethod:
    Type: AWS::ApiGateway::Method
    Properties:
      RestApiId: !Ref RAGAgentAPI
      ResourceId: !Ref RAGAgentIntegration
      HttpMethod: ANY
      AuthorizationType: NONE
      Integration:
        Type: AWS_PROXY
        IntegrationHttpMethod: POST
        Uri: !Sub 'arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${RAGAgentFunction.Arn}/invocations'

  # Lambda permission for API Gateway
  ApiGatewayInvokePermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref RAGAgentFunction
      Action: lambda:InvokeFunction
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${RAGAgentAPI}/*/*'

  # S3 bucket for React frontend
  ReactAppBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub 'rag-chatbot-${Environment}-${AWS::AccountId}'
      VersioningConfiguration:
        Status: Enabled
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  # CloudFront distribution
  CloudFrontDistribution:
    Type: AWS::CloudFront::Distribution
    Properties:
      DistributionConfig:
        Enabled: true
        Origins:
          # S3 origin for React app
          - Id: S3Origin
            DomainName: !GetAtt ReactAppBucket.RegionalDomainName
            S3OriginConfig:
              OriginAccessIdentity: !Sub 'origin-access-identity/cloudfront/${CloudFrontOAI}'

          # API Gateway origin
          - Id: APIOrigin
            DomainName: !Sub '${RAGAgentAPI}.execute-api.${AWS::Region}.amazonaws.com'
            CustomOriginConfig:
              HTTPPort: 80
              OriginProtocolPolicy: https-only

        DefaultCacheBehavior:
          TargetOriginId: S3Origin
          ViewerProtocolPolicy: redirect-to-https
          AllowedMethods: [GET, HEAD, OPTIONS]
          CachePolicyId: '658327ea-f89d-4fab-a63d-7e88639e58f6'  # Managed-CachingOptimized

        CacheBehaviors:
          # API Gateway cache behavior
          - PathPattern: '/api/*'
            TargetOriginId: APIOrigin
            ViewerProtocolPolicy: https-only
            AllowedMethods: [GET, HEAD, POST, PUT, DELETE, PATCH, OPTIONS]
            CachePolicyId: '4135ea3d-c35d-46eb-81d7-reeSJHnjPDA'  # Managed-CachingDisabled
            OriginRequestPolicyId: 'b689b0a8-53d0-40ab-baf2-68738e2966ac'  # Managed-AllViewerExceptHostHeader

Outputs:
  ReactAppBucketName:
    Description: S3 bucket for React app
    Value: !Ref ReactAppBucket
    Export:
      Name: !Sub '${AWS::StackName}-ReactBucket'

  CloudFrontURL:
    Description: CloudFront distribution URL
    Value: !GetAtt CloudFrontDistribution.DomainName
    Export:
      Name: !Sub '${AWS::StackName}-CloudFrontURL'

  APIEndpoint:
    Description: API Gateway endpoint
    Value: !Sub 'https://${RAGAgentAPI}.execute-api.${AWS::Region}.amazonaws.com/${Environment}'
    Export:
      Name: !Sub '${AWS::StackName}-APIEndpoint'
```

### 3D. Deployment Steps

```bash
# 1. Package Lambda function
sam build

# 2. Deploy (creates all AWS resources)
sam deploy \
  --stack-name rag-agent-serverless \
  --parameter-overrides \
    MilvusHost=milvus.company.com \
    OllamaHost=ollama.company.com \
  --capabilities CAPABILITY_IAM

# 3. Build React app
cd chatbots/react-chatbot
npm run build

# 4. Upload to S3
aws s3 sync build/ s3://rag-chatbot-prod-<account>/

# 5. Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*"
```

### 3E. Environment Variables

For serverless deployment, set these in Lambda:

```env
MILVUS_HOST=milvus-serverless.example.com
MILVUS_PORT=19530
OLLAMA_HOST=http://ollama-serverless.example.com:11434
MILVUS_DB_NAME=knowledge_base
OLLAMA_COLLECTION_NAME=milvus_rag_collection
API_PORT=80  # Not used in Lambda (API Gateway handles routing)
```

### 3F. Serverless Considerations

**Advantages:**
- ✅ Auto-scaling
- ✅ Pay-per-invocation
- ✅ No infrastructure management
- ✅ CloudFront caching reduces latency
- ✅ Built-in monitoring/logging

**Limitations:**
- ⚠️ 15-minute timeout (cold starts can take 3-5s)
- ⚠️ Streaming requires WebSocket (API Gateway doesn't support SSE)
- ⚠️ Requires external Milvus/Ollama (not containerized)
- ⚠️ State not persisted between invocations

**Recommendations:**
- Use RDS for Milvus (Aurora, Managed Database)
- Use ECS/Fargate for Ollama (needs persistence)
- Enable Lambda@Edge for performance
- Use API Gateway caching for frequent queries

---

## 4. Comparison Matrix

| Aspect | Local | Docker | Serverless |
|--------|-------|--------|-----------|
| **Setup Time** | 5 min | 10 min | 20 min |
| **Cost** | Free | Infrastructure | Pay-as-you-go |
| **Scalability** | Single machine | Manual | Auto |
| **Latency (p50)** | <100ms | <200ms | 500ms-3s |
| **Cold Starts** | No | ~5s | 3-5s |
| **DevOps** | Simple | Medium | Complex |
| **Production Ready** | No | Yes | Yes |
| **Streaming** | Full SSE | Full SSE | WebSocket only |

---

## 5. Quick Deployment Reference

### Local
```bash
npm start  # Port 3000
```

### Docker
```bash
docker compose up react-chatbot  # Port 3000
```

### Serverless
```bash
sam deploy
# Upload React build to S3
# Access via CloudFront URL
```

---

## 6. Recommended Production Setup

**Tier 1: Most Scalable**
```
CloudFront → Lambda (API) → Aurora RDS (Milvus) + ECS Fargate (Ollama)
```

**Tier 2: Balanced**
```
CloudFront → NextJS/Vercel (React) → Docker API → Milvus + Ollama
```

**Tier 3: Simplest**
```
Docker Compose (React + API + Milvus + Ollama) on EC2/VM
```
