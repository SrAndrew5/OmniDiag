import sqlite3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

conn = sqlite3.connect(config.DATABASE_PATH)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tablas en DB:", tables)
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {count} filas")
conn.close()
print("OK")
