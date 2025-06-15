import sqlite3
import os

DB_PATH = "data/stig.db"

def initialize_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        benchmark TEXT,
        rule_id TEXT,
        definition_id TEXT,
        oval_path TEXT,
        supported INTEGER,
        unsupported_probes TEXT,
        manual INTEGER,
        excluded INTEGER DEFAULT 0,
        benchmark_type TEXT,
        UNIQUE (benchmark, rule_id)
    )
    """)

    conn.commit()
    conn.close()

def insert_rule(benchmark, rule_id, definition_id, oval_path, supported=None, unsupported_probes=None, manual=False,benchmark_type=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO rules 
    (benchmark, rule_id, definition_id, oval_path, supported, unsupported_probes, manual,benchmark_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (benchmark, rule_id, definition_id, oval_path, supported, unsupported_probes, manual,benchmark_type))

    conn.commit()
    conn.close()