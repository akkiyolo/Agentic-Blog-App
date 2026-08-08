from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agents.draft_agent import run_draft_graph
from auth import CurrentUser
from database import get_db
from schemas import DraftGenerateRequest, DraftReviseRequest, DraftResponse

router = APIRouter()


@router.post("/generate", response_model=DraftResponse)
async def generate_draft(
    request: DraftGenerateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await run_draft_graph(topic=request.topic, db=db)
    return DraftResponse(**result)


@router.post("/revise", response_model=DraftResponse)
async def revise_draft(
    request: DraftReviseRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await run_draft_graph(
        topic=request.topic,
        db=db,
        feedback=request.feedback,
        previous_outline=request.previous_outline,
        previous_draft_title=request.previous_draft_title,
        previous_draft_content=request.previous_draft_content,
    )
    return DraftResponse(**result)