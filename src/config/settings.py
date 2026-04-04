import os
from dotenv import load_dotenv

from src.config.logging_config import logger

# ------------------------------------------------------------------------------
# Load Environment Variables
# ------------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set. Please set it in the .env file.")

DB_FILE = "conversations.db"

# ------------------------------------------------------------------------------
# OpenAI-compatible LLM backend (LM Studio or Ollama)
# LM_STUDIO_* URL names are historical; they target whichever backend is active.
# ------------------------------------------------------------------------------
LM_STUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")

_raw_provider = os.getenv("LLM_PROVIDER", "lmstudio").strip().lower()
LLM_PROVIDER = _raw_provider if _raw_provider in ("lmstudio", "ollama") else "lmstudio"

_effective_base = OLLAMA_BASE_URL if LLM_PROVIDER == "ollama" else LM_STUDIO_BASE_URL

# Ollama: never read LM_STUDIO_*_URL here — those lines in .env often still point at LM Studio and
# would override OLLAMA_BASE_URL. Use OLLAMA_*_URL only if you need per-endpoint overrides.
if LLM_PROVIDER == "ollama":
    LM_STUDIO_MODELS_URL = os.getenv("OLLAMA_MODELS_URL", f"{_effective_base}/models")
    LM_STUDIO_CHAT_COMPLETIONS_URL = os.getenv(
        "OLLAMA_CHAT_COMPLETIONS_URL", f"{_effective_base}/chat/completions"
    )
    LM_STUDIO_COMPLETIONS_URL = os.getenv(
        "OLLAMA_COMPLETIONS_URL", f"{_effective_base}/completions"
    )
    LM_STUDIO_EMBEDDINGS_URL = os.getenv(
        "OLLAMA_EMBEDDINGS_URL", f"{_effective_base}/embeddings"
    )
else:
    LM_STUDIO_MODELS_URL = os.getenv("LM_STUDIO_MODELS_URL", f"{_effective_base}/models")
    LM_STUDIO_CHAT_COMPLETIONS_URL = os.getenv(
        "LM_STUDIO_CHAT_COMPLETIONS_URL", f"{_effective_base}/chat/completions"
    )
    LM_STUDIO_COMPLETIONS_URL = os.getenv(
        "LM_STUDIO_COMPLETIONS_URL", f"{_effective_base}/completions"
    )
    LM_STUDIO_EMBEDDINGS_URL = os.getenv(
        "LM_STUDIO_EMBEDDINGS_URL", f"{_effective_base}/embeddings"
    )

logger.info("LLM provider=%s effective_base=%s", LLM_PROVIDER, _effective_base)

# Ollama ignores or mishandles very large max_tokens (LM Studio-oriented defaults); cap per request.
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "16384"))

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen3.5-2b")
TOKEN_THRESHOLD = int(os.getenv("TOKEN_THRESHOLD", "7975"))

# Main conversation parameters (extend as needed)
conversation_params = {
    "max_tokens": 260000,
    "temperature": 0.7,
    "top_p": 1.0,
    "top_k": 40,
    "stop": None,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repeat_penalty": None,
    "logit_bias": {},
    "seed": None,
}

LOADING_MESSAGE_ENABLED = os.getenv("LOADING_MESSAGE_ENABLED", "true").lower() == "true"
LOADING_SUMMARIZE_ENABLED = os.getenv("LOADING_SUMMARIZE_ENABLED", "true").lower() == "true"
LOADING_UPDATE_INTERVAL = int(os.getenv("LOADING_UPDATE_INTERVAL", "5"))
LOADING_TIMEOUT = int(os.getenv("LOADING_TIMEOUT", "300"))

STREAMING_ENABLED = os.getenv("STREAMING_ENABLED", "true").lower() == "true"
STREAM_UPDATE_INTERVAL = float(os.getenv("STREAM_UPDATE_INTERVAL", "3.0"))
STREAM_MIN_CHARS = int(os.getenv("STREAM_MIN_CHARS", "20"))
STREAM_CANCEL_TIMEOUT = int(os.getenv("STREAM_CANCEL_TIMEOUT", "300"))
# Max seconds between SSE chunks when streaming (remote Ollama / slow TTFT)
STREAM_READ_TIMEOUT = int(os.getenv("STREAM_READ_TIMEOUT", "300"))
