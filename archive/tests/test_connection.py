"""Archived ad-hoc cloud database connection check.

Credentials are read from the environment; never hardcode them in source.
"""
import os
import urllib.parse

from sqlalchemy import create_engine

raw_password = os.getenv("DB_PASSWORD", "")

# URL-encode the password
safe_password = urllib.parse.quote(raw_password)

# Full URL wins if provided, otherwise build it from DB_* variables.
DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{os.getenv('DB_USER', 'postgres')}:{safe_password}"
    f"@{os.getenv('DB_HOST', '')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'postgres')}?sslmode=require"
)

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        print("Success, path to the cloud is open")


except Exception as e:
    print(f"Database connection failed {e}")
