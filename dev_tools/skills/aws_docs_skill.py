import asyncio
import json
from typing import Any, Dict

import websockets

try:
    from strands.agents import tool  # type: ignore
except ImportError:
    def tool(func):
        return func

AWS_MCP_URL = "wss://knowledge-mcp.global.api.aws/mcp"

@tool
def aws_docs_query(query: str) -> Dict[str, Any]:
    """Query the AWS Documentation MCP server for live AWS docs answers."""
    async def ask_aws_mcp(question: str) -> Dict[str, Any]:
        async with websockets.connect(AWS_MCP_URL) as ws:
            req: Dict[str, Any] = {
                "type": "tool_call",
                "tool": "aws_docs_search",
                "input": {"query": question}
            }
            await ws.send(json.dumps(req))
            resp = await ws.recv()
            data: Dict[str, Any] = json.loads(resp)
            return data
    try:
        result: Dict[str, Any] = asyncio.run(ask_aws_mcp(query))
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
