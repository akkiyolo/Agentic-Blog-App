from __future__ import annotations

import asyncio
import logging
import operator
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

import models
from config import settings
from schemas import DraftOutput

logger = logging.getLogger(__name__)

STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "with",
    "about", "how", "what", "why", "is", "are", "your", "you", "my",
}

MAX_CONTEXT_CHARS_PER_ITEM = 500


class DraftState(TypedDict, total=False):
    topic: str
    feedback: str | None
    skip_research: bool
    own_posts_context: str
    web_context: str
    research_context: str
    outline: str
    draft_title: str
    draft_content: str
    sources: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------
# Lazy LLM / client init — same pattern as agents/tagging_agent.py so
# the app still boots and other agents still work if only one API key
# is missing.
# ---------------------------------------------------------------------

_outline_llm = None
_draft_llm = None
_tavily_client = None

_llm_semaphore = asyncio.Semaphore(3)


class DraftAgentNotConfiguredError(RuntimeError):
    pass


def _get_outline_llm():
    global _outline_llm
    if _outline_llm is not None:
        return _outline_llm
    if settings.google_api_key is None:
        raise DraftAgentNotConfiguredError("GOOGLE_API_KEY is not set.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    _outline_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=0.4,
    )
    return _outline_llm


def _get_draft_llm():
    global _draft_llm
    if _draft_llm is not None:
        return _draft_llm
    if settings.google_api_key is None:
        raise DraftAgentNotConfiguredError("GOOGLE_API_KEY is not set.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=0.6,
    )
    _draft_llm = llm.with_structured_output(DraftOutput)
    return _draft_llm


def _get_tavily_client():
    global _tavily_client
    if _tavily_client is not None:
        return _tavily_client
    if settings.tavily_api_key is None:
        return None
    from tavily import TavilyClient

    _tavily_client = TavilyClient(api_key=settings.tavily_api_key.get_secret_value())
    return _tavily_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def _call_outline_llm(prompt: str) -> str:
    llm = _get_outline_llm()
    async with _llm_semaphore:
        result = await llm.ainvoke(prompt)
    return result.content


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def _call_draft_llm(prompt: str) -> DraftOutput:
    llm = _get_draft_llm()
    async with _llm_semaphore:
        result = await llm.ainvoke(prompt)
    return result  # type: ignore[return-value]


# ---------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------

OUTLINE_PROMPT = """You are a blog writing assistant. Based on the topic and research
notes below, produce a clear outline for a blog post: 4-6 sections, each with a
one-line description of what it covers. Ground the outline in the research where
relevant, but note where you're filling gaps with general knowledge.

Topic: {topic}

Research notes:
{research}

Return the outline as a plain numbered list only.
"""

DRAFT_PROMPT = """You are a blog writing assistant. Write a full blog post following
the outline below, in a natural and engaging voice. Where the research notes reference
one of the author's own past posts (marked [Post #N]), you may refer to it naturally.
Do not fabricate facts, statistics, or quotes not supported by the research notes.

Topic: {topic}

Outline:
{outline}

Research notes:
{research}
"""

REVISE_PROMPT = """You are a blog writing assistant revising a draft based on the
author's feedback. Preserve what already works; change only what the feedback asks for.

Topic: {topic}

Outline:
{outline}

Previous draft:
{previous_draft}

Author feedback:
{feedback}

Return the full revised post.
"""


# ---------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------

async def research_posts(state: DraftState, config: RunnableConfig) -> dict:
    """Naive keyword search over the author's own posts.

    This is a placeholder for real semantic retrieval — swap for a
    pgvector similarity search once the RAG pipeline is built.
    """
    db: AsyncSession = config["configurable"]["db"]
    topic = state["topic"]

    keywords = [
        w.strip(".,!?").lower()
        for w in topic.split()
        if len(w) > 3 and w.lower() not in STOPWORDS
    ]
    if not keywords:
        keywords = [topic]

    conditions = [
        or_(models.Post.title.ilike(f"%{kw}%"), models.Post.content.ilike(f"%{kw}%"))
        for kw in keywords[:5]
    ]

    result = await db.execute(
        select(models.Post)
        .where(or_(*conditions))
        .order_by(models.Post.date_posted.desc())
        .limit(5),
    )
    posts = result.scalars().all()

    if not posts:
        return {"own_posts_context": "", "sources": []}

    context_parts = []
    sources = []
    for post in posts:
        snippet = post.content[:MAX_CONTEXT_CHARS_PER_ITEM]
        context_parts.append(f"[Post #{post.id}] {post.title}\n{snippet}")
        sources.append({"type": "post", "title": post.title, "post_id": post.id, "url": None})

    return {"own_posts_context": "\n\n".join(context_parts), "sources": sources}


