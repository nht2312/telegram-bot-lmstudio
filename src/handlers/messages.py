import sqlite3
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

def escape_markdown(text: str) -> str:
    """Escape special Markdown characters in text"""
    escape_chars = '*_`[]()#>+-=!|'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)
from src.database.models import (
    upsert_user, get_user_settings, create_conversation, set_user_setting,
    append_message, get_messages, append_summary, clear_conversation_messages
)
from src.api.lm_studio import call_lm_studio_chat, summarize_conversation
from src.config.settings import DB_FILE, TOKEN_THRESHOLD

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    upsert_user(user)

    s = get_user_settings(user.id)
    cid = s["active_conversation_id"]
    if not cid:
        cid = create_conversation(user.id, "Default Thread")
        set_user_setting(user.id, "active_conversation_id", cid)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
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

    data = call_lm_studio_chat(msgs, model)
    if "error" in data:
        await update.message.reply_text(
            f"API Error: {data['error']}", parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        assistant_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
    except:
        await update.message.reply_text(
            "No content in response.", parse_mode=ParseMode.MARKDOWN
        )
        return

    append_message(cid, "assistant", assistant_text)

    usage_msg = ""
    if usage:
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens > TOKEN_THRESHOLD:
            # Summarize automatically
            summary = summarize_conversation(cid, model)
            append_summary(cid, summary)
            clear_conversation_messages(cid)
            usage_msg = "\n\n🔄 Context summarized and reset."

    await update.message.reply_text(
        assistant_text + usage_msg, parse_mode=None
    )
