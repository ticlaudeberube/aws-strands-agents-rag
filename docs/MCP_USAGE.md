# MCP Usage in Kiro

This page describes the Model Context Protocol (MCP) servers that Kiro uses while working on this project. It covers what each server does and when to enable it.

Kiro reads MCP servers from two files:

- User config: `~/.kiro/settings/mcp.json`
- Workspace config: `.kiro/settings/mcp.json` in this repo

When both files define a server with the same name, the workspace definition wins. Each enabled server adds its tool definitions to the context on every turn, so keep only the servers you need.

The project's own MCP server (`src/mcp/mcp_server.py`, exposed through `/api/mcp/*`) is a separate thing. See [API_SERVER.md](API_SERVER.md).

## Servers

| Server | Config file | What it does | Enable when | Leave disabled when |
|--------|-------------|--------------|-------------|---------------------|
| `aws-docs` | Workspace | Searches and reads public AWS documentation. | You need AWS service facts, API details, or limits. | You only work on code that is already in the repo. |
| `bedrock-agentcore` | Workspace (also in user config, overridden by workspace) | Helps with AgentCore runtimes, gateways, memory, identity, policy, and code interpreter sessions. | You build or debug AgentCore deployments. | You use only the local RAG stack or Bedrock without AgentCore. |
| `mlflow-mcp` | Workspace | Lets Kiro query MLflow experiments, runs, and traces. | You review evaluation results from [EVAL_LOCAL.md](EVAL_LOCAL.md). | The MLflow tracking server is not running. The server needs one at `http://127.0.0.1:5000` and fails without it. |
| `playwright-test` | Workspace | Runs and inspects Playwright end-to-end tests for the React chatbot. | You work on the E2E tests in `chatbots/react-chatbot/e2e/`. | You do not change the UI or E2E tests. |
| `terraform` | Workspace | Looks up Terraform providers, modules, and registry details through the HashiCorp Docker image. | You edit files under `infrastructure/terraform/`. | Docker is not running, or you do not touch Terraform. Set `TFE_TOKEN` for Terraform Cloud access. |
| `aws-mcp` | User (currently disabled) | Runs AWS CLI commands through a proxy using the `cberube` profile, plus AWS docs and skills. | You want Kiro to inspect or change AWS resources in your account. | You only need documentation or code help. Use `aws-docs` instead. |
| `power-terraform-terraform` | User (under `powers`) | Same HashiCorp Terraform image as the workspace `terraform` server. | Not needed when the workspace `terraform` server is enabled. | Always, while the workspace `terraform` server is enabled. It duplicates that server. |

## Guidelines

- Start with the minimum set. Add a server when a task needs it, and disable it afterward.
- Read documentation with `aws-docs`. Use `aws-mcp` only when Kiro must act on AWS.
- Do not enable two servers that run the same image or service, such as the two Terraform entries.
- Servers that need a running local service (`mlflow-mcp`, Docker-based `terraform`) fail when that service is down. Start the service first.
- Auto-approve lists skip confirmation prompts. They do not reduce token use.
- Pin server versions when you need reproducible behavior. The current entries use `@latest`, so each start can pull a newer release.

## Known issues

- MLflow tracking URI `http://127.0.0.1:5000` conflicts with macOS AirPlay Receiver (ControlCenter), which also listens on port 5000. Use another port for MLflow, or turn off AirPlay Receiver.
- `TFE_TOKEN` is empty in some shells. Set it in the environment Kiro uses.
