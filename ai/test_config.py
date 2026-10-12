from ai import config

print("DB_HOST:", config.DB_HOST)
print("DB_PORT:", config.DB_PORT)
print("DB_NAME:", config.DB_NAME)
print("DB_USER:", config.DB_USER)
print("DB_PASSWORD set:", bool(config.DB_PASSWORD))

print("SQL_AGENT_USER:", config.SQL_AGENT_USER)
print("SQL_AGENT_PASSWORD set:", bool(config.SQL_AGENT_PASSWORD))

print("OLLAMA_URL:", config.OLLAMA_URL)
print("EMBEDDING_MODEL:", config.EMBEDDING_MODEL)
print("ROUTER_MODEL:", config.ROUTER_MODEL)

print("DEEPSEEK_API_KEY set:", bool(config.DEEPSEEK_API_KEY))
print("DEEPSEEK_BASE_URL:", config.DEEPSEEK_BASE_URL)
print("DEEPSEEK_MODEL:", config.DEEPSEEK_MODEL)

print("REDIS_URL:", config.REDIS_URL)
