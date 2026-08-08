import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from database import get_db, AsyncSessionLocal
from schemas import PostCreate, PostResponse, PostUpdate, PaginatedPostsResponse

from auth import CurrentUser
from agents.tagging_agent import generate_post_metadata

logger = logging.getLogger(__name__)

router = APIRouter()


async def run_tagging(post_id: int, title: str, content: str) -> None:
    """Background job: generate tags/summary for a post and persist the result."""
    async with AsyncSessionLocal() as session:
        try:
            meta = await generate_post_metadata(title, content)
            await session.execute(
                update(models.Post)
                .where(models.Post.id == post_id)
                .values(
                    tags=meta.tags,
                    summary=meta.summary,
                    meta_description=meta.meta_description,
                    tagging_status="done",
                ),
            )
            await session.commit()
        except Exception:
            logger.exception("Auto-tagging failed for post_id=%s", post_id)
            await session.execute(
                update(models.Post)
                .where(models.Post.id == post_id)
                .values(tagging_status="failed"),
            )
            await session.commit()


@router.get("", response_model=PaginatedPostsResponse)
async def get_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):

    count_result = await db.execute(select(func.count()).select_from(models.Post))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
        .offset(skip)
        .limit(limit),
    )
    posts = result.scalars().all()

    has_more=skip+len(posts)<total

    return PaginatedPostsResponse(
        posts=[PostResponse.model_validate(post) for post in posts],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    post: PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):

    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=current_user.id,
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])

    background_tasks.add_task(run_tagging, new_post.id, new_post.title, new_post.content)

    return new_post


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id),
    )
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.put("/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int,
    post_data: PostCreate,
    current_user:CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id!=current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not Authorized to update this post"
        )

    post.title = post_data.title
    post.content = post_data.content
    post.tagging_status = "pending"

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    background_tasks.add_task(run_tagging, post.id, post.title, post.content)

    return post


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int,
    post_data: PostUpdate,
    current_user:CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id!=current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not Authorized to update this post"
        )

    update_data = post_data.model_dump(exclude_unset=True)
    content_changed = "title" in update_data or "content" in update_data
    for field, value in update_data.items():
        setattr(post, field, value)

    if content_changed:
        post.tagging_status = "pending"

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    if content_changed:
        background_tasks.add_task(run_tagging, post.id, post.title, post.content)

    return post


@router.post("/{post_id}/retag", response_model=PostResponse)
async def retag_post(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """Manually re-run the auto-tagging agent for a post stuck in pending/failed."""
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author)).where(models.Post.id == post_id),
    )
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not Authorized")

    post.tagging_status = "pending"
    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    background_tasks.add_task(run_tagging, post.id, post.title, post.content)

    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int,current_user:CurrentUser ,db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    if post.user_id!=current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not Authorized to delete this post"
        )

    await db.delete(post)
    await db.commit()