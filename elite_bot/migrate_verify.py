"""Add email verification and phone columns to app_users."""
import sqlite3
import sys
from pathlib import Path

db_path = Path(__file__).parent / "elite.db"
if not db_path.exists():
    print(f"Database not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check existing columns
cur.execute("PRAGMA table_info(app_users)")
cols = {row[1] for row in cur.fetchall()}

migrations = [
    ("phone", "ALTER TABLE app_users ADD COLUMN phone TEXT"),
    ("email_verified", "ALTER TABLE app_users ADD COLUMN email_verified BOOLEAN DEFAULT 1"),
    ("verify_code", "ALTER TABLE app_users ADD COLUMN verify_code TEXT"),
    ("verify_code_expires", "ALTER TABLE app_users ADD COLUMN verify_code_expires DATETIME"),
]

for col, sql in migrations:
    if col not in cols:
        cur.execute(sql)
        print(f"Added column: {col}")
    else:
        print(f"Column already exists: {col}")

conn.commit()
conn.close()
print("Done.")
