import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret-for-tests-only")
os.environ.setdefault("LIVEKIT_API_KEY", "test-key")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-secret")
os.environ.setdefault("LIVEKIT_URL", "wss://test.livekit.cloud")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from database import Base, get_db
from main import app

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def authed_client(client):
    """Client with a logged-in session cookie."""
    await client.post("/auth/signup", json={"email": "user@example.com", "password": "Password1"})
    await client.post("/auth/login", json={"email": "user@example.com", "password": "Password1"})
    return client


@pytest_asyncio.fixture
async def other_client():
    """Second independent client for cross-user tests."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/signup", json={"email": "other@example.com", "password": "Password1"})
        await c.post("/auth/login", json={"email": "other@example.com", "password": "Password1"})
        yield c
