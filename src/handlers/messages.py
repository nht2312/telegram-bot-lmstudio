import sqlite3
import re
import asyncio
import time
import telegram.error
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from src.database.models import (
    upsert_user, get_user_settings, create_conversation, set_user_setting,
    append_message, get_messages, append_summary, clear_conversation_messages
)
from src.api.lm_studio import call_lm_studio_chat, summarize_conversation
from src.config.logging_config import logger
from src.config.settings import DB_FILE, TOKEN_THRESHOLD, LOADING_MESSAGE_ENABLED, LOADING_SUMMARIZE_ENABLED, LOADING_UPDATE_INTERVAL, LOADING_TIMEOUT

def markdown_to_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML"""
    html = text

    html = html.replace('&', '&amp;')
    html = html.replace('<', '&lt;')
    html = html.replace('>', '&gt;')

    html = re.sub(r'```([\s\S]*?)```', r'<pre>\1</pre>', html)

    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'__(.+?)__', r'<b>\1</b>', html)

    html = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', html)
    html = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', html)

    html = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', html)

    html = re.sub(r'^### (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)

    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    html = re.sub(r'^-\s+(.+)$', r'• \1', html, flags=re.MULTILINE)
    html = re.sub(r'^\d+\.\s+(.+)$', r'• \1', html, flags=re.MULTILINE)

    html = re.sub(r'\n{3,}', '\n\n', html)

    return html

async def show_loading_until(coro, chat_id, message_id, context, interval=5, timeout=300):
    """Run coroutine while showing/updating loading message. Returns (result, elapsed)."""
    start = time.time()

    async def update_loop():
        while True:
            await asyncio.sleep(interval)
            elapsed = int(time.time() - start)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=f"⏳ Wait: {elapsed}s"
                )
            except telegram.error.BadRequest:
                break

    task = asyncio.create_task(update_loop())
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        return {"error": "Request timed out after 5 minutes"}, int(time.time() - start)
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

    return result, int(time.time() - start)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    upsert_user(user)

    s = get_user_settings(user.id)
    cid = s["active_conversation_id"]
    if not cid:
        cid = create_conversation(user.id, "Default Thread")
        set_user_setting(user.id, "active_conversation_id", cid)

    append_message(cid, "user", text)

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT model, system_prompt FROM user_conversations WHERE conversation_id = ?", (cid,))
        row = c.fetchone()

    model = row[0] if row and row[0] else s["default_model"]
    system_prompt = row[1] if row and row[1] else ""

    msgs = []
    if system_prompt.strip():
        msgs.append({"role": "system", "content": system_prompt})
    for m in get_messages(cid):
        msgs.append({"role": m["role"], "content": m["content"]})

    loading_msg = None
    response_msg = None

    if LOADING_MESSAGE_ENABLED:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        loading_msg = await update.message.reply_text("⏳ Wait: 0s")
        data, _ = await show_loading_until(
            asyncio.to_thread(call_lm_studio_chat, msgs, model),
            update.effective_chat.id, loading_msg.message_id, context,
            interval=LOADING_UPDATE_INTERVAL, timeout=LOADING_TIMEOUT
        )
        try:
            await loading_msg.delete()
        except:
            pass
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        data = call_lm_studio_chat(msgs, model)

    if "error" in data:
        if "timed out" in data["error"].lower():
            await update.message.reply_text("⏰ Request timed out after 5 minutes. Please try again.")
        else:
            await update.message.reply_text(f"API Error: {data['error']}", parse_mode=ParseMode.HTML)
        return

    try:
        assistant_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
    except:
        await update.message.reply_text("No content in response.", parse_mode=ParseMode.HTML)
        return

    append_message(cid, "assistant", assistant_text)

    usage_msg = ""
    need_summarize = False
    if usage:
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens > TOKEN_THRESHOLD:
            need_summarize = True

    if need_summarize:
        if LOADING_SUMMARIZE_ENABLED:
            loading_msg = await update.message.reply_text("⏳ Summarizing...")
            summary = summarize_conversation(cid, model)
            try:
                await loading_msg.delete()
            except:
                pass
        else:
            summary = summarize_conversation(cid, model)
        append_summary(cid, summary)
        clear_conversation_messages(cid)
        usage_msg = "\n\n🔄 Context summarized and reset."

    processed_text = markdown_to_html(assistant_text)
    response_msg = await update.message.reply_text(processed_text, parse_mode=ParseMode.HTML)

    if usage_msg:
        full_text = markdown_to_html(assistant_text + usage_msg)
        try:
            await response_msg.edit_text(full_text, parse_mode=ParseMode.HTML)
        except:
            pass
