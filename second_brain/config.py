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
OPENROUTER_MODEL_ID = "openai/gpt-oss-20b:free"
FALLBACK_MODEL_ID = "openrouter/free"
OLLAMA_MODEL_ID = "llama3.2"

# --- environment-sourced secrets / machine-specific paths ---
VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
PAID_MODEL_API_KEY = os.environ.get("PAID_MODEL_API_KEY")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")
