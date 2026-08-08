import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user


@pytest.mark.anyio
async def test_generate_draft_requires_auth(client: AsyncClient):
    response = await client.post("/api/drafts/generate", json={"topic": "Kubernetes basics"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_generate_draft_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/drafts/generate",
        json={"topic": "Kubernetes basics for beginners"},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["draft_title"] == "Mock Draft Title"
    assert data["draft_content"] == "Mock draft content."
    assert data["outline"] == "1. Intro\n2. Body\n3. Conclusion"
    assert isinstance(data["sources"], list)


@pytest.mark.anyio
async def test_generate_draft_topic_too_short(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/drafts/generate",
        json={"topic": "ab"},
        headers=auth_header(token),
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_revise_draft_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.post(
        "/api/drafts/revise",
        json={
            "topic": "Kubernetes basics",
            "feedback": "make it more casual",
            "previous_outline": "1. Intro",
            "previous_draft_title": "Old Title",
            "previous_draft_content": "Old content",
        },
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["draft_title"] == "Mock Draft Title"
    assert data["outline"] == "1. Intro"  # preserved, not regenerated
    assert data["sources"] == []


@pytest.mark.anyio
async def test_revise_draft_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/drafts/revise",
        json={
            "topic": "Kubernetes basics",
            "feedback": "shorter",
            "previous_outline": "1. Intro",
            "previous_draft_title": "Old",
            "previous_draft_content": "Old content",
        },
    )
    assert response.status_code == 401