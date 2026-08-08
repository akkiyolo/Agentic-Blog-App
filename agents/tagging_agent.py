from __future__ import annotations

import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from schemas import PostMetadata

logger = logging.getLogger(__name__)

_PROMPT = """You are a blog metadata assistant. Given a blog post, generate:
- 3-6 concise, lowercase, topical tags
- a 2-3 sentence summary
- an SEO meta description (max 155 characters)

Title: {title}

Content:
{content}
"""

MAX_CONTENT_CHARS = 6000

# Caps concurrent calls to Gemini so a burst of publishes doesn't blow
# through rate limits. Tune based on your API tier.
_llm_semaphore = asyncio.Semaphore(3)

_structured_llm = None  # lazily initialized singleton


class TaggingNotConfiguredError(RuntimeError):
    pass


def _get_structured_llm():
    global _structured_llm
    if _structured_llm is not None:
        return _structured_llm

    if settings.google_api_key is None:
        raise TaggingNotConfiguredError(
            "GOOGLE_API_KEY is not set — auto-tagging is disabled.",
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=0.3,
    )
    _structured_llm = llm.with_structured_output(PostMetadata)
    return _structured_llm


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
async def _call_llm(prompt: str) -> PostMetadata:
    llm = _get_structured_llm()
    async with _llm_semaphore:
        result = await llm.ainvoke(prompt)
    return result  # type: ignore[return-value]


async def generate_post_metadata(title: str, content: str) -> PostMetadata:
    """Call the LLM to generate structured tags/summary/meta description for a post.

    Raises TaggingNotConfiguredError if no API key is set, or the underlying
    exception after 3 retries with exponential backoff on transient failures.
    """
    prompt = _PROMPT.format(title=title, content=content[:MAX_CONTENT_CHARS])
    return await _call_llm(prompt)