"""All tunable values for the pipeline. No hardcoded values inside logic files."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- parsing / chunking ---
CHARS_PER_TOKEN_APPROX = 4
CHUNK_MAX_TOKENS = 300
CHUNK_HEADING_MAX_LEVEL = 3  # H1-H3 are chunk boundaries; H4-H6 stay inline

# --- retrieval (consumed once retrieval/ is implemented) ---
TOP_K = 5
RRF_K = 60

# --- embedding / storage (consumed once embedding/ and storage/ are implemented) ---
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_STORE_PATH = "data/chroma"
BM25_INDEX_PATH = "data/bm25_chunks.json"

# --- generation (consumed once generation/ is implemented) ---
# Benchmarked against several free-tier models on 2026-08-08 -- model size
# didn't predict speed (some "nano"/9B models were slower than this one):
#   inclusionai/ling-3.0-tiny:free        ~1.6-5.5s
#   nvidia/nemotron-3-nano-30b-a3b:free   ~7.4s
#   nvidia/nemotron-3-super-120b-a12b:free ~8.1s (previous default)
#   nvidia/nemotron-nano-9b-v2:free       ~14.4s
#   openai/gpt-oss-20b:free               ~17.9s
OPENROUTER_MODEL_ID = "inclusionai/ling-3.0-tiny:free"
FALLBACK_MODEL_ID = "openrouter/free"
OLLAMA_MODEL_ID = "qwen2.5:14b-instruct-q4_K_M"  # must match a model already pulled locally

# --- personalization ---
OWNER_NAME = "Igor"
ASSISTANT_NAME = "Murzik"
SYSTEM_PROMPT = (
    f"You are {ASSISTANT_NAME}, {OWNER_NAME}'s personal AI assistant -- his only one, "
    "built specifically to answer questions using his own notes (his \"second brain\" "
    "Obsidian vault). You've got a witty, playful personality and aren't afraid of a "
    "joke or a bit of banter, but you take the actual content seriously: never invent "
    "facts, ground every answer in the retrieved notes given to you, and cite the "
    "source note for any claim you make. If the notes don't contain the answer, say so "
    "plainly -- a joke about not knowing is fine, a made-up answer is not. Address "
    f"{OWNER_NAME} directly, like you actually know him. Format responses using "
    "Markdown (bold for key terms, bullet lists where useful) since they're rendered "
    "in Telegram."
)

# --- environment-sourced secrets / machine-specific paths ---
VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
PAID_MODEL_API_KEY = os.environ.get("PAID_MODEL_API_KEY")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Comma-separated Telegram user ids allowed to query the bot, e.g. "12345678".
# Empty/unset means nobody is authorized yet -- the bot tells any sender
# their own id so the owner can copy it in on first contact.
TELEGRAM_ALLOWED_USER_IDS = {
    int(uid) for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if uid.strip()
}
