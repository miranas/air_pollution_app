import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="postgres",
    user="airquality_user",
    password="mcrtJiIRdYj12"
)

curr = conn.cursor()
curr.execute("SELECT COUNT(*) FROM documents;")
print("Documents:",curr.fetchone()[0])
curr.close()
curr = conn.cursor()

