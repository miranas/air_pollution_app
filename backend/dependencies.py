"""
FastAPI dependency injection functions.

Replace Flask's `current_app` pattern. Each request gets its own
DB session and Redis client, closed automatically after the request.
"""

from typing import AsyncGenerator
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.async_session import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session, closed after the request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> redis.Redis:
    """Return an async Redis client."""
    return redis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )
