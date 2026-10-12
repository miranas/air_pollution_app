import contextlib
import psycopg2
import pwd
from pgvector.psycopg2 import register_vector
from ai import config

@contextlib.contextmanager
def get_rag_connection():
    """Full access to the rag database connection"""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()



@contextlib.contextmanager
def get_sql_connection():
    """Limited access to the rag database connection (read-only)"""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.SQL_AGENT_USER,
        password=config.SQL_AGENT_PASSWORD,
    )
    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()







