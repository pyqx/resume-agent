"""Regression tests: the agent loop must always produce a usable answer.

Covers the "工具成功但回复'我暂时没有得到有效回复'" bug: models drift on the
respond-message key name, or return truncated JSON — the loop must recover
via key aliases or a plain-language composition call, never a canned failure.
"""

import asyncio
import json


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.messages = self

    async def create(self, **kwargs):
        self.calls += 1
        return _Resp(self.replies.pop(0))


class FakeAssembler:
    async def assemble(self, **kwargs):
        return {"system_prompt": "sys", "available_tools": []}


class FakeCheckpoint:
    async def load(self, session_id):
        return None

    async def save(self, checkpoint):
        pass

    async def delete(self, session_id):
        pass


class FakeRegistry:
    def get(self, name):
        return None

    async def execute(self, name, **kwargs):
        raise AssertionError("no tool execution expected")


def _run(replies):
    from agent.loop import AgentLoop

    loop = AgentLoop(FakeLLM(replies), FakeAssembler(), FakeRegistry(), FakeCheckpoint())

    async def collect():
        final = None
        async for event in loop.run("这份简历怎么样"):
            if event["type"] == "final":
                final = event["data"]
        return final

    return asyncio.run(collect())


class TestRespondRecovery:
    def test_alias_answer_key(self):
        """Model used "answer" instead of "message" — must still be used."""
        final = _run([json.dumps(
            {"action": "respond", "answer": "整体 8.2 分,建议加强量化。"},
            ensure_ascii=False,
        )])
        assert final["response"] == "整体 8.2 分,建议加强量化。"

    def test_alias_response_key(self):
        final = _run([json.dumps(
            {"action": "respond", "response": "回答内容"}, ensure_ascii=False
        )])
        assert final["response"] == "回答内容"

    def test_compose_fallback_when_no_text_key(self):
        """No usable key at all — one extra plain-language call composes it."""
        final = _run([
            json.dumps({"action": "respond", "reasoning": "done"}),
            "这是基于工具结果的完整回答。",
        ])
        assert final["response"] == "这是基于工具结果的完整回答。"

    def test_truncated_json_not_echoed(self):
        """Truncated JSON must not be shown to the user verbatim."""
        final = _run([
            '{"action": "respond", "message": "很长的回答被截',
            "兜底回答成功。",
        ])
        assert final["response"] == "兜底回答成功。"
        assert "{" not in final["response"]

    def test_plain_prose_passthrough(self):
        """Non-JSON prose is a legitimate direct response."""
        final = _run(["直接的自然语言回答。"])
        assert final["response"] == "直接的自然语言回答。"
