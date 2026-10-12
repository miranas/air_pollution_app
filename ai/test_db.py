import sqlite3

from ai.db import get_rag_connection,get_sql_connection

print("---RAG CONNECTION---")
with get_rag_connection() as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents;")
    print("Documents:", cur.fetchall())

print("---SQL CONNECTION---")
with get_sql_connection() as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM measurements;")
    print("Measurements:", cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM stations;")
    print("Stations:", cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM pollutants;")
    print("Pollutants:", cur.fetchall())

print("\n---test readonly agent permissions---")
try:
    with get_sql_connection() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TABLE hacker_input (id int);")
        cur.execute("INSERT INTO hacker_input VALUES (1);")
        conn.commit()
        print("Hacker's got access")
except Exception as e:
    print("He he, no access for the hacker")
    print(f"Razlog: {type(e).__name__}")
