import os
import psycopg2
import httpx
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect(
    host="127.0.0.1",
    password="mcrtJiIRdYj12",
    user="airquality_user",
    dbname="postgres",
    port=5432
)
register_vector(conn)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        content TEXT,
        embedding vector(768),
        source TEXT
    );
""")
conn.commit()

folder = "rag_sources"
for filename in os.listdir(folder):
    if not filename.endswith(".txt"):
        continue
    path = os.path.join(folder, filename)
    with open(path, "r", encoding="utf-8") as f:
        vsebina = f.read()

    fragmenti = [f.strip() for f in vsebina.split("\n\n") if len(f.strip()) > 100]

    for fragment in fragmenti:
        response = httpx.post(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": fragment}
        )
        vektor = response.json()["embedding"]

        cur.execute(
            "INSERT INTO documents (content, embedding, source) VALUES (%s, %s, %s)",
            (fragment, vektor, filename)
        )
        print(f"✅ {filename}: {fragment[:60]}...")

conn.commit()
cur.close()
conn.close()
print("Vektorizacija končana.")
