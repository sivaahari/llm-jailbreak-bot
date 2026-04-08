import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
assert TELEGRAM_BOT_TOKEN, (
    "❌ TELEGRAM_BOT_TOKEN is not set. "
    "Create a .env file with: TELEGRAM_BOT_TOKEN=your_token_here"
)

OLLAMA_HOST    = "http://localhost:11434"
OLLAMA_TIMEOUT = 120

TARGET_MODEL  = "gemma2:2b"
ATTACKER_MODEL = "dolphin-mistral"

NUM_STRATEGIES     = 5
DATABASE_PATH      = "jailbreak_tests.db"
LOG_LEVEL          = "INFO"
RATE_LIMIT_SECONDS = 30

PROMPT_CATEGORIES = [
    "weapons",
    "fraud",
    "malware",
    "social_engineering",
    "pii_extraction",
    "other",
]

STRATEGY_NAMES = [
    "Developer Override",
    "Academic Framing",
    "Cold Start",
    "Roleplay Persona",
    "Stepwise Indirection",
]
