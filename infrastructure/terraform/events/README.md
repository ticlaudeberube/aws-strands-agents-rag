# Sample events for `sam local invoke`

These JSON files are sample Lambda invocation payloads for local testing with
the AWS SAM CLI Terraform hook. See the **Local testing with the AWS SAM CLI**
section of [`../DEPLOYMENT.md`](../DEPLOYMENT.md) for the full workflow and
caveats.

## `event.json` — chat function (API Gateway v2 proxy)

An API Gateway v2 (HTTP API) proxy request for the `POST /chat` route, which
targets `module.compute.aws_lambda_function.chat`
(`agentcore_handler.lambda_handler`).

The handler reads the HTTP request `body` (a JSON string) and extracts:

| Field              | Required | Notes                                            |
|--------------------|----------|--------------------------------------------------|
| `question`         | yes      | Non-empty string, else HTTP 400 `MISSING_FIELD`  |
| `session_id`       | no       | Defaults to a fresh UUID when absent             |
| `top_k`            | no       | Integer in `[1, 50]`, else HTTP 400 `INVALID_TOP_K` |
| `force_web_search` | no       | Boolean, defaults to `false`                     |

Invoke it from `infrastructure/terraform/`:

```bash
sam local invoke --hook-name terraform \
  module.compute.aws_lambda_function.chat \
  -e events/event.json
```

To exercise the HTTP 400 validation path (no AWS backing services needed),
change the `body` to malformed JSON or drop `question` — the handler returns the
`{error_code, message}` envelope before invoking any agent node.

## Generating other events

The SAM CLI can generate skeleton events for other triggers. The indexing
function (`module.compute.aws_lambda_function.indexing`,
`indexing_handler.lambda_handler`) is triggered by **S3 ObjectCreated** under
the `documents/` prefix, so it expects an S3 event:

```bash
sam local generate-event s3 put \
  --bucket strands-rag-dev-documents \
  --key documents/example.pdf > events/s3-put.json

sam local invoke --hook-name terraform \
  module.compute.aws_lambda_function.indexing \
  -e events/s3-put.json
```
