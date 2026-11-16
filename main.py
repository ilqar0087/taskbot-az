
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salam! TaskBot AZ aktivdir! 🤖\n\n"
        "Mən onlayn tapşırıqları tapmağa və "
        "qazancını izləməyə kömək edəcəyəm.\n\n"
        "/tasks - Tapşırıqlar\n"
        "/balance - Balans"
    )


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Tapşırıqlar axtarılır. Rəsmi platformalar "
        "qoşulduqdan sonra tapşırıqlar burada görünəcək."
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Balans: 0.00 USD\n"
        "Təsdiqlənmiş qazanc: 0.00 USD"
    )


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN tapılmadı")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("balance", balance))
    app.run_polling()


if __name__ == "__main__":
    main()

