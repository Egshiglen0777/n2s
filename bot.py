import os
import re
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from pybit.unified_trading import HTTP  # Bybit API client

# ===== API CLIENT INIT ===== #
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
bybit = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
    testnet=False  # Set True for testing
)

# ===== PRICE FETCHERS ===== #
def get_crypto_price(symbol: str) -> float:
    """Fetch spot price from Bybit (symbol format: BTCUSDT)"""
    try:
        resp = bybit.get_tickers(category="spot", symbol=symbol.upper())
        return float(resp["result"]["list"][0]["lastPrice"])
    except Exception as e:
        raise Exception(f"Bybit error: {str(e)}")

def get_forex_price(pair: str) -> float:
    """Fetch forex rate from TwelveData (pair format: GBPJPY)"""
    try:
        url = f"https://api.twelvedata.com/price?symbol={pair}&apikey={os.getenv('TWELVEDATA_API_KEY')}"
        data = requests.get(url).json()
        if "price" not in data:
            raise Exception(data.get("message", "Unknown error"))
        return float(data["price"])
    except Exception as e:
        raise Exception(f"TwelveData error: {str(e)}")

# ===== CORE BOT LOGIC ===== #
TRADING_SYSTEM_PROMPT = """
You are a professional trading analyst. Provide concise yet insightful market analysis with:

1. [TREND] Bullish/Bearish/Neutral (Multi-Timeframe)
2. [KEY LEVELS] Nearest support/resistance 
3. [ACTION] Clear trade suggestion (Buy/Sell/Wait) with logical TP/SL
4. [NEWS] Relevant upcoming events
5. [RISK] Volatility assessment

Format response in bullet points.
"""

async def analyze_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.message.text
        asset = extract_asset(query)
        
        if not asset:
            await update.message.reply_text("❌ Please specify an asset (e.g. 'BTC/USDT' or 'GBP/JPY')")
            return

        # Get live price
        is_crypto = 'USDT' in asset.upper()
        symbol = asset.replace('/', '')
        price = get_crypto_price(symbol) if is_crypto else get_forex_price(symbol)
        
        # Generate analysis
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": TRADING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze {asset} at current price {price}. Query: {query}"}
            ],
            temperature=0.3
        )
        
        analysis = response.choices[0].message.content
        await update.message.reply_text(f"📊 {asset} Analysis (${price})\n\n{analysis}")
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

def extract_asset(text: str) -> str:
    """Extract asset pair from natural language"""
    # Crypto pattern (BTC/USDT, ETH-USDT)
    crypto_match = re.search(r'([A-Z]{3,6})[/-]?USDT', text.upper())
    if crypto_match:
        return f"{crypto_match.group(1)}/USDT"
    
    # Forex pattern (GBP/JPY, EUR-USD)
    forex_match = re.search(r'([A-Z]{3})[/-]([A-Z]{3})', text.upper())
    if forex_match:
        return f"{forex_match.group(1)}/{forex_match.group(2)}"
    
    return None

# ===== BOT CONTROLS ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
💎 Trading Bot Activated!
Simply ask about any asset:
• "BTC/USDT analysis"
• "Should I buy GBP/JPY?"
• "POPCAT price prediction"
"""
    await update.message.reply_text(help_text)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_trade))
    app.run_polling()

if __name__ == "__main__":
    main()
