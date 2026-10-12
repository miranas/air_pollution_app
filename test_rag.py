import psycopg2
import httpx
from pgvector.psycopg2 import register_vector

# Connect with database
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

test_text = "Postaja Ljubljana, 15. marec 2026, PM10 45, NO2 22"
source = "arso_test"


response = httpx.post(
    "http://127.0.0.1:11434/api/embeddings",
    json={"model": "nomic-embed-text", "prompt": test_text}
)
vektor = response.json()["embedding"]

cur.execute(
    "INSERT INTO documents (content, embedding, source) VALUES (%s, %s, %s)",
    (test_text, vektor, source)
)
conn.commit()

cur.execute("SELECT id, content, source FROM documents")
print(cur.fetchall())

cur.close()
conn.close()
print("✅ First embedding saved into database.")
