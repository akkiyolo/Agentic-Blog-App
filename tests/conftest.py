import os 
from collections.abc import AsyncGenerator

os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://bloguser:blogpass@localhost/test_blog"
)
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

os.environ["S3_ACCESS_KEY_ID"] = "testing"
os.environ["S3_SECRET_ACCESS_KEY"] = "testing"
os.environ["S3_REGION"] = "us-east-1"

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

os.environ["GOOGLE_API_KEY"] = "test-google-api-key"

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from types import SimpleNamespace
from schemas import PostMetadata, DraftOutput

from database import Base, get_db
from main import app

from unittest.mock import AsyncMock, patch
from schemas import PostMetadata

pytest_plugins=["anyio"]

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(
    test_engine,
    setup_database,
) -> AsyncGenerator[AsyncSession]:
    conn = await test_engine.connect()
    trans = await conn.begin()

    test_async_session = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with test_async_session() as session:
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
            await conn.close()


@pytest.fixture
def mocked_aws():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=os.environ["S3_BUCKET_NAME"])
        yield s3


@pytest.fixture
async def client(
    db_session: AsyncSession,
    mocked_aws,
) -> AsyncGenerator[AsyncClient]:

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def create_test_user(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "testpassword123",
) -> dict:
    response = await client.post(
        "/api/users",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()


async def login_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpassword123",
) -> str:
    response = await client.post(
        "/api/users/token",
        data={
            "username": email,
            "password": password,
        },
    )
    assert response.status_code == 200, f"Failed to login: {response.text}"
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_tagging_llm(request):
    """All tests get a mocked tagging LLM by default — no real network
    calls, deterministic output, no dependency on a real API key.
    The retry decorator on _call_llm stays live since we only swap out
    the LLM object, not _call_llm itself.

    Tests that need the real LLM-selection logic (e.g. missing-key
    behavior) opt out with @pytest.mark.no_mock_llm.
    """
    if "no_mock_llm" in request.keywords:
        yield
        return

    fake_metadata = PostMetadata(
        tags=["test", "mock"],
        summary="Mock summary.",
        meta_description="Mock meta description.",
    )
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=fake_metadata)

    with patch("agents.tagging_agent._get_structured_llm", return_value=mock_llm):
        yield


@pytest.fixture(autouse=True)
def mock_draft_llm(request):
    """Mocks the draft-assist agent's outline/draft LLMs — no real Gemini
    calls in tests. Opt out with @pytest.mark.no_mock_llm.
    """
    if "no_mock_llm" in request.keywords:
        yield
        return

    mock_outline_llm = AsyncMock()
    mock_outline_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content="1. Intro\n2. Body\n3. Conclusion"),
    )

    fake_draft = DraftOutput(title="Mock Draft Title", content="Mock draft content.")
    mock_draft_llm_obj = AsyncMock()
    mock_draft_llm_obj.ainvoke = AsyncMock(return_value=fake_draft)

    with patch("agents.draft_agent._get_outline_llm", return_value=mock_outline_llm), \
         patch("agents.draft_agent._get_draft_llm", return_value=mock_draft_llm_obj):
        yield
