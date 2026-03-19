import requests
from src.config.settings import (
    LM_STUDIO_MODELS_URL,
    LM_STUDIO_CHAT_COMPLETIONS_URL,
    LM_STUDIO_COMPLETIONS_URL,
    LM_STUDIO_EMBEDDINGS_URL,
    conversation_params,
    DEFAULT_MODEL
)
from src.config.logging_config import logger
from src.database.models import get_messages, append_summary, clear_conversation_messages

# ------------------------------------------------------------------------------
# LM Studio API Calls
# ------------------------------------------------------------------------------
def list_models() -> dict:
    try:
        r = requests.get(LM_STUDIO_MODELS_URL)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error(f"Error listing models: {e}")
        return {"error": str(e)}

def call_lm_studio_chat(messages: list, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": conversation_params["max_tokens"],
            "temperature": conversation_params["temperature"],
            "top_p": conversation_params["top_p"],
            "top_k": conversation_params["top_k"],
            "presence_penalty": conversation_params["presence_penalty"],
            "frequency_penalty": conversation_params["frequency_penalty"],
            "logit_bias": conversation_params["logit_bias"],
        }
        if conversation_params["stop"] is not None:
            payload["stop"] = conversation_params["stop"]
        if conversation_params["repeat_penalty"] is not None:
            payload["repeat_penalty"] = conversation_params["repeat_penalty"]
        if conversation_params["seed"] is not None:
            payload["seed"] = conversation_params["seed"]
        resp = requests.post(LM_STUDIO_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error calling chat completions: {e}")
        return {"error": str(e)}

def call_lm_studio_completions(prompt: str, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": conversation_params["max_tokens"],
            "temperature": conversation_params["temperature"],
            "top_p": conversation_params["top_p"],
            "top_k": conversation_params["top_k"],
            "presence_penalty": conversation_params["presence_penalty"],
            "frequency_penalty": conversation_params["frequency_penalty"],
            "logit_bias": conversation_params["logit_bias"],
        }
        if conversation_params["stop"] is not None:
            payload["stop"] = conversation_params["stop"]
        if conversation_params["repeat_penalty"] is not None:
            payload["repeat_penalty"] = conversation_params["repeat_penalty"]
        if conversation_params["seed"] is not None:
            payload["seed"] = conversation_params["seed"]
        resp = requests.post(LM_STUDIO_COMPLETIONS_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error calling completions: {e}")
        return {"error": str(e)}

def call_lm_studio_embeddings(text: str, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"model": model, "input": [text]}
        resp = requests.post(LM_STUDIO_EMBEDDINGS_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error calling embeddings: {e}")
        return {"error": str(e)}

def summarize_conversation(conversation_id: int, model: str) -> str:
    msgs = get_messages(conversation_id)
    if not msgs:
        return "Nothing to summarize."
    joined = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])
    prompt = f"Summarize:\n\n{joined}\n\nSummary:"
    data = call_lm_studio_completions(prompt, model)
    if "error" in data:
        return "Summary error."
    try:
        return data["choices"][0]["text"].strip()
    except:
        return "Failed to extract summary."
