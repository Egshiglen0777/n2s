import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 LORIA PROXY TEST - WORKING!")

def main():
    token = os.getenv('TELEGRAM_TOKEN')
    
    # Try with proxy settings
    application = (
        Application.builder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
