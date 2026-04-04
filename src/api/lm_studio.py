import asyncio
import json
import queue
import threading
import requests
from src.config.settings import (
    LM_STUDIO_MODELS_URL,
    LM_STUDIO_CHAT_COMPLETIONS_URL,
    LM_STUDIO_COMPLETIONS_URL,
    LM_STUDIO_EMBEDDINGS_URL,
    LLM_PROVIDER,
    OLLAMA_MAX_TOKENS,
    STREAM_READ_TIMEOUT,
    conversation_params,
)
from src.config.logging_config import logger
from src.database.models import get_messages, append_summary, clear_conversation_messages

# ------------------------------------------------------------------------------
# HTTP errors (Ollama returns 404 for unknown model, not only for missing routes)
# ------------------------------------------------------------------------------
def _http_response_error_message(resp: requests.Response) -> str:
    code = resp.status_code
    try:
        j = resp.json()
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("detail")
                if msg:
                    return f"HTTP {code}: {msg}"
            if isinstance(err, str) and err.strip():
                return f"HTTP {code}: {err.strip()}"
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    text = (resp.text or "").strip()
    if text:
        return f"HTTP {code}: {text[:800]}"
    return f"HTTP {code} {resp.reason or ''}".strip()


def _ollama_error_hint(status_code: int) -> str:
    if status_code != 404:
        return ""
    return (
        " | Ollama: 404 thường là model chưa có hoặc sai tên — trên máy chạy Ollama chạy `ollama list`, "
        "hoặc dùng /list_models trên bot; kéo model bằng `ollama pull <tên>`."
    )


# ------------------------------------------------------------------------------
# OpenAI-style SSE streaming (LM Studio + Ollama)
# ------------------------------------------------------------------------------
def _extract_stream_text_piece(data: dict) -> str:
    """Collect assistant text from one chat.completion.chunk (varies slightly by server)."""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return ""
    parts: list[str] = []
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        delta = ch.get("delta")
        if isinstance(delta, dict):
            c = delta.get("content")
            if c:
                parts.append(str(c))
            rc = delta.get("reasoning_content")
            if rc:
                parts.append(str(rc))
        msg = ch.get("message")
        if isinstance(msg, dict):
            c = msg.get("content")
            if c:
                parts.append(str(c))
    return "".join(parts)


def _sse_line_to_chunks(line: str):
    """Parse a single line; may emit 0 or 1 JSON dict. [DONE] ends stream (caller checks)."""
    s = (line or "").strip()
    if not s:
        return None
    if s.lower().startswith("data:"):
        raw = s[5:].lstrip()
        if raw == "[DONE]":
            return "done"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("SSE JSON error: %s", raw[:160])
            return None
    return None


def _blocking_read_sse_lines(resp: requests.Response, out: queue.Queue) -> None:
    """Run in a thread so asyncio event loop is not blocked (critical for python-telegram-bot + remote Ollama)."""
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if line is None:
                continue
            out.put(("line", line))
    except Exception as e:
        out.put(("err", str(e)))
    finally:
        out.put(("end", None))
        try:
            resp.close()
        except Exception:
            pass


# ------------------------------------------------------------------------------
# Payload builders (Ollama OpenAI-compat rejects some LM Studio–specific fields)
# ------------------------------------------------------------------------------
def _ollama_max_tokens() -> int:
    return min(conversation_params["max_tokens"], OLLAMA_MAX_TOKENS)


def _build_chat_payload(messages: list, model: str, stream: bool = False) -> dict:
    p = conversation_params
    if LLM_PROVIDER == "ollama":
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": _ollama_max_tokens(),
            "temperature": p["temperature"],
            "top_p": p["top_p"],
        }
        if stream:
            payload["stream"] = True
        if p["stop"] is not None:
            payload["stop"] = p["stop"]
        return payload

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": p["max_tokens"],
        "temperature": p["temperature"],
        "top_p": p["top_p"],
        "top_k": p["top_k"],
        "presence_penalty": p["presence_penalty"],
        "frequency_penalty": p["frequency_penalty"],
        "logit_bias": p["logit_bias"],
    }
    if stream:
        payload["stream"] = True
    if p["stop"] is not None:
        payload["stop"] = p["stop"]
    if p["repeat_penalty"] is not None:
        payload["repeat_penalty"] = p["repeat_penalty"]
    if p["seed"] is not None:
        payload["seed"] = p["seed"]
    return payload


