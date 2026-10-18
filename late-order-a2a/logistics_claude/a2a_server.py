"""Explicit A2A adapter for the Claude Logistics runtime.

The Anthropic SDK does not ship an A2A server, so this implements the subset of
the A2A JSON-RPC message/send contract that the existing CX agent consumes, plus
an Agent Card for discovery. The response is shaped as an A2A Task so CX reads
result.artifacts[].parts[].text and result.status.state with no changes.

Run:
    uvicorn logistics_claude.a2a_server:a2a_app --port 8002
"""
import os
import re
import uuid

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from logistics_claude.agent import diagnose, MODEL

PORT = int(os.getenv("LOGISTICS_PORT", "8002"))
PUBLIC_URL = os.getenv("LOGISTICS_PUBLIC_URL", f"http://localhost:{PORT}")
ORDER_RE = re.compile(r"order_id\s*=\s*(\d+)")

# Curated card: no internal instructions, no raw SQL, no credentials.
AGENT_CARD = {
    "protocolVersion": "0.3.0",
    "name": "logistics-agent",
    "description": (
        "Supply Chain logistics delay diagnosis. Classifies warehouse delay "
        "versus transit delay for one order against the distribution center "
        "90 day baseline. Does not handle refunds or customer communication."
    ),
    "version": "2.0-claude",
    "preferredTransport": "JSONRPC",
    "url": PUBLIC_URL,
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [{
        "id": "delay-root-cause",
        "name": "Delay Root Cause",
        "description": "Diagnose why an order is late: warehouse lag versus transit time against the DC baseline.",
        "tags": ["logistics", "delay", "diagnosis"],
    }],
}


def extract_order_id(message: dict):
    parts = message.get("parts", []) if isinstance(message, dict) else []
    text = " ".join(p.get("text", "") for p in parts if p.get("kind") == "text")
    match = ORDER_RE.search(text)
    return int(match.group(1)) if match else None


def build_task(req_id, text: str, state: str = "completed", metadata: dict = None) -> dict:
    result = {
        "id": str(uuid.uuid4()),
        "contextId": str(uuid.uuid4()),
        "kind": "task",
        "status": {"state": state},
        "artifacts": [{
            "artifactId": str(uuid.uuid4()),
            "name": "delay_diagnosis",
            "parts": [{"kind": "text", "text": text}],
        }],
    }
    if metadata:
        # Non breaking: CX reads only artifacts and status; extra fields are ignored.
        result["metadata"] = metadata
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


async def agent_card(request):
    return JSONResponse(AGENT_CARD)


async def handle_rpc(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "parse error"}})
    req_id = body.get("id")
    if body.get("method") != "message/send":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id,
                             "error": {"code": -32601, "message": "method not found"}})

    order_id = extract_order_id(body.get("params", {}).get("message", {}))
    if order_id is None:
        return JSONResponse(build_task(
            req_id, "INVALID_REQUEST: could not read order_id", state="rejected"))

    out = diagnose(order_id)
    meta = {
        "model": MODEL,
        "guard": out.get("guard"),
        "usage": out.get("usage"),
    }
    return JSONResponse(build_task(req_id, out["text"], state="completed", metadata=meta))


routes = [
    Route("/", handle_rpc, methods=["POST"]),
    Route("/.well-known/agent-card.json", agent_card, methods=["GET"]),
]

a2a_app = Starlette(routes=routes)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(a2a_app, host="0.0.0.0", port=PORT)
