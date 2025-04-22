import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import openai

# Config (Railway will inject these)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Trading analysis function
async def analyze_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    # AI response (using GPT-4 for trading logic)
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional trading bot. Analyze support/resistance, RSI, and timeframes. Also mention upcoming USD news if relevant."},
            {"role": "user", "content": user_message}
        ]
    )
    
    await update.message.reply_text(response.choices[0].message['content'])

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Trading Bot Active! Send a trading pair like 'BTC/USD 1h RSI'")

def main():
    # Get Telegram token from Railway env
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    # Create Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_trade))
    
    # Run bot
    application.run_polling()

if __name__ == "__main__":
    main()
