import os

import psycopg2
import httpx
from pgvector.psycopg2 import register_vector

def isci_po_dokumentih(vprasanje, top_k=3):
    # 1. Povezava na bazo (credentials come from environment / .env)
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        password=os.getenv("DB_PASSWORD"),
        user=os.getenv("DB_USER", "airquality_user"),
        dbname=os.getenv("DB_NAME", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
    )
    register_vector(conn)
    cur = conn.cursor()

    # 2. Pretvori vprašanje v vektor (Ollama)
    response = httpx.post(
        "http://127.0.0.1:11434/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": vprasanje}
    )
    vektor = response.json()["embedding"]

    # 3. Poišči najbolj podobne fragmente (pgvector)
    cur.execute("""
        SELECT content, source, 1 - (embedding <=> %s::vector) AS podobnost
        FROM documents
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """, (vektor, vektor, top_k))

    # 4. Preberi rezultate
    rezultati = cur.fetchall()
    cur.close()
    conn.close()
    return rezultati

# 5. Test
vprasanje = "Zakaj ozon pade na NG Grčna?"
rezultati = isci_po_dokumentih(vprasanje)
for content, source, podobnost in rezultati:
    print(f"[{source}] podobnost={podobnost:.3f}\n{content[:200]}...\n")
