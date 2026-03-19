import sqlite3
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

def markdown_to_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML"""
    html = text

    # Escape HTML special characters first
    html = html.replace('&', '&amp;')
    html = html.replace('<', '&lt;')
    html = html.replace('>', '&gt;')

    # Code blocks (```code```)
    html = re.sub(r'```([\s\S]*?)```', r'<pre><code>\1</code></pre>', html)

    # Inline code (`code`)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    # Bold (**text** or __text__)
    html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'__([^_]+)__', r'<b>\1</b>', html)

    # Italic (*text* or _text_)
    html = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', html)
    html = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<i>\1</i>', html)

    # Strikethrough (~~text~~)
    html = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', html)

    # Headers ### -> bold with newline
    html = re.sub(r'^###\s+(.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^##\s+(.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^#\s+(.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)

    # Links [text](url)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    # Lists (- item)
    html = re.sub(r'^-\s+(.+)$', r'• \1', html, flags=re.MULTILINE)

    # Remove excessive newlines
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html
from src.database.models import (
    get_user_settings, set_user_setting, create_conversation,
    get_user_conversations, switch_conversation, update_conversation_model,
    update_conversation_system_prompt, get_messages, clear_conversation_messages,
    append_summary, get_summaries
)
from src.api.lm_studio import (
    list_models, call_lm_studio_completions, call_lm_studio_embeddings,
    summarize_conversation
)
from src.config.settings import DEFAULT_MODEL, conversation_params, DB_FILE

async def summarize_thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    # If user typed /summarize_thread <id>, use that ID; else active conversation
    cid = None
    if args:
        try:
            cid = int(args[0])
        except ValueError:
            await update.message.reply_text(
                "*Invalid conversation ID.*", parse_mode=ParseMode.MARKDOWN
            )
            return

    if not cid:
        s = get_user_settings(user_id)
        cid = s["active_conversation_id"]

    if not cid:
        await update.message.reply_text(
            "*No active conversation or invalid ID.*", parse_mode=ParseMode.MARKDOWN
        )
        return

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT model FROM user_conversations WHERE conversation_id = ?", (cid,))
        row = c.fetchone()

    if not row:
        await update.message.reply_text(
            "*Conversation not found.*", parse_mode=ParseMode.MARKDOWN
        )
        return

    model = row[0] if row[0] else DEFAULT_MODEL

    summary_text = summarize_conversation(cid, model)
    if summary_text.startswith("Summary error") or summary_text.startswith("Failed"):
        await update.message.reply_text(
            f"*Error summarizing conversation {cid}.*", parse_mode=ParseMode.MARKDOWN
        )
        return

    # Store summary
    append_summary(cid, summary_text)

    await update.message.reply_text(
        f"*Summary for conversation {cid}:*\n\n{summary_text}",
        parse_mode=ParseMode.MARKDOWN
    )

async def set_parameter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/set <param> <value>`", parse_mode=ParseMode.MARKDOWN
        )
        return

    param = args[0].lower()
    val = " ".join(args[1:])
    if param in conversation_params:
        try:
            if param in ["max_tokens", "top_k"]:
                conversation_params[param] = int(val)
            elif param in ["temperature", "top_p", "presence_penalty", "frequency_penalty"]:
                conversation_params[param] = float(val)
            elif param == "stop":
                conversation_params["stop"] = None if val.lower() == "none" else val
            elif param == "repeat_penalty":
                conversation_params["repeat_penalty"] = None if val.lower() == "none" else float(val)
            elif param == "seed":
                conversation_params["seed"] = None if val.lower() == "none" else int(val)
            else:
                conversation_params[param] = val
            await update.message.reply_text(
                f"*Set* `{param}` *to* `{conversation_params[param]}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            await update.message.reply_text(
                f"Invalid value for `{param}`: `{val}`", parse_mode=ParseMode.MARKDOWN
            )
    else:
        await update.message.reply_text(
            f"Unknown parameter: `{param}`", parse_mode=ParseMode.MARKDOWN
        )

async def show_parameters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [f"`{k}` = `{v}`" for k, v in conversation_params.items()]
    formatted = "\n".join(lines)
    msg = "*Current parameters:*\n" + formatted
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def clear_context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = get_user_settings(user_id)
    cid = s["active_conversation_id"]
    if not cid:
        await update.message.reply_text(
            "*No active context to clear.*", parse_mode=ParseMode.MARKDOWN
        )
        return
    clear_conversation_messages(cid)
    await update.message.reply_text(
        "*Context cleared.*", parse_mode=ParseMode.MARKDOWN
    )

async def show_summaries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cid = get_user_settings(user_id)["active_conversation_id"]
    if not cid:
        await update.message.reply_text(
            "*No active conversation.*", parse_mode=ParseMode.MARKDOWN
        )
        return
    sums = get_summaries(cid)
    if sums:
        bullet_sums = "\n\n".join(f" {s}" for s in sums)
        await update.message.reply_text(
            f"*Summaries for Conversation {cid}:*\n\n{bullet_sums}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("*No summaries found.*", parse_mode=ParseMode.MARKDOWN)

async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = " ".join(context.args) or "Unnamed"
    conv_id = create_conversation(user_id, name)
    switch_conversation(user_id, conv_id)
    await update.message.reply_text(
        f"New conversation *'{name}'* created.\nSwitched to conversation *ID={conv_id}*",
        parse_mode=ParseMode.MARKDOWN
    )

async def list_threads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    convs = get_user_conversations(user_id)
    s = get_user_settings(user_id)

    if not convs:
        await update.message.reply_text("*No conversations.*", parse_mode=ParseMode.MARKDOWN)
        return

    lines = []
    for c in convs:
        cid = c["conversation_id"]
        cname_escaped = c["conversation_name"].replace("_", "\\_")
        active_prefix = "**(active)** " if cid == s["active_conversation_id"] else ""
        lines.append(
            f"{active_prefix}**ID {cid}**: [{cname_escaped}](/{'switch_thread'} {cid}) -> Model: `{c['model']}`"
        )

    out_text = "*Your conversations:*\n\n" + "\n".join(lines)
    await update.message.reply_text(out_text, parse_mode=ParseMode.MARKDOWN)

async def switch_thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/switch_thread <id>`", parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        cid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("*Invalid conversation ID.*", parse_mode=ParseMode.MARKDOWN)
        return

    if switch_conversation(user_id, cid):
        await update.message.reply_text(
            f"Switched to conversation *ID={cid}*", parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "*Not found or not owned by you.*", parse_mode=ParseMode.MARKDOWN
        )

async def set_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cid = get_user_settings(user_id)["active_conversation_id"]
    if not cid:
        await update.message.reply_text(
            "*No active conversation.*", parse_mode=ParseMode.MARKDOWN
        )
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/set_model <model_name>`", parse_mode=ParseMode.MARKDOWN
        )
        return
    model = " ".join(context.args)
    update_conversation_model(cid, model)
    await update.message.reply_text(
        f"Conversation *{cid}* model set to `{model}`", parse_mode=ParseMode.MARKDOWN
    )

async def set_system_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cid = get_user_settings(user_id)["active_conversation_id"]
    if not cid:
        await update.message.reply_text("*No active conversation.*", parse_mode=ParseMode.MARKDOWN)
        return
    prompt = " ".join(context.args)
    update_conversation_system_prompt(cid, prompt)
    await update.message.reply_text("*System prompt updated.*", parse_mode=ParseMode.MARKDOWN)

async def show_system_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = get_user_settings(user_id)
    cid = s["active_conversation_id"]
    if not cid:
        await update.message.reply_text(
            "*No active conversation.*", parse_mode=ParseMode.MARKDOWN
        )
        return

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT system_prompt FROM user_conversations WHERE conversation_id = ?", (cid,))
        row = c.fetchone()

    if row and row[0]:
        system_prompt = row[0]
        await update.message.reply_text(
            f"*System Prompt for conversation {cid}:*\n\n```{system_prompt}```",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("*No system prompt set.*", parse_mode=ParseMode.MARKDOWN)

async def list_models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = list_models()
    if "error" in r:
        await update.message.reply_text(f"*Error:* {r['error']}", parse_mode=ParseMode.MARKDOWN)
        return
    if "data" in r:
        models = [m["id"] for m in r["data"]]
        lines = "\n".join(f"- `{m}`" for m in models)
        await update.message.reply_text(f"*Models loaded:*\n\n{lines}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("*Unexpected /v1/models response.*", parse_mode=ParseMode.MARKDOWN)

async def completion_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prompt = " ".join(context.args)
    if not prompt.strip():
        await update.message.reply_text(
            "Usage: `/completion <prompt>`", parse_mode=ParseMode.MARKDOWN
        )
        return
    s = get_user_settings(user_id)
    cid = s["active_conversation_id"]
    model = s["default_model"]
    if cid:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT model FROM user_conversations WHERE conversation_id = ?", (cid,))
            row = c.fetchone()
            if row and row[0]:
                model = row[0]

    await update.message.reply_text(
        f"Requesting completion with model: `{model}`...",
        parse_mode=ParseMode.MARKDOWN
    )
    data = call_lm_studio_completions(prompt, model)
    if "error" in data:
        await update.message.reply_text(f"*Error:* {data['error']}", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        txt = data["choices"][0]["text"]
        if not txt.strip():
            txt = "*No content returned.*"
        html_content = markdown_to_html(txt)
        await update.message.reply_text(html_content, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("*No text in response.*", parse_mode=ParseMode.MARKDOWN)

async def embedding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txt = " ".join(context.args)
    if not txt.strip():
        await update.message.reply_text(
            "Usage: `/embedding <text>`", parse_mode=ParseMode.MARKDOWN
        )
        return
    s = get_user_settings(user_id)
    cid = s["active_conversation_id"]
    model = s["default_model"]
    if cid:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT model FROM user_conversations WHERE conversation_id = ?", (cid,))
            row = c.fetchone()
            if row and row[0]:
                model = row[0]

    await update.message.reply_text(
        f"Requesting embedding with model: `{model}`...",
        parse_mode=ParseMode.MARKDOWN
    )
    data = call_lm_studio_embeddings(txt, model)
    if "error" in data:
        await update.message.reply_text(f"*Error:* {data['error']}", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        emb = data["data"][0]["embedding"]
        truncated = emb[:10]
        emb_preview = ", ".join(str(x) for x in truncated)
        await update.message.reply_text(
            f"*Embedding (first 10 values):* `{emb_preview}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        await update.message.reply_text("*No embedding data returned.*", parse_mode=ParseMode.MARKDOWN)
