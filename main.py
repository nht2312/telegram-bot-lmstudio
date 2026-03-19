import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from src.config.settings import BOT_TOKEN
from src.database.models import init_db
from src.handlers.commands import (
    summarize_thread_command, set_parameter, show_parameters,
    clear_context_command, show_summaries_command, new_conversation_command,
    list_threads_command, switch_thread_command, set_model_command,
    set_system_prompt_command, show_system_prompt_command,
    list_models_command, completion_command, embedding_command, stats_command
)
from src.handlers.messages import chat, cancel_streaming
from src.config.logging_config import logger

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        try:
            await update.message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=None  # Use plain text to avoid markdown errors
            )
        except:
            pass  # If even this fails, just ignore

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("set", set_parameter))
    app.add_handler(CommandHandler("show_params", show_parameters))
    app.add_handler(CommandHandler("clear_context", clear_context_command))
    app.add_handler(CommandHandler("show_summaries", show_summaries_command))
    app.add_handler(CommandHandler("new_thread", new_conversation_command))
    app.add_handler(CommandHandler("list_threads", list_threads_command))
    app.add_handler(CommandHandler("switch_thread", switch_thread_command))
    app.add_handler(CommandHandler("set_model", set_model_command))
    app.add_handler(CommandHandler("set_system_prompt", set_system_prompt_command))
    app.add_handler(CommandHandler("show_system_prompt", show_system_prompt_command))
    app.add_handler(CommandHandler("list_models", list_models_command))
    app.add_handler(CommandHandler("completion", completion_command))
    app.add_handler(CommandHandler("embedding", embedding_command))
    app.add_handler(CommandHandler("summarize_thread", summarize_thread_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("cancel", cancel_streaming))

    # Chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    # Add error handler
    app.add_error_handler(error_handler)

    # 👇 chuẩn async lifecycle
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # giữ bot chạy
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
