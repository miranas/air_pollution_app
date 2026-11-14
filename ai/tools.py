"""
Orodja za AI agenta.

Vsa orodja vrnejo JSON string, ki ga LLM razume.
"""

import json
import httpx
import redis
from ai.db import get_rag_connection, get_sql_connection
from ai import config


_redis = redis.from_url(config.REDIS_URL, decode_responses=True)


# ============================================================
# 1. SQL
# ============================================================

def sql_query(query: str) -> str:
    """
    Izvrši SQL SELECT poizvedbo v PostgreSQL (read-only).

    Args:
        query: SQL SELECT poizvedba.

    Returns:
        JSON string z rezultati ali napako.
    """
    q = query.strip().upper()
    if not q.startswith("SELECT"):
        return json.dumps({"error": "Samo SELECT poizvedbe."})
    if ";" in query.rstrip(";"):
        return json.dumps({"error": "Samo en stavek."})

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
    for word in forbidden:
        if word in q:
            return json.dumps({"error": f"Prepovedano: {word}"})

    if "LIMIT" not in q:
        query = query.rstrip(";") + " LIMIT 100;"

    try:
        with get_sql_connection() as conn:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            result = [dict(zip(cols, row)) for row in rows]
            return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================
# 2. RAG
# ============================================================

def rag_search(query: str, top_k: int = 3) -> str:
    """
    Poišči dokumente v pgvector.

    Args:
        query: iskalni niz.
        top_k: koliko rezultatov vrniti.

    Returns:
        JSON string z najdenimi kosi.
    """
    response = httpx.post(
        f"{config.OLLAMA_URL}/api/embeddings",
        json={"model": config.EMBEDDING_MODEL, "prompt": query},
        timeout=30,
    )
    vektor = response.json()["embedding"]

    with get_rag_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT content, source, 1 - (embedding <=> %s::vector) AS similarity
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """, (vektor, vektor, top_k))
        rows = cur.fetchall()
        result = [
            {"content": r[0], "source": r[1], "similarity": float(r[2])}
            for r in rows
        ]
        return json.dumps(result, ensure_ascii=False)


# ============================================================
# 3. REDIS
# ============================================================

def redis_latest(station: str = None) -> str:
    """Vrni zadnje meritve iz Redisa."""
    value = _redis.get("latest_merged_data")
    if value is None:
        return json.dumps({"error": "Ni podatka latest_merged_data"})

    data = json.loads(value)

    if station is None:
        return json.dumps(data, ensure_ascii=False)

    if station not in data:
        return json.dumps({"error": f"Ni postaje {station}"})

    return json.dumps(data[station], ensure_ascii=False)


def redis_history(period: str = "day") -> str:
    """Vrni zgodovino iz Redisa."""
    key = f"history_payload:{period}"
    value = _redis.get(key)
    if value is None:
        return json.dumps({"error": f"Ni podatka {key}"})
    return value