import os
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import openai

# Config (Railway will inject these)
openai.api_key = os.getenv("OPENAI_API_KEY")

def analyze_trade(update, context):
    user_message = update.message.text
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a trading bot. Analyze RSI, support/resistance, and timeframes. Include USD news if relevant."},
            {"role": "user", "content": user_message}
        ]
    )
    update.message.reply_text(response.choices[0].message['content'])

def start(update, context):
    update.message.reply_text("🚀 Trading Bot Active! Send a pair like 'BTC/USD 1h RSI'")

def main():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text, analyze_trade))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
