import pytest
from unittest.mock import AsyncMock, patch
from tenacity import wait_none

from schemas import PostMetadata
import agents.tagging_agent as tagging_agent
from agents.tagging_agent import generate_post_metadata, TaggingNotConfiguredError


@pytest.mark.anyio
async def test_generate_post_metadata_success():
    result = await generate_post_metadata("Test Title", "Some post content")
    assert result.tags == ["test", "mock"]
    assert result.summary == "Mock summary."


@pytest.mark.anyio
async def test_generate_post_metadata_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(tagging_agent._call_llm.retry, "wait", wait_none())

    fake_result = PostMetadata(tags=["a"], summary="s", meta_description="m")
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[Exception("rate limited"), fake_result])

    with patch("agents.tagging_agent._get_structured_llm", return_value=mock_llm):
        result = await generate_post_metadata("T", "C")

    assert result.tags == ["a"]
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.anyio
async def test_generate_post_metadata_exhausts_retries(monkeypatch):
    monkeypatch.setattr(tagging_agent._call_llm.retry, "wait", wait_none())

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("persistent failure"))

    with patch("agents.tagging_agent._get_structured_llm", return_value=mock_llm):
        with pytest.raises(Exception, match="persistent failure"):
            await generate_post_metadata("T", "C")

    assert mock_llm.ainvoke.call_count == 3


@pytest.mark.no_mock_llm
@pytest.mark.anyio
async def test_missing_api_key_raises_clear_error(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(tagging_agent, "_structured_llm", None)

    with pytest.raises(TaggingNotConfiguredError):
        await tagging_agent._call_llm("prompt")