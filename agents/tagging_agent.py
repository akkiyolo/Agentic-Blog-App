from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI

from config import settings
from schemas import PostMetadata

logger = logging.getLogger(__name__)

_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=settings.google_api_key.get_secret_value(),
    temperature=0.3,
)
_structured_llm = _llm.with_structured_output(PostMetadata)

_PROMPT = """You are a blog metadata assistant. Given a blog post, generate:
- 3-6 concise, lowercase, topical tags
- a 2-3 sentence summary
- an SEO meta description (max 155 characters)

Title: {title}

Content:
{content}
"""

MAX_CONTENT_CHARS = 6000


async def generate_post_metadata(title: str, content: str) -> PostMetadata:
    """Call the LLM to generate structured tags/summary/meta description for a post."""
    prompt = _PROMPT.format(title=title, content=content[:MAX_CONTENT_CHARS])
    result = await _structured_llm.ainvoke(prompt)
    return result  # type: ignore[return-value]