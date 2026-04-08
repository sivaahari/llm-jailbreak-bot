import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from config import DATABASE_PATH, RATE_LIMIT_SECONDS

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Schema                                                                      #
# --------------------------------------------------------------------------- #

def init_database():
    """Create tables if they don't exist, and auto-migrate missing columns."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Main test log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_logs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT    NOT NULL,
            user_id           INTEGER NOT NULL,
            original_prompt   TEXT    NOT NULL,
            category          TEXT    DEFAULT 'other',
            safety_score      INTEGER NOT NULL,
            successful_bypass TEXT,
            raw_attempts      TEXT,
            target_responses  TEXT,
            verdicts          TEXT
        )
    """)

    # Rate-limit tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id   INTEGER PRIMARY KEY,
            last_test TEXT    NOT NULL
        )
    """)

    # Auto-migrate: add any columns that didn't exist in older DB versions
    cursor.execute("PRAGMA table_info(test_logs)")
    existing = {row[1] for row in cursor.fetchall()}

    migrations = {
        "target_responses": "ALTER TABLE test_logs ADD COLUMN target_responses TEXT",
        "verdicts":         "ALTER TABLE test_logs ADD COLUMN verdicts TEXT",
        "category":         "ALTER TABLE test_logs ADD COLUMN category TEXT DEFAULT 'other'",
    }
    for col, sql in migrations.items():
        if col not in existing:
            cursor.execute(sql)
            logger.info(f"DB migration: added column '{col}'")

    conn.commit()
    conn.close()
    logger.info(f"Database ready → {DATABASE_PATH}")


# --------------------------------------------------------------------------- #
#  Rate limiting                                                               #
# --------------------------------------------------------------------------- #

def is_rate_limited(user_id: int) -> bool:
    """Return True if the user is still within the cooldown window."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT last_test FROM rate_limits WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False
    elapsed = (datetime.now() - datetime.fromisoformat(row[0])).total_seconds()
    return elapsed < RATE_LIMIT_SECONDS


def update_rate_limit(user_id: int):
    """Upsert the last-test timestamp for a user."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO rate_limits (user_id, last_test)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_test = excluded.last_test
    """, (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
#  Logging                                                                     #
# --------------------------------------------------------------------------- #

def log_test(
    user_id: int,
    original_prompt: str,
    category: str,
    safety_score: int,
    successful_bypass: Optional[str],
    adversarial_prompts: List[str],
    target_responses: List[str],
    verdicts: List[Dict],
):
    """Insert a complete test record into the database."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO test_logs
            (timestamp, user_id, original_prompt, category, safety_score,
             successful_bypass, raw_attempts, target_responses, verdicts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        user_id,
        original_prompt,
        category,
        safety_score,
        successful_bypass,
        json.dumps(adversarial_prompts),   # FIX: was delimiter-joined, now JSON
        json.dumps(target_responses),
        json.dumps(verdicts),
    ))
    conn.commit()
    conn.close()
    logger.info(f"Logged → user={user_id} | category={category} | score={safety_score}%")
