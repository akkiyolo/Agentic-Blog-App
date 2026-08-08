import pytest 
from httpx  import AsyncClient
from routers.posts import run_tagging
from unittest.mock import AsyncMock, patch
from tests.conftest import auth_header,create_test_user,login_user

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.mark.anyio
async def test_get_posts_empty(client:AsyncClient):
  response=await client.get("/api/posts")

  assert response.status_code==200
  data=response.json()
  assert data["posts"]==[]
  assert data["total"]==0
  assert data["has_more"] is False


@pytest.mark.anyio
async def test_get_posts_not_found(client:AsyncClient):
  response=await client.get("/api/posts/999")

  assert response.status_code==404
  assert response.json()["detail"]=="Post not found"


@pytest.mark.anyio
async def test_create_post_success(client: AsyncClient):
    user = await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.post(
        "/api/posts",
        json={"title": "My First Post", "content": "This is the content"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My First Post"
    assert data["content"] == "This is the content"
    assert data["user_id"] == user["id"]
    assert "id" in data
    assert "date_posted" in data
    assert data["author"]["username"] == "testuser"


@pytest.mark.anyio
async def test_create_post_unauthorized(client: AsyncClient):
    response = await client.post(
        "/api/posts",
        json={"title": "Test Post", "content": "Test content"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.anyio
async def test_update_post_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    response = await client.post(
        "/api/posts",
        json={"title": "Original Title", "content": "Original content"},
        headers=headers,
    )
    post_id = response.json()["id"]

    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["content"] == "Original content"


@pytest.mark.anyio
async def test_update_post_wrong_user(client: AsyncClient):
    await create_test_user(client, username="user1", email="user1@example.com")
    token1 = await login_user(client, email="user1@example.com")

    response = await client.post(
        "/api/posts",
        json={"title": "User 1's Post", "content": "Only user 1 can edit this"},
        headers=auth_header(token1),
    )
    post_id = response.json()["id"]

    await create_test_user(client, username="user2", email="user2@example.com")
    token2 = await login_user(client, email="user2@example.com")

    response = await client.patch(
        f"/api/posts/{post_id}",
        json={"title": "Hacked Title"},
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not Authorized to update this post"


@pytest.mark.anyio
async def test_get_posts_with_pagination(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)

    for i in range(5):
        response = await client.post(
            "/api/posts",
            json={"title": f"Post {i}", "content": f"Content for post {i}"},
            headers=headers,
        )
        assert response.status_code == 201

    response = await client.get("/api/posts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["posts"]) == 5
    assert data["has_more"] is False

    response = await client.get("/api/posts?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["posts"]) == 2
    assert data["has_more"] is True

    response = await client.get("/api/posts?skip=2&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["posts"]) == 2
    assert data["skip"] == 2
    assert data["limit"] == 2


@pytest.mark.anyio
async def test_new_post_starts_pending(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/posts",
        json={"title": "Agentic Post", "content": "Some content"},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    assert response.json()["tagging_status"] == "pending"


@pytest.mark.anyio
async def test_run_tagging_updates_post(client: AsyncClient, db_session):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/posts",
        json={"title": "Agentic Post", "content": "Some content"},
        headers=auth_header(token),
    )
    post_id = response.json()["id"]

    await run_tagging(post_id, "Agentic Post", "Some content", db=db_session)

    response = await client.get(f"/api/posts/{post_id}")
    data = response.json()
    assert data["tagging_status"] == "done"
    assert data["tags"] == ["test", "mock"]
    assert data["summary"] == "Mock summary."


@pytest.mark.anyio
async def test_run_tagging_marks_failed_on_llm_error(client: AsyncClient, db_session):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/posts",
        json={"title": "Bad Post", "content": "Content"},
        headers=auth_header(token),
    )
    post_id = response.json()["id"]

    with patch(
        "agents.tagging_agent._call_llm",
        new=AsyncMock(side_effect=Exception("boom")),
    ):
        await run_tagging(post_id, "Bad Post", "Content", db=db_session)

    response = await client.get(f"/api/posts/{post_id}")
    assert response.json()["tagging_status"] == "failed"


@pytest.mark.anyio
async def test_retag_requires_ownership(client: AsyncClient):
    await create_test_user(client, username="user1", email="user1@example.com")
    token1 = await login_user(client, email="user1@example.com")

    response = await client.post(
        "/api/posts",
        json={"title": "User 1's Post", "content": "Content"},
        headers=auth_header(token1),
    )
    post_id = response.json()["id"]

    await create_test_user(client, username="user2", email="user2@example.com")
    token2 = await login_user(client, email="user2@example.com")

    response = await client.post(
        f"/api/posts/{post_id}/retag",
        headers=auth_header(token2),
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_retag_not_found(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/posts/999/retag",
        headers=auth_header(token),
    )

    assert response.status_code == 404


