"""call_tool works on models that reject a forced tool_choice."""
from types import SimpleNamespace as NS

import pytest

from valuebot.llm import toolcall


class BadRequest(Exception):
    pass


class FakeClient:
    def __init__(self, forced_ok: bool, prose_first: bool = False):
        self.forced_ok, self.prose_first, self.calls = forced_ok, prose_first, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if kw["tool_choice"]["type"] == "tool" and not self.forced_ok:
            raise BadRequest("Error code: 400 - tool_choice: type \"tool\" and \"any\" are not supported for this model.")
        if self.prose_first and len(self.calls) == (1 if self.forced_ok else 2):
            return NS(content=[NS(type="text", text="Here is my answer in prose")])
        return NS(content=[NS(type="thinking", thinking="..."), NS(type="tool_use", name="submit", input={"x": 1})])


TOOL = {"name": "submit", "description": "d", "input_schema": {"type": "object"}}


@pytest.fixture(autouse=True)
def _reset():
    toolcall._no_forced.clear()


def call(c, model="m"):
    return toolcall.call_tool(c, model=model, system="s", messages=[{"role": "user", "content": "u"}], tool=TOOL, max_tokens=10)


def test_forced_when_supported():
    c = FakeClient(forced_ok=True)
    assert call(c) == {"x": 1} and len(c.calls) == 1


def test_falls_back_to_auto_and_remembers():
    c = FakeClient(forced_ok=False)
    assert call(c) == {"x": 1}
    assert [k["tool_choice"]["type"] for k in c.calls] == ["tool", "auto"]
    assert "submit" in c.calls[1]["system"]
    assert call(c) == {"x": 1}  # second call skips the forced attempt
    assert [k["tool_choice"]["type"] for k in c.calls[2:]] == ["auto"]


def test_nudges_after_prose_reply():
    c = FakeClient(forced_ok=False, prose_first=True)
    assert call(c) == {"x": 1}
    assert c.calls[-1]["messages"][-2]["role"] == "assistant"


def test_other_errors_propagate():
    class Boom(FakeClient):
        def create(self, **kw):
            raise BadRequest("Error code: 400 - max_tokens too large")
    with pytest.raises(BadRequest):
        call(Boom(forced_ok=True))
