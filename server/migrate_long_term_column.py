"""One-time migration: fixes isolation_certificates.long_term, which was created as
VARCHAR(100) instead of BOOLEAN (the table was first auto-created before
IsolationCertificate.long_term had a `False` default, so IsolationCertificateDb's
type-inference saw None instead of a bool and fell back to VARCHAR).

Symptom this caused: psycopg2 returns VARCHAR columns as raw strings, so the stored
text 'false' was read back as a non-empty (truthy) Python string, making every
certificate appear "long term" in the UI regardless of its real value.

Run once from the server/ directory: python migrate_long_term_column.py
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(
    host=os.environ.get('DB_HOST', 'localhost'),
    database=os.environ.get('DB_NAME', 'ptw_database'),
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD'),
)
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'isolation_certificates' AND column_name = 'long_term'
        """)
        row = cur.fetchone()
        if row is None:
            print("isolation_certificates.long_term column not found — nothing to migrate.")
        elif row[0] == 'boolean':
            print("isolation_certificates.long_term is already BOOLEAN — nothing to migrate.")
        else:
            cur.execute("""
                UPDATE isolation_certificates
                SET long_term = 'false'
                WHERE long_term IS NULL OR long_term NOT IN ('true', 'false')
            """)
            cur.execute("""
                ALTER TABLE isolation_certificates
                ALTER COLUMN long_term TYPE boolean USING long_term::boolean,
                ALTER COLUMN long_term SET DEFAULT FALSE,
                ALTER COLUMN long_term SET NOT NULL
            """)
            conn.commit()
            print("Migrated isolation_certificates.long_term from VARCHAR to BOOLEAN.")
finally:
    conn.close()
