"""Claude powered Logistics runtime.

Replaces the Gemini LlmAgent with a manual Anthropic Messages tool loop. The
model only decides to call the deterministic tool and narrates the result; the
cause codes and values come from the shared logistics_core diagnosis and are
authoritative. A strict narrative guard drops any model text that omits an
authoritative code or invents one, and errors are returned as sanitized codes.
"""
import os
import json
import logging

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from logistics_core import diagnosis
from logistics_core.diagnosis import CAUSE_CODES, InvalidOrderId
from logistics_claude.skill_loader import load_skill, DEFAULT_SKILL_DIR

log = logging.getLogger("logistics_claude.agent")

MODEL = os.getenv("LOGISTICS_MODEL", "claude-haiku-5-5")
MAX_TOKENS = int(os.getenv("LOGISTICS_MAX_TOKENS", "1024"))
MAX_TURNS = int(os.getenv("LOGISTICS_MAX_TURNS", "4"))
SKILL_DIR = os.getenv("DELAY_SKILL_DIR", DEFAULT_SKILL_DIR)

TOOL = {
    "name": "delay_root_cause",
    "description": (
        "Governed deterministic logistics diagnosis for one order. Returns per "
        "item warehouse lag and transit time against the shipping distribution "
        "center 90 day baseline, and the authoritative cause code per item. The "
        "rules, not the model, decide the cause."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"order_id": {"type": "integer"}},
        "required": ["order_id"],
    },
}


# --- governance helpers (pure, offline testable) ---------------------------

def authoritative_codes(result) -> set:
    """Collect every cause code string found anywhere in the diagnosis result."""
    found = set()

    def walk(node):
        if isinstance(node, str):
            if node in CAUSE_CODES:
                found.add(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(result)
    return found


def guard_narrative(text: str, result) -> tuple:
    """Return (ok, reason). Strict: deterministic result stays authoritative."""
    if isinstance(result, dict) and result.get("error"):
        return False, "error result, use sanitized fallback"
    if not text or not text.strip():
        return False, "empty narrative"
    auth = authoritative_codes(result)
    present = {code for code in CAUSE_CODES if code in text}
    missing = auth - present
    invented = present - auth
    if missing:
        return False, f"missing authoritative codes {sorted(missing)}"
    if invented:
        return False, f"invented codes not in result {sorted(invented)}"
    return True, "ok"


def render_fallback(order_id: int, result) -> str:
    """Deterministic text built straight from the tool output. Always has codes."""
    codes = authoritative_codes(result)
    lines = [f"Delay diagnosis for order {order_id} (deterministic, authoritative)."]
    if isinstance(result, dict) and result.get("error"):
        lines.append(f"Status: {result['error']}.")
    if codes:
        lines.append("Cause codes: " + ", ".join(sorted(codes)) + ".")
    lines.append("Structured result: " + json.dumps(result, default=str))
    return "\n".join(lines)


def _run_tool(order_id: int) -> dict:
    """Execute the shared diagnosis. Never leak raw errors; return sanitized codes."""
    try:
        return diagnosis.delay_root_cause(order_id)
    except InvalidOrderId:
        return {"order_id": order_id, "error": "INVALID_ORDER_ID"}
    except Exception:  # noqa: BLE001 - sanitize everything else
        log.exception("delay_root_cause failed for order_id=%s", order_id)
        return {"order_id": order_id, "error": "DATA_UNAVAILABLE"}


def _client():
    from anthropic import Anthropic  # lazy: offline tests need no SDK or key

    return Anthropic()


def diagnose(order_id: int) -> dict:
    """Run the Claude tool loop for one order and return guarded text plus data.

    The tool is always executed with the request order_id, so the model cannot
    redirect the diagnosis to a different order. The deterministic result runs
    even if the model skips the tool, and the guard decides whether the model
    narrative or a deterministic fallback is returned.
    """
    system = load_skill(SKILL_DIR)
    messages = [{
        "role": "user",
        "content": (
            f"Diagnose the delay for order_id={order_id}. Call the "
            "delay_root_cause tool and follow the skill. Report each item cause "
            "code exactly as returned."
        ),
    }]

    client = _client()
    authoritative = None
    narrative = ""
    usage = {"input_tokens": 0, "output_tokens": 0, "model_calls": 0}

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system,
            tools=[TOOL], messages=messages,
        )
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        usage["model_calls"] += 1
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use" and block.name == "delay_root_cause":
                    result = _run_tool(order_id)  # bound to request order_id
                    if authoritative is None:
                        authoritative = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue
        narrative = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        break

    if authoritative is None:
        authoritative = _run_tool(order_id)

    ok, reason = guard_narrative(narrative, authoritative)
    text = narrative if ok else render_fallback(order_id, authoritative)
    return {
        "order_id": order_id,
        "text": text,
        "result": authoritative,
        "guard": {"passed": ok, "reason": reason, "model": MODEL},
        "usage": usage,
    }