def _build_completions_payload(prompt: str, model: str) -> dict:
    p = conversation_params
    if LLM_PROVIDER == "ollama":
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": _ollama_max_tokens(),
            "temperature": p["temperature"],
            "top_p": p["top_p"],
        }
        if p["stop"] is not None:
            payload["stop"] = p["stop"]
        return payload

    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": p["max_tokens"],
        "temperature": p["temperature"],
        "top_p": p["top_p"],
        "top_k": p["top_k"],
        "presence_penalty": p["presence_penalty"],
        "frequency_penalty": p["frequency_penalty"],
        "logit_bias": p["logit_bias"],
    }
    if p["stop"] is not None:
        payload["stop"] = p["stop"]
    if p["repeat_penalty"] is not None:
        payload["repeat_penalty"] = p["repeat_penalty"]
    if p["seed"] is not None:
        payload["seed"] = p["seed"]
    return payload


# ------------------------------------------------------------------------------
# LM Studio API Calls
# ------------------------------------------------------------------------------
def list_models() -> dict:
    try:
        r = requests.get(LM_STUDIO_MODELS_URL)
        if not r.ok:
            msg = _http_response_error_message(r) + _ollama_error_hint(r.status_code)
            logger.error("Error listing models: %s", msg)
            return {"error": msg}
        return r.json()
    except requests.RequestException as e:
        logger.error(f"Error listing models: {e}")
        return {"error": str(e)}

def call_lm_studio_chat(messages: list, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = _build_chat_payload(messages, model, stream=False)
        resp = requests.post(LM_STUDIO_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        if not resp.ok:
            msg = _http_response_error_message(resp)
            if LLM_PROVIDER == "ollama":
                msg += _ollama_error_hint(resp.status_code)
            logger.error("Error calling chat completions: %s", msg)
            return {"error": msg}
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error calling chat completions: {e}")
        return {"error": str(e)}

def call_lm_studio_completions(prompt: str, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = _build_completions_payload(prompt, model)
        resp = requests.post(LM_STUDIO_COMPLETIONS_URL, headers=headers, json=payload)
        if not resp.ok:
            msg = _http_response_error_message(resp)
            if LLM_PROVIDER == "ollama":
                msg += _ollama_error_hint(resp.status_code)
            logger.error("Error calling completions: %s", msg)
            return {"error": msg}
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Error calling completions: {e}")
        return {"error": str(e)}

def call_lm_studio_embeddings(text: str, model: str) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"model": model, "input": [text]}
        resp = requests.post(LM_STUDIO_EMBEDDINGS_URL, headers=headers, json=payload)
        if not resp.ok:
            msg = _http_response_error_message(resp)
            if LLM_PROVIDER == "ollama":
                msg += _ollama_error_hint(resp.status_code)
            logger.error("Error calling embeddings: %s", msg)
            return {"error": msg}
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

async def stream_lm_studio_chat(messages: list, model: str):
    try:
        headers = {"Content-Type": "application/json"}
        payload = _build_chat_payload(messages, model, stream=True)
        resp = requests.post(
            LM_STUDIO_CHAT_COMPLETIONS_URL,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(30, STREAM_READ_TIMEOUT),
        )
        if not resp.ok:
            msg = _http_response_error_message(resp)
            if LLM_PROVIDER == "ollama":
                msg += _ollama_error_hint(resp.status_code)
            logger.error("Error in streaming chat completions: %s", msg)
            yield {"error": msg}
            return

        q: queue.Queue = queue.Queue(maxsize=256)
        t = threading.Thread(target=_blocking_read_sse_lines, args=(resp, q), daemon=True)
        t.start()

        while True:
            kind, payload = await asyncio.to_thread(q.get)
            if kind == "end":
                break
            if kind == "err":
                yield {"error": payload}
                return
            if kind != "line":
                continue
            parsed = _sse_line_to_chunks(payload)
            if parsed == "done":
                break
            if not isinstance(parsed, dict):
                continue
            piece = _extract_stream_text_piece(parsed)
            if piece:
                yield piece

        yield None

    except requests.RequestException as e:
        logger.error(f"Error in streaming chat completions: {e}")
        yield {"error": str(e)}
