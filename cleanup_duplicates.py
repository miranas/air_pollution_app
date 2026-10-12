import psycopg2
conn = psycopg2.connect(
    host="127.0.0.1", port=5432, dbname="postgres",
    user="airquality_user", password="mcrtJiIRdYj12"
)
cur = conn.cursor()
cur.execute("DELETE FROM documents WHERE source = 'arso_test';")
print(f"Izbrisanih: {cur.rowcount}")
conn.commit()
cur.close()
conn.close()