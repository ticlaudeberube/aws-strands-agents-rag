import asyncio
import json
from typing import Any

import websockets

try:
    from strands.agents import tool  # type: ignore
except ImportError:

    def tool(func):
        return func


AWS_MCP_URL = "wss://knowledge-mcp.global.api.aws/mcp"


@tool
def aws_docs_query(query: str) -> dict[str, Any]:
    """Query the AWS Documentation MCP server for live AWS docs answers."""

    async def ask_aws_mcp(question: str) -> dict[str, Any]:
        async with websockets.connect(AWS_MCP_URL) as ws:
            req: dict[str, Any] = {
                "type": "tool_call",
                "tool": "aws_docs_search",
                "input": {"query": question},
            }
            await ws.send(json.dumps(req))
            resp = await ws.recv()
            data: dict[str, Any] = json.loads(resp)
            return data

    try:
        result: dict[str, Any] = asyncio.run(ask_aws_mcp(query))
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
