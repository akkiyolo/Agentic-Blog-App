import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tenacity import wait_none
from httpx import AsyncClient

import agents.draft_agent as draft_agent
from agents.draft_agent import (
    research_posts,
    research_web,
    merge_research,
    generate_outline,
    generate_draft,
    run_draft_graph,
    DraftAgentNotConfiguredError,
)
from schemas import DraftOutput
from tests.conftest import auth_header, create_test_user, login_user


# --- research_posts (keyword search over own posts) ---

@pytest.mark.anyio
async def test_research_posts_finds_matching_posts(client: AsyncClient, db_session):
    await create_test_user(client)
    token = await login_user(client)
    await client.post(
        "/api/posts",
        json={"title": "Kubernetes basics", "content": "Learning kubernetes deployments and pods."},
        headers=auth_header(token),
    )
    await client.post(
        "/api/posts",
        json={"title": "Cooking pasta", "content": "How to cook pasta al dente."},
        headers=auth_header(token),
    )

    result = await research_posts(
        {"topic": "Kubernetes deployments explained"},
        {"configurable": {"db": db_session}},
    )

    assert "Kubernetes basics" in result["own_posts_context"]
    assert len(result["sources"]) >= 1
    assert result["sources"][0]["type"] == "post"


@pytest.mark.anyio
async def test_research_posts_no_match_returns_empty(db_session):
    result = await research_posts(
        {"topic": "xyzzyquantumfoobar"},
        {"configurable": {"db": db_session}},
    )
    assert result == {"own_posts_context": "", "sources": []}


# --- research_web (Tavily) ---

@pytest.mark.anyio
async def test_research_web_not_configured_returns_empty(monkeypatch):
    monkeypatch.setattr(
        draft_agent,
        "_get_tavily_client",
        lambda: None,
    )

    result = await research_web(
        {"topic": "anything"},
        {"configurable": {}},
    )

    assert result == {
        "web_context": "",
        "sources": [],
    }

@pytest.mark.anyio
async def test_research_web_success(monkeypatch):
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {
                "title": "Kubernetes Guide",
                "content": "Kubernetes orchestrates containers.",
                "url": "https://example.com/k8s",
            },
        ],
    }
    monkeypatch.setattr(draft_agent, "_get_tavily_client", lambda: mock_client)

    result = await research_web({"topic": "Kubernetes"}, {"configurable": {}})

    assert "Kubernetes Guide" in result["web_context"]
    assert result["sources"][0]["type"] == "web"
    assert result["sources"][0]["url"] == "https://example.com/k8s"


@pytest.mark.anyio
async def test_research_web_handles_failure(monkeypatch):
    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("tavily down")
    monkeypatch.setattr(draft_agent, "_get_tavily_client", lambda: mock_client)

    result = await research_web({"topic": "x"}, {"configurable": {}})
    assert result == {"web_context": "", "sources": []}


# --- merge_research ---

@pytest.mark.anyio
async def test_merge_research_combines_both():
    result = await merge_research({"own_posts_context": "post stuff", "web_context": "web stuff"})
    assert "post stuff" in result["research_context"]
    assert "web stuff" in result["research_context"]


@pytest.mark.anyio
async def test_merge_research_empty_when_no_context():
    result = await merge_research({})
    assert result["research_context"] == "No research context available."


# --- generate_outline / generate_draft (mocked by autouse fixture) ---

@pytest.mark.anyio
async def test_generate_outline_returns_content():
    result = await generate_outline({"topic": "Test topic", "research_context": "some research"})
    assert result["outline"] == "1. Intro\n2. Body\n3. Conclusion"


@pytest.mark.anyio
async def test_generate_draft_fresh():
    result = await generate_draft(
        {"topic": "T", "outline": "1. Intro", "research_context": "R", "feedback": None, "draft_content": ""},
    )
    assert result["draft_title"] == "Mock Draft Title"
    assert result["draft_content"] == "Mock draft content."


@pytest.mark.anyio
async def test_generate_draft_truncates_long_title(monkeypatch):
    long_title = "x" * 150
    fake_draft = DraftOutput(title=long_title, content="content")
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_draft)

    with patch("agents.draft_agent._get_draft_llm", return_value=mock_llm):
        result = await generate_draft(
            {"topic": "T", "outline": "O", "research_context": "R", "feedback": None, "draft_content": ""},
        )

    assert len(result["draft_title"]) == 100


# --- retries ---

@pytest.mark.anyio
async def test_generate_outline_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(draft_agent._call_outline_llm.retry, "wait", wait_none())

    from types import SimpleNamespace
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[Exception("rate limited"), SimpleNamespace(content="Outline text")],
    )

    with patch("agents.draft_agent._get_outline_llm", return_value=mock_llm):
        result = await generate_outline({"topic": "T", "research_context": "R"})

    assert result["outline"] == "Outline text"
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.anyio
async def test_generate_draft_exhausts_retries(monkeypatch):
    monkeypatch.setattr(draft_agent._call_draft_llm.retry, "wait", wait_none())

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("persistent failure"))

    with patch("agents.draft_agent._get_draft_llm", return_value=mock_llm):
        with pytest.raises(Exception, match="persistent failure"):
            await generate_draft(
                {"topic": "T", "outline": "O", "research_context": "R", "feedback": None, "draft_content": ""},
            )

    assert mock_llm.ainvoke.call_count == 3


# --- missing API key ---

@pytest.mark.no_mock_llm
@pytest.mark.anyio
async def test_missing_api_key_raises_for_outline(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(draft_agent, "_outline_llm", None)

    with pytest.raises(DraftAgentNotConfiguredError):
        await draft_agent._call_outline_llm("prompt")


@pytest.mark.no_mock_llm
@pytest.mark.anyio
async def test_missing_api_key_raises_for_draft(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(draft_agent, "_draft_llm", None)

    with pytest.raises(DraftAgentNotConfiguredError):
        await draft_agent._call_draft_llm("prompt")


# --- full graph: routing behavior ---

@pytest.mark.anyio
async def test_run_draft_graph_fresh_generation(client: AsyncClient, db_session):
    await create_test_user(client)
    token = await login_user(client)
    await client.post(
        "/api/posts",
        json={"title": "Async Postgres on Windows", "content": "Notes on psycopg async issues."},
        headers=auth_header(token),
    )

    result = await run_draft_graph(topic="Async Postgres on Windows tips", db=db_session)

    assert result["draft_title"] == "Mock Draft Title"
    assert result["draft_content"] == "Mock draft content."
    assert result["outline"] == "1. Intro\n2. Body\n3. Conclusion"
    assert any(s["type"] == "post" for s in result["sources"])


@pytest.mark.anyio
async def test_run_draft_graph_revision_skips_research(client: AsyncClient, db_session):
    await create_test_user(client)
    token = await login_user(client)
    await client.post(
        "/api/posts",
        json={"title": "Kubernetes basics", "content": "kubernetes content"},
        headers=auth_header(token),
    )

    result = await run_draft_graph(
        topic="Kubernetes basics",
        db=db_session,
        feedback="make it shorter",
        previous_outline="1. Old outline",
        previous_draft_title="Old Title",
        previous_draft_content="Old content",
    )

    # research nodes never ran on the revision path, so no sources were added
    assert result["sources"] == []
    # outline was preserved from input, not regenerated
    assert result["outline"] == "1. Old outline"
    assert result["draft_title"] == "Mock Draft Title"