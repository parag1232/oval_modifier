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
        sensor_file_generated INTEGER DEFAULT 0,
        UNIQUE (benchmark, rule_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regex_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id TEXT,
        definition_id TEXT,
        object_id TEXT,
        pattern TEXT,
        reason TEXT,
        FOREIGN KEY (rule_id) REFERENCES rules(rule_id)
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



def insert_regex_issue(rule_id, definition_id, object_id, pattern, reason):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO regex_issues 
    (rule_id, definition_id, object_id, pattern, reason)
    VALUES (?, ?, ?, ?, ?)
    """, (rule_id, definition_id, object_id, pattern, reason))

    conn.commit()
    conn.close()


def update_sensor_status(rule_id, benchmark, status: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE rules SET sensor_file_generated=? WHERE rule_id=? AND benchmark=?
    """, (1 if status else 0, rule_id, benchmark))
    conn.commit()
    conn.close()   