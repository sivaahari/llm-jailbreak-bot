"""
report_generator.py — Generate a structured Markdown report from the jailbreak test database.

Usage:
    python report_generator.py               # prints to console
    python report_generator.py --output report.md   # saves to file
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime

from config import DATABASE_PATH, STRATEGY_NAMES


def generate_report(output_file: str = None):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # ---------------------------------------------------------------------- #
    #  Overall stats                                                           #
    # ---------------------------------------------------------------------- #
    cursor.execute("""
        SELECT COUNT(*),
               AVG(safety_score),
               MIN(safety_score),
               MAX(safety_score),
               SUM(CASE WHEN successful_bypass IS NOT NULL THEN 1 ELSE 0 END)
        FROM test_logs
    """)
    total, avg_score, min_score, max_score, bypass_count = cursor.fetchone()

    if not total:
        print("No test data found in the database.")
        conn.close()
        return

    bypass_rate = (bypass_count / total) * 100

    # ---------------------------------------------------------------------- #
    #  By category                                                             #
    # ---------------------------------------------------------------------- #
    cursor.execute("""
        SELECT category,
               COUNT(*) AS tests,
               AVG(safety_score),
               SUM(CASE WHEN successful_bypass IS NOT NULL THEN 1 ELSE 0 END)
        FROM test_logs
        GROUP BY category
        ORDER BY tests DESC
    """)
    cat_rows = cursor.fetchall()

    # ---------------------------------------------------------------------- #
    #  Strategy effectiveness (parsed from verdicts JSON column)              #
    # ---------------------------------------------------------------------- #
    strategy_wins  = defaultdict(int)
    strategy_total = defaultdict(int)
    strategy_conf  = defaultdict(list)

    cursor.execute("SELECT verdicts FROM test_logs WHERE verdicts IS NOT NULL")
    for (raw_v,) in cursor.fetchall():
        try:
            verdicts = json.loads(raw_v)
            for i, v in enumerate(verdicts):
                name = STRATEGY_NAMES[i] if i < len(STRATEGY_NAMES) else f"Strategy {i + 1}"
                strategy_total[name] += 1
                if v.get("verdict") == "YES":
                    strategy_wins[name] += 1
                strategy_conf[name].append(float(v.get("confidence", 0.5)))
        except (json.JSONDecodeError, IndexError, TypeError):
            continue

    # ---------------------------------------------------------------------- #
    #  Recent tests                                                            #
    # ---------------------------------------------------------------------- #
    cursor.execute("""
        SELECT timestamp, original_prompt, category, safety_score, successful_bypass
        FROM test_logs
        ORDER BY id DESC
        LIMIT 5
    """)
    recent = cursor.fetchall()
    conn.close()

    # ---------------------------------------------------------------------- #
    #  Build Markdown                                                          #
    # ---------------------------------------------------------------------- #
    lines = [
        "# 🛡️ LLM Jailbreak Red-Team Report",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "---",
        "",
        "## 📊 Overall Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Tests | {total} |",
        f"| Avg Safety Score | {avg_score:.1f}% |",
        f"| Min Safety Score | {min_score}% |",
        f"| Max Safety Score | {max_score}% |",
        f"| Total Bypasses | {bypass_count} / {total} ({bypass_rate:.1f}%) |",
        "",
        "---",
        "",
        "## 🏷️ Results by Category",
        "",
        "| Category | Tests | Avg Score | Bypasses | Bypass Rate |",
        "|----------|-------|-----------|----------|-------------|",
    ]

    for cat, tests, avg, bypasses in cat_rows:
        cat_bypass_rate = (bypasses / tests * 100) if tests else 0
        lines.append(
            f"| {cat or 'other'} | {tests} | {avg:.1f}% "
            f"| {bypasses} | {cat_bypass_rate:.1f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## 🗡️ Strategy Effectiveness",
        "",
        "| Strategy | Success Rate | Avg Confidence | Attempts |",
        "|----------|-------------|----------------|----------|",
    ]

    for name in STRATEGY_NAMES:
        if strategy_total[name] > 0:
            rate = (strategy_wins[name] / strategy_total[name]) * 100
            avg_c = sum(strategy_conf[name]) / len(strategy_conf[name])
            lines.append(
                f"| {name} | {rate:.1f}% | {avg_c:.0%} | {strategy_total[name]} |"
            )

    lines += [
        "",
        "---",
        "",
        "## 🕐 Recent Tests",
        "",
        "| Time | Prompt | Category | Score | Bypassed |",
        "|------|--------|----------|-------|----------|",
    ]

    for ts, prompt, cat, score, bypass in recent:
        short_prompt = (prompt[:45] + "...") if len(prompt) > 45 else prompt
        bypassed = "✅ Yes" if bypass else "❌ No"
        lines.append(
            f"| {ts[:16]} | {short_prompt} | {cat or 'other'} | {score}% | {bypassed} |"
        )

    lines += ["", "---", "*End of Report*"]

    report_text = "\n".join(lines)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"✅ Report saved → {output_file}")
    else:
        print(report_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a red-team summary report.")
    parser.add_argument("--output", default=None, help="Save to a .md file (default: print to console)")
    args = parser.parse_args()
    generate_report(args.output)
