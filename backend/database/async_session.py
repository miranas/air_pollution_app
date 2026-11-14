"""
Async database engine and session factory for FastAPI.

Coexists with the sync session.py used by Flask. Both share the same
models from backend/database/models.py.

Uses SQLAlchemy 2.0 async API with asyncpg driver.
"""
import os
import urllib.parse

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Load env vars (same behavior as Flask's session.py)
load_dotenv(override=True)

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

if DB_PASSWORD is None:
    raise RuntimeError("DB_PASSWORD environment variable is not set")

safe_password = urllib.parse.quote(DB_PASSWORD)

# Note: postgresql+asyncpg (not just postgresql)
DATABASE_URL = (
    f"postgresql+asyncpg://{DB_USER}:{safe_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,             # don't log every query (unlike Flask's sync session)
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,     # verify connection before use
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # required for FastAPI
)
