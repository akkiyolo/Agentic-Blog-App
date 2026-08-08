import pytest
from unittest.mock import AsyncMock, patch
from tenacity import wait_none

import agents.qa_agent as qa_agent
from agents.qa_agent import answer_question, QAAgentNotConfiguredError
from schemas import QAMessage


@pytest.mark.anyio
async def test_answer_question_basic():
    answer = await answer_question("Title", "Some post content", "What is this about?")
    assert answer == "Mock answer."


@pytest.mark.anyio
async def test_answer_question_includes_history(monkeypatch):
    captured = {}
    mock_llm = AsyncMock()

    async def fake_ainvoke(messages):
        captured["messages"] = messages
        from types import SimpleNamespace
        return SimpleNamespace(content="ok")

    mock_llm.ainvoke = fake_ainvoke

    with patch("agents.qa_agent._get_qa_llm", return_value=mock_llm):
        await answer_question(
            "Title", "Content", "Follow-up question",
            chat_history=[QAMessage(role="user", content="Earlier question")],
        )

    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "user"]


@pytest.mark.anyio
async def test_answer_question_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(qa_agent._call_qa_llm.retry, "wait", wait_none())

    from types import SimpleNamespace
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[Exception("rate limited"), SimpleNamespace(content="recovered")],
    )

    with patch("agents.qa_agent._get_qa_llm", return_value=mock_llm):
        result = await answer_question("T", "C", "Q?")

    assert result == "recovered"


@pytest.mark.no_mock_llm
@pytest.mark.anyio
async def test_missing_api_key_raises(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(qa_agent, "_qa_llm", None)

    with pytest.raises(QAAgentNotConfiguredError):
        await qa_agent._call_qa_llm([{"role": "user", "content": "hi"}])