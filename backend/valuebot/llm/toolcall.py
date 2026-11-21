"""Structured output via a single tool call, on every Claude model.

Some models reject a forced ``tool_choice`` ({"type": "tool"} or {"type": "any"}). For those we ask with
``tool_choice: auto`` plus an explicit instruction, and nudge once more if the reply has no tool call.
Which models refuse is learned at runtime and remembered for the life of the process, so each model
pays for at most one rejected request.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger("valuebot.toolcall")

_no_forced: set[str] = set()
_lock = threading.Lock()

NUDGE = "Respond only by calling the `{name}` tool with the complete result. Do not reply in plain text."


def _tool_input(resp: Any, name: str) -> dict | None:
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", name) == name:
            return dict(block.input)
    return None


def _rejects_forced(err: Exception) -> bool:
    msg = str(err).lower()
    return "tool_choice" in msg and ("not supported" in msg or "not compatible" in msg or "cannot be used" in msg)


def call_tool(client: Any, *, model: str, system: str, messages: list[dict], tool: dict, max_tokens: int) -> dict:
    """Return the input of the model's call to ``tool``. Raises RuntimeError if it never calls it."""
    name = tool["name"]
    base = {"model": model, "max_tokens": max_tokens, "tools": [tool]}

    if model not in _no_forced:
        try:
            resp = client.messages.create(**base, system=system, messages=messages,
                                          tool_choice={"type": "tool", "name": name})
            out = _tool_input(resp, name)
            if out is not None:
                return out
        except Exception as e:
            if not _rejects_forced(e):
                raise
            with _lock:
                _no_forced.add(model)
            log.info("model %s does not accept a forced tool_choice; using auto", model)

    sys2 = f"{system}\n\n{NUDGE.format(name=name)}"
    msgs = list(messages)
    for attempt in range(2):
        resp = client.messages.create(**base, system=sys2, messages=msgs, tool_choice={"type": "auto"})
        out = _tool_input(resp, name)
        if out is not None:
            return out
        if attempt == 0:  # it answered in prose: show it its reply and ask again
            text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
            msgs = msgs + [{"role": "assistant", "content": text or "(no answer)"},
                           {"role": "user", "content": NUDGE.format(name=name)}]
    raise RuntimeError(f"Model did not call the {name} tool")
