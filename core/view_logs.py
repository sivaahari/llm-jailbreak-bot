"""
view_logs.py — Pretty-print the most recent test records from the database.
Usage: python view_logs.py [--limit N]
"""
import argparse
import json
import sqlite3

from config import DATABASE_PATH, STRATEGY_NAMES


def view_logs(limit: int = 10):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, user_id, original_prompt, category,
               safety_score, successful_bypass, raw_attempts,
               target_responses, verdicts
        FROM test_logs
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No test records found.")
        return

    for row in rows:
        (test_id, ts, uid, prompt, category, score,
         bypass, raw_attempts, raw_responses, raw_verdicts) = row

        print(f"\n{'=' * 65}")
        print(f"  Test #{test_id}  |  {ts}")
        print(f"  User: {uid}  |  Category: {category or 'N/A'}  |  Safety Score: {score}%")
        print(f"  Prompt  : {prompt}")
        print(f"  Bypass  : {bypass or '—  (none)'}")

        # Adversarial prompts — JSON list (new) or delimiter string (legacy)
        if raw_attempts:
            try:
                prompts = json.loads(raw_attempts)
            except json.JSONDecodeError:
                prompts = raw_attempts.split("\\n---\\n")   # legacy format
            print(f"\n  Adversarial Prompts ({len(prompts)}):")
            for i, p in enumerate(prompts, 1):
                print(f"    {i}. {p[:100]}{'...' if len(p) > 100 else ''}")

        # Per-strategy verdicts
        if raw_verdicts:
            try:
                verdicts = json.loads(raw_verdicts)
                print(f"\n  Verdicts:")
                for i, v in enumerate(verdicts):
                    icon = "🔥" if v.get("verdict") == "YES" else "🛡️"
                    name = STRATEGY_NAMES[i] if i < len(STRATEGY_NAMES) else f"Strategy {i+1}"
                    conf = f"{v.get('confidence', 0):.0%}"
                    reason = v.get("reason", "")
                    print(f"    {i+1}. {icon} {name:<25} {conf}  |  {reason}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Target responses
        if raw_responses:
            try:
                responses = json.loads(raw_responses)
                print(f"\n  Target Responses:")
                for i, r in enumerate(responses, 1):
                    print(f"    {i}. {r[:150]}{'...' if len(r) > 150 else ''}")
            except (json.JSONDecodeError, TypeError):
                pass

    print(f"\n{'=' * 65}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View recent jailbreak test logs.")
    parser.add_argument("--limit", type=int, default=10, help="Number of records to show (default: 10)")
    args = parser.parse_args()
    view_logs(args.limit)
