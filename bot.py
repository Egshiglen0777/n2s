import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI  # Updated import

# Configure API keys
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # New client initialization
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def analyze_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text
        response = client.chat.completions.create(  # Updated API call
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a trading expert. Analyze RSI, support/resistance, and fundamentals. Include key levels and news when relevant."},
                {"role": "user", "content": user_message}
            ]
        )
        await update.message.reply_text(response.choices[0].message.content)  # Updated response access
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error analyzing trade: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📈 Trading Bot Ready! Ask me about any asset (e.g. 'GBPJPY 1H RSI')")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_trade))
    app.run_polling()

if __name__ == "__main__":
    main()
