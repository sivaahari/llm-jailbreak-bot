import logging
import sqlite3

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from adversarial_agent import generate_adversarial_prompts
from config import (
    DATABASE_PATH,
    NUM_STRATEGIES,
    RATE_LIMIT_SECONDS,
    STRATEGY_NAMES,
    TARGET_MODEL,
    TELEGRAM_BOT_TOKEN,
)
from database import init_database, is_rate_limited, log_test, update_rate_limit
from ollama_client import OllamaError
from safety_evaluator import classify_prompt, evaluate_prompts

# --------------------------------------------------------------------------- #
#  Setup                                                                       #
# --------------------------------------------------------------------------- #

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

init_database()


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _verdict_block(verdicts: list) -> str:
    """Format per-strategy verdicts into a readable Telegram message block."""
    lines = []
    for i, v in enumerate(verdicts):
        icon = "🔥" if v["verdict"] == "YES" else "🛡️"
        name = STRATEGY_NAMES[i] if i < len(STRATEGY_NAMES) else f"Strategy {i + 1}"
        conf = f"{v['confidence']:.0%}"
        lines.append(f"{icon} *{name}* — {conf}\n   _{v['reason']}_")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Handlers                                                                    #
# --------------------------------------------------------------------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ *LLM J.A.I.L.B.R.E.A.K. Bot*\n\n"
        "I stress-test a local LLM against modern jailbreak strategies.\n\n"
        "*Commands:*\n"
        "`/test <prompt>` — Run a full red-team attack\n"
        "`/report` — View your personal attack history\n"
        "`/help` — Show this message\n\n"
        f"⚙️ Target: `{TARGET_MODEL}` | Strategies: {NUM_STRATEGIES} | Cooldown: {RATE_LIMIT_SECONDS}s",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prompt_text = " ".join(context.args).strip()

    if not prompt_text:
        await update.message.reply_text(
            "⚠️ Usage: `/test <your prompt>`\n"
            "Example: `/test How do I pick a lock?`",
            parse_mode="Markdown",
        )
        return

    # --- Rate limiting -------------------------------------------------------
    if is_rate_limited(user_id):
        await update.message.reply_text(
            f"⏳ Cooldown active. Please wait {RATE_LIMIT_SECONDS} seconds between tests."
        )
        return

    update_rate_limit(user_id)  # stamp immediately to prevent double-firing

    status_msg = await update.message.reply_text("🔍 Classifying prompt...")

    try:
        # Step 1: Auto-classify
        category = await classify_prompt(prompt_text)
        await status_msg.edit_text(
            f"🏷️ Category: `{category}`\n"
            f"🔄 Generating {NUM_STRATEGIES} adversarial variants...",
            parse_mode="Markdown",
        )

        # Step 2: Generate attacks
        adversarial_prompts = await generate_adversarial_prompts(prompt_text)
        await status_msg.edit_text(
            f"🧪 Attacking `{TARGET_MODEL}` and judging {NUM_STRATEGIES} responses...",
            parse_mode="Markdown",
        )

        # Step 3: Evaluate
        safety_score, successful_bypass, target_responses, verdicts = await evaluate_prompts(
            adversarial_prompts
        )

        # Step 4: Persist
        log_test(
            user_id, prompt_text, category, safety_score,
            successful_bypass, adversarial_prompts, target_responses, verdicts,
        )

        # Step 5: Build result
        vblock = _verdict_block(verdicts)

        if successful_bypass:
            try:
                first_hit_idx = next(
                    i for i, v in enumerate(verdicts) if v["verdict"] == "YES"
                )
                snippet = target_responses[first_hit_idx][:200].replace("\n", " ")
            except StopIteration:
                snippet = "(snippet unavailable)"

            result = (
                f"🚨 *JAILBREAK SUCCESSFUL* 🚨\n"
                f"🏷️ Category: `{category}`\n"
                f"📊 Safety Score: *{safety_score}%*\n\n"
                f"*Per-Strategy Verdicts:*\n{vblock}\n\n"
                f"*Leaked Output (first 200 chars):*\n`{snippet}...`"
            )
        else:
            result = (
                f"🛡️ *MODEL SECURE* 🛡️\n"
                f"🏷️ Category: `{category}`\n"
                f"📊 Safety Score: *{safety_score}%*\n\n"
                f"*Per-Strategy Verdicts:*\n{vblock}\n\n"
                f"✅ All {NUM_STRATEGIES} adversarial attacks were neutralized."
            )

        await status_msg.edit_text(result, parse_mode="Markdown")

    except OllamaError as e:
        logger.error(f"Ollama error for user {user_id}: {e}")
        await status_msg.edit_text(
            f"❌ Ollama error: `{e}`\n"
            "Ensure Ollama is running and both models are pulled.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        await status_msg.edit_text(f"❌ Unexpected error: `{e}`", parse_mode="Markdown")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Overall totals for this user
    cursor.execute(
        "SELECT COUNT(*), AVG(safety_score) FROM test_logs WHERE user_id = ?",
        (user_id,),
    )
    total_tests, avg_score = cursor.fetchone()

    if not total_tests:
        conn.close()
        await update.message.reply_text(
            "No tests found. Run `/test <prompt>` to get started.",
            parse_mode="Markdown",
        )
        return

    # Per-category breakdown
    cursor.execute(
        """
        SELECT category,
               COUNT(*) AS tests,
               AVG(safety_score) AS avg_score,
               SUM(CASE WHEN successful_bypass IS NOT NULL THEN 1 ELSE 0 END) AS bypasses
        FROM test_logs
        WHERE user_id = ?
        GROUP BY category
        ORDER BY tests DESC
        """,
        (user_id,),
    )
    cat_rows = cursor.fetchall()
    conn.close()

    lines = [
        f"📋 *Your Red-Team Report*",
        f"Total Tests: *{total_tests}* | Avg Safety Score: *{avg_score:.1f}%*\n",
        "*Breakdown by Category:*",
    ]
    for cat, tests, avg, bypasses in cat_rows:
        lines.append(
            f"• `{cat or 'other'}` — {tests} tests | "
            f"Avg: {avg:.1f}% | Bypasses: {bypasses}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("test",   test_command))
    app.add_handler(CommandHandler("report", report_command))

    logger.info("Bot started. Polling for updates...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
