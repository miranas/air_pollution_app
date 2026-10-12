import os
from dotenv import load_dotenv

load_dotenv()

# DB – RAG (full access)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# DB – SQL agent (read-only)
SQL_AGENT_USER = os.getenv("SQL_AGENT_USER")
SQL_AGENT_PASSWORD = os.getenv("SQL_AGENT_PASSWORD")

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "sokol-4b-slo")

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")