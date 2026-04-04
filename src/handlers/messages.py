import sqlite3
import re
import asyncio
import time
import telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from src.database.models import (
    upsert_user, get_user_settings, create_conversation, set_user_setting,
    append_message, get_messages, append_summary, clear_conversation_messages,
    log_usage, init_usage_log_table, resolve_conversation_model,
)
from src.api.lm_studio import call_lm_studio_chat, stream_lm_studio_chat, summarize_conversation
from src.config.logging_config import logger
from src.config.settings import (
    DB_FILE, TOKEN_THRESHOLD, LOADING_MESSAGE_ENABLED, LOADING_SUMMARIZE_ENABLED,
    LOADING_UPDATE_INTERVAL, LOADING_TIMEOUT, STREAMING_ENABLED, STREAM_UPDATE_INTERVAL, 
    STREAM_MIN_CHARS, STREAM_CANCEL_TIMEOUT
)

streaming_active = {}

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

def escape_html(text: str) -> str:
    """Escape HTML special characters only"""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

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

async def cancel_streaming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing streaming for this chat"""
    chat_id = update.effective_chat.id
    if chat_id in streaming_active:
        streaming_active[chat_id] = False
        try:
            await update.message.reply_text("✅ Streaming cancelled.")
        except:
            pass
    else:
        await update.message.reply_text("No active streaming to cancel.")

async def handle_streaming(update: Update, context: ContextTypes.DEFAULT_TYPE, msgs: list, model: str, cid: int, user_id: int):
    """Handle streaming response from LM Studio"""
    chat_id = update.effective_chat.id
    streaming_active[chat_id] = True
    
    response_msg = await update.message.reply_text("⚡ Generating...")
    
    full_text = ""
    prev_text_len = 0
    start_time = time.time()
    last_update = time.time()
    update_interval = STREAM_UPDATE_INTERVAL
    
    try:
        async for chunk in stream_lm_studio_chat(msgs, model):
            if chat_id not in streaming_active or not streaming_active[chat_id]:
                break
            
            if chunk is None:
                continue
            
            if isinstance(chunk, dict) and "error" in chunk:
                try:
                    await response_msg.edit_text(f"❌ API Error: {chunk['error']}")
                except:
                    pass
                return
            
            full_text += str(chunk)
            
            current_time = time.time()
            chars_since_update = len(full_text) - prev_text_len
            
            if current_time - last_update >= update_interval and chars_since_update >= STREAM_MIN_CHARS:
                try:
                    escaped = escape_html(full_text[:2000] + ("..." if len(full_text) > 2000 else ""))
                    keyboard = [[InlineKeyboardButton("⏹ Cancel", callback_data="cancel_stream")]]
                    await response_msg.edit_text(
                        escaped + "\n\n⏳ Generating...",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    last_update = current_time
                    prev_text_len = len(full_text)
                except telegram.error.BadRequest:
                    pass
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        if chat_id in streaming_active:
            del streaming_active[chat_id]
        
        if not full_text:
            try:
                await response_msg.edit_text("⚠️ No content generated.")
            except:
                pass
            return
        
        append_message(cid, "assistant", full_text)
        
        estimated_tokens = len(full_text) // 4
        log_usage(user_id, cid, model, 0, estimated_tokens, estimated_tokens, elapsed_ms)
        
        need_summarize = estimated_tokens > TOKEN_THRESHOLD // 2
        
        if need_summarize:
            try:
                await response_msg.edit_text("🔄 Summarizing context...")
            except:
                pass
            summary = summarize_conversation(cid, model)
            append_summary(cid, summary)
            clear_conversation_messages(cid)
        
        processed = markdown_to_html(full_text)
        try:
            if len(processed) > 4096:
                parts = [processed[i:i+4096] for i in range(0, len(processed), 4096)]
                await response_msg.edit_text(parts[0], parse_mode=ParseMode.HTML)
                for part in parts[1:]:
                    await update.message.reply_text(part, parse_mode=ParseMode.HTML)
            else:
                await response_msg.edit_text(processed, parse_mode=ParseMode.HTML)
        except telegram.error.BadRequest:
            await response_msg.edit_text(escape_html(full_text))
        
        if need_summarize:
            try:
                await update.message.reply_text("🔄 Context summarized and reset.")
            except:
                pass
            
    except asyncio.TimeoutError:
        if chat_id in streaming_active:
            del streaming_active[chat_id]
        try:
            await response_msg.edit_text("⏰ Request timed out after 5 minutes. Please try again.")
        except:
            pass
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        if chat_id in streaming_active:
            del streaming_active[chat_id]
        try:
            await response_msg.edit_text(f"❌ Error: {str(e)}")
        except:
            pass

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    upsert_user(user)
    
    init_usage_log_table()
    start_time = time.time()

    s = get_user_settings(user.id)
    cid = s["active_conversation_id"]
    if not cid:
        cid = create_conversation(user.id, "Default Thread")
        set_user_setting(user.id, "active_conversation_id", cid)

    append_message(cid, "user", text)

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT system_prompt FROM user_conversations WHERE conversation_id = ?", (cid,))
        row = c.fetchone()

    model = resolve_conversation_model(cid, user.id)
    system_prompt = row[0] if row and row[0] else ""

    msgs = []
    if system_prompt.strip():
        msgs.append({"role": "system", "content": system_prompt})
    for m in get_messages(cid):
        msgs.append({"role": m["role"], "content": m["content"]})

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    if STREAMING_ENABLED:
        await handle_streaming(update, context, msgs, model, cid, user.id)
    else:
        loading_msg = None
        if LOADING_MESSAGE_ENABLED:
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
            
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            if total_tokens > 0:
                elapsed_ms = int((time.time() - start_time) * 1000)
                log_usage(user.id, cid, model, prompt_tokens, completion_tokens, total_tokens, elapsed_ms)
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
