import psycopg2
conn = psycopg2.connect(
    host="127.0.0.1", port=5432, dbname="postgres",
    user="airquality_user", password="mcrtJiIRdYj12"
)
cur = conn.cursor()
cur.execute("SELECT id, content, source, subvector(embedding, 1, 3) FROM documents ORDER BY id DESC LIMIT 3;")
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
