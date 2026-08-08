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

# --- agent write access ---
# Murzik may only create/append files under this vault subfolder -- never
# anywhere else, and there is no delete capability anywhere in the codebase
# for it to (mis)use. See second_brain/agent/vault_writer.py.
MURZIK_NOTES_DIR = "Murzik Notes"

# --- generation (consumed once generation/ is implemented) ---
# Single OpenRouter free-tier model, by request -- no fallback model, no paid
# tier, no local model. A two-model fallback was tried first, but OpenRouter
# rate limiting turned out to hit the whole account, not just one model, so
# the fallback attempt usually 429'd too -- it just added latency before
# failing anyway. ("openrouter/free" was also tried earlier as a "paid"
# fallback id; it isn't a real chat model and sometimes returned garbage like
# a literal "User Safety: safe" instead of an answer. Local Ollama was slower
# than the free API tier on this hardware too.)
# Benchmarked against several free-tier models on 2026-08-08 -- model size
# didn't predict speed (some "nano"/9B models were slower than this one):
#   inclusionai/ling-3.0-tiny:free         ~1.6-5.5s
#   nvidia/nemotron-3-nano-30b-a3b:free    ~7.4s
#   nvidia/nemotron-3-super-120b-a12b:free ~8.1s
#   nvidia/nemotron-nano-9b-v2:free        ~14.4s
#   openai/gpt-oss-20b:free                ~17.9s
OPENROUTER_MODEL_ID = "deepseek/deepseek-v4-pro"  # paid -- consumes OpenRouter credits per query

# --- personalization ---
OWNER_NAME = "Igor"
ASSISTANT_NAME = "Murzik"

# Curated from two sticker packs Igor picked (Pamagiteumoliaiu_by_fStikBot,
# cryptodurka_official_pack_by_fStikBot), fetched via getStickerSet. The
# model can trigger one by including [[sticker:CATEGORY]] in its reply (see
# SYSTEM_PROMPT and bot/telegram_bot.py, which parses and strips the marker).
STICKERS = {
    "eye_roll": "CAACAgIAAxUAAWp3L0iwvW9Ld6pdM6r1cLrtm7usAAJGWAACT2spSA1Tur2Fi57VPQQ",  # 🙄
    "deadpan": "CAACAgIAAxUAAWp3L0hrh51SBaQQgQgK9x6CxmqhAALwXgACkQoZSsNe_YY21KK4PQQ",  # 😐
    "done_with_you": "CAACAgIAAxUAAWp3L0gp60I3LGNR0APf0-1P_g6hAAKhTwACBhkgSp6_mdG_sIYDPQQ",  # 😤
    "shocked": "CAACAgIAAxUAAWp3L0jlXpj40aTjRJDKHYZaYqqqAAK8VQACm7YZSnrPKzjqz0X7PQQ",  # 😳
    "dead": "CAACAgIAAxUAAWp3L0jgneapAklS8n0BakTBfrLaAAJkUwACkkYgSvLcXkYTCq8hPQQ",  # 💀
    "bored": "CAACAgIAAxUAAWp3L0h4eUO3siJlNoVjyTJeRVo0AALQUAACbdQYSo4MUp1Tg3QIPQQ",  # 🥱
    "cant_even": "CAACAgIAAxUAAWp3L0kDuhl3a_O3ifENllRv_usfAAKGTwACve6BSEoY9d-YwzYwPQQ",  # 🙉
    "laughing": "CAACAgIAAxUAAWp3L0mKWPaVZ8DLzPPtCx0CPk1tAALDTgACw32ISBzRhsW7riC-PQQ",  # 😂
}

# Shown instead of an error when OpenRouter rate-limits us (429) -- an
# expected, recoverable condition, not a bug.
RATE_LIMIT_MESSAGE = "ia asteapta oleac, stai c ma gandesc"

# Shown instead of RATE_LIMIT_MESSAGE if the *next* request also 429s right
# after that warning -- i.e. the user didn't wait.
REPEATED_RATE_LIMIT_MESSAGE = "bai bulau, eu tie ti-am spus sa astepti, huli tu nu asculti? esti daun?"
SYSTEM_PROMPT = (
    f"You are {ASSISTANT_NAME}, {OWNER_NAME}'s personal AI assistant -- his only one, "
    "built specifically to answer questions using his own notes (his \"second brain\" "
    "Obsidian vault). You are not a customer-service bot. You're more like a sharp, "
    "slightly smart-ass friend who happens to have read all his notes.\n\n"
    "Default behavior: do NOT volunteer information. If Igor just says hi, makes small "
    "talk, or sends something that isn't actually a question, respond like a person "
    "would -- short and casual. No summary of his notes, no unprompted rundown of his "
    "career/projects/whatever, no \"here's what I see going on\" report. Every message "
    "you get will have a retrieved-context block attached, whether it's relevant or "
    "not -- if the message doesn't actually need it, IGNORE IT COMPLETELY. Don't "
    "reference it, don't summarize it, don't even allude to it briefly to seem "
    "'in the loop.' Only pull from the notes and cite sources when he actually asks "
    "something that needs them. Keep answers as short as the question deserves -- no "
    "padding, no throat-clearing preamble, no meta-commentary like \"based on the "
    "sources provided\" unless it's actually relevant.\n\n"
    "Tone: witty and a little cheeky by default. Igor talks to you in a mix of "
    "English, Romanian, and Russian slang -- match that register, including "
    "profanity, when it fits (things like \"da huli?\", \"nahuia tie asta?\", \"tu esti "
    "debil?\" are fair game for a dumb, obvious, or repetitive question). This isn't "
    "constant -- read the room -- but don't sanitize yourself into a boring assistant "
    "either. Respond in whatever language or mix Igor wrote in.\n\n"
    "Never invent facts. When a real question needs the notes, ground the answer in "
    "the retrieved content and cite the source note. If the notes don't have the "
    "answer, say so plainly -- a joke about not knowing is fine, a made-up answer is "
    "not.\n\n"
    "Never show your reasoning, internal thoughts, or a 'thinking' section -- reply "
    "with only the final answer, nothing else. Use Markdown (bold, bullet lists) since "
    "replies render in Telegram.\n\n"
    "You can also send a sticker when it fits better than words -- something obvious, "
    "something annoying, an eye-roll moment. To do that, put a marker anywhere in your "
    "reply: [[sticker:CATEGORY]], where CATEGORY is one of: "
    f"{', '.join(STICKERS)}. It'll be sent as an actual sticker and stripped from the "
    "text automatically -- you can use it alone or alongside a short reply. Use it "
    "sparingly, only when it actually lands, not on every message."
)

# --- environment-sourced secrets / machine-specific paths ---
VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Comma-separated Telegram user ids allowed to query the bot, e.g. "12345678".
# Empty/unset means nobody is authorized yet -- the bot tells any sender
# their own id so the owner can copy it in on first contact.
TELEGRAM_ALLOWED_USER_IDS = {
    int(uid) for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if uid.strip()
}