async def research_web(state: DraftState, config: RunnableConfig) -> dict:
    client = _get_tavily_client()
    if client is None:
        logger.warning("TAVILY_API_KEY not set — skipping web research")
        return {"web_context": "", "sources": []}

    topic = state["topic"]
    try:
        response = await asyncio.to_thread(
            client.search, query=topic, max_results=5, search_depth="basic",
        )
    except Exception:
        logger.exception("Tavily search failed for topic=%s", topic)
        return {"web_context": "", "sources": []}

    results = response.get("results", [])
    if not results:
        return {"web_context": "", "sources": []}

    context_parts = []
    sources = []
    for r in results:
        content = (r.get("content") or "")[:MAX_CONTEXT_CHARS_PER_ITEM]
        title = r.get("title") or "Untitled"
        context_parts.append(f"[{title}]\n{content}")
        sources.append({"type": "web", "title": title, "url": r.get("url"), "post_id": None})

    return {"web_context": "\n\n".join(context_parts), "sources": sources}


async def merge_research(state: DraftState) -> dict:
    parts = []
    if state.get("own_posts_context"):
        parts.append(f"### Related posts from your own blog:\n{state['own_posts_context']}")
    if state.get("web_context"):
        parts.append(f"### Web research:\n{state['web_context']}")
    return {"research_context": "\n\n".join(parts) or "No research context available."}


async def generate_outline(state: DraftState) -> dict:
    prompt = OUTLINE_PROMPT.format(topic=state["topic"], research=state["research_context"])
    outline = await _call_outline_llm(prompt)
    return {"outline": outline}


async def generate_draft(state: DraftState) -> dict:
    if state.get("feedback"):
        prompt = REVISE_PROMPT.format(
            topic=state["topic"],
            outline=state["outline"],
            previous_draft=state["draft_content"],
            feedback=state["feedback"],
        )
    else:
        prompt = DRAFT_PROMPT.format(
            topic=state["topic"],
            outline=state["outline"],
            research=state["research_context"],
        )

    result = await _call_draft_llm(prompt)
    return {"draft_title": result.title[:100], "draft_content": result.content}


def _route_start(state: DraftState) -> str | list[str]:
    if state.get("skip_research"):
        return "draft"
    return ["research_posts", "research_web"]


def _build_graph():
    graph = StateGraph(DraftState)
    graph.add_node("research_posts", research_posts)
    graph.add_node("research_web", research_web)
    graph.add_node("merge_research", merge_research)
    graph.add_node("outline", generate_outline)
    graph.add_node("draft", generate_draft)

    graph.add_conditional_edges(START, _route_start, ["research_posts", "research_web", "draft"])
    graph.add_edge("research_posts", "merge_research")
    graph.add_edge("research_web", "merge_research")
    graph.add_edge("merge_research", "outline")
    graph.add_edge("outline", "draft")
    graph.add_edge("draft", END)

    return graph.compile()


_graph = _build_graph()


# ---------------------------------------------------------------------
# Public entrypoint used by routers/drafts.py
# ---------------------------------------------------------------------

async def run_draft_graph(
    topic: str,
    db: AsyncSession,
    feedback: str | None = None,
    previous_outline: str | None = None,
    previous_draft_title: str | None = None,
    previous_draft_content: str | None = None,
) -> dict:
    initial_state: DraftState = {
        "topic": topic,
        "feedback": feedback,
        "skip_research": feedback is not None,
        "own_posts_context": "",
        "web_context": "",
        "research_context": "",
        "outline": previous_outline or "",
        "draft_title": previous_draft_title or "",
        "draft_content": previous_draft_content or "",
        "sources": [],
    }

    final_state = await _graph.ainvoke(
        initial_state,
        config={"configurable": {"db": db}},
    )

    return {
        "outline": final_state["outline"],
        "draft_title": final_state["draft_title"],
        "draft_content": final_state["draft_content"],
        "sources": final_state["sources"],
    }