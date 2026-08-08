from __future__ import annotations

import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from schemas import QAMessage

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8000
MAX_HISTORY_TURNS = 6

_qa_llm = None
_llm_semaphore = asyncio.Semaphore(5)


class QAAgentNotConfiguredError(RuntimeError):
    pass


def _get_qa_llm():
    global _qa_llm
    if _qa_llm is not None:
        return _qa_llm
    if settings.google_api_key is None:
        raise QAAgentNotConfiguredError("GOOGLE_API_KEY is not set.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    _qa_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=0.2,
    )
    return _qa_llm


SYSTEM_PROMPT = """You are a helpful assistant answering reader questions about a
single blog post. Answer ONLY using the information in the post below. If the post
doesn't contain the answer, say so honestly instead of guessing or using outside
knowledge. Keep answers concise (2-5 sentences unless the question needs more).

Post title: {title}

Post content:
{content}
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15), reraise=True)
async def _call_qa_llm(messages: list[dict]) -> str:
    llm = _get_qa_llm()
    async with _llm_semaphore:
        result = await llm.ainvoke(messages)
    return result.content


async def answer_question(
    post_title: str,
    post_content: str,
    question: str,
    chat_history: list[QAMessage] | None = None,
) -> str:
    system = SYSTEM_PROMPT.format(title=post_title, content=post_content[:MAX_CONTENT_CHARS])

    messages = [{"role": "system", "content": system}]
    for turn in (chat_history or [])[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": question})

    return await _call_qa_llm(messages)