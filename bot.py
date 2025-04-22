import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Enhanced system prompt with trading expertise
TRADING_EXPERT_SYSTEM = """
You are a professional trading bot specializing in technical and fundamental analysis. 
When analyzing any asset (forex/crypto/stocks):

1. Always include:
   - Key support/resistance levels
   - Trend analysis (HTF + current TF)
   - Volume analysis (when available)
   - RSI and MACD conditions
   - Relevant news/events (NFP, FOMC, etc.)

2. Structure responses clearly:
   [TREND] Bullish/Bearish/Neutral
   [KEY LEVELS] S1/S2/R1/R2
   [INDICATORS] RSI: 54 (neutral), MACD: bullish crossover
   [ACTION] Buy/Sell/Wait + logical TP/SL
   [NEWS] Upcoming USD CPI data on Friday

3. For crypto include:
   - Liquidation levels
   - BTC dominance impact
   - Key on-chain metrics
"""

async def analyze_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text
        
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": TRADING_EXPERT_SYSTEM},
                {"role": "user", "content": f"Analyze this trading query: {user_message}"}
            ],
            temperature=0.3  # More deterministic outputs
        )
        
        analysis = response.choices[0].message.content
        await update.message.reply_text(f"📊 Analysis:\n\n{analysis}")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

# ... (rest of the code remains same as previous version)
