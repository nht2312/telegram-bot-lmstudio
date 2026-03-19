import os
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Load Environment Variables
# ------------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set. Please set it in the .env file.")

DB_FILE = "conversations.db"

# ------------------------------------------------------------------------------
# LM Studio Configuration
# ------------------------------------------------------------------------------
LM_STUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODELS_URL = os.getenv("LM_STUDIO_MODELS_URL", f"{LM_STUDIO_BASE_URL}/models")
LM_STUDIO_CHAT_COMPLETIONS_URL = os.getenv("LM_STUDIO_CHAT_COMPLETIONS_URL", f"{LM_STUDIO_BASE_URL}/chat/completions")
LM_STUDIO_COMPLETIONS_URL = os.getenv("LM_STUDIO_COMPLETIONS_URL", f"{LM_STUDIO_BASE_URL}/completions")
LM_STUDIO_EMBEDDINGS_URL = os.getenv("LM_STUDIO_EMBEDDINGS_URL", f"{LM_STUDIO_BASE_URL}/embeddings")

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
