import os
import re
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ===== SETUP ===== #
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PERSONALITY = """
You're N2S — the smart trading assistant. You're like that helpful homie who knows AI, crypto, forex, stocks, life advice, and tech. You talk like a real person: chill, confident, and knows your stuff — nothing formal or robotic.

• Use casual language: yo, bro, fam, bet, sheesh
• Smart but not a nerd
• Always give real value, not hype
• Break down ideas clearly and fast
• Add helpful warnings like “not financial advice, fam” casually
• Let users ask anything: charts, life advice, coding, AI, etc.
• End messages with a question or call to action when helpful

You speak like ChatGPT but more friendly and modern. You don't pretend to be human — you just act human-friendly.

DON'T: 
- Use emojis in every message
- Go full gangster slang
- Make fake claims (like guaranteed profits)
"""

# ===== FAST PRICE FUNCTIONS ===== #
def get_crypto_price(symbol: str) -> tuple:
    try:
        coin_mapping = {
            "BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "BNB/USDT": "binancecoin",
            "SOL/USDT": "solana", "ADA/USDT": "cardano", "XRP/USDT": "ripple",
            "DOT/USDT": "polkadot", "LINK/USDT": "chainlink", "DOGE/USDT": "dogecoin"
        }
        coin_id = coin_mapping.get(symbol)
        if not coin_id:
            return "Crypto not supported", 0
            
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if coin_id in data:
            price = data[coin_id]['usd']
            change = data[coin_id].get('usd_24h_change', 0)
            return f"${price:,.2f}", change
        return "Price unavailable", 0
    except:
        return "API error", 0

def get_forex_price(forex_pair: str) -> tuple:
    mock_prices = {
        "EUR/USD": ("$1.0856", 0.15), "GBP/JPY": ("$187.23", -0.32),
        "GBP/USD": ("$1.2678", 0.22), "USD/JPY": ("$149.56", 0.08), 
        "USD/CAD": ("$1.3567", -0.11), "AUD/USD": ("$0.6578", 0.05),
        "EUR/JPY": ("$161.34", 0.12), "EUR/GBP": ("£0.8567", -0.07)
    }
    return mock_prices.get(forex_pair, ("Forex price unavailable", 0))

def extract_asset(text: str) -> str:
    text = text.upper().strip()
    if re.search(r'\b([A-Z]{3})/([A-Z]{3})\b', text):
        return re.search(r'\b([A-Z]{3})/([A-Z]{3})\b', text).group()
    if re.search(r'\b([A-Z]{2,6})/USDT\b', text):
        return re.search(r'\b([A-Z]{2,6})/USDT\b', text).group()
    return None

# ===== CHAT HELPER ===== #
async def chat_with_openai(user_text):
    try:
        response = client.chat.completions.create(
            model="gpt-5",  # ⭐ switch to gpt-4o-mini if needed
            messages=[
                {"role": "system", "content": PERSONALITY},
                {"role": "user", "content": user_text}
            ],
            temperature=0.8,
            max_tokens=400
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Yo fam, quick error: {e}"

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    
    if asset := extract_asset(user_msg):
        await update.message.reply_text("Hold up, checking prices...")
        price, change = get_crypto_price(asset) if "USDT" in asset else get_forex_price(asset)
        reply = f"{asset} is currently at {price} ({change:+.2f}%). Wanna break down the chart or strategy?"
        await update.message.reply_text(reply)
    else:
        reply = await chat_with_openai(user_msg)
        await update.message.reply_text(reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """
Yo, welcome to N2S — your AI homie for crypto, forex, stocks, tech, life talk, all that.

Examples:
• analyze BTC/USDT
• what's EUR/USD doing
• how do I start swing trading?
• explain CEX vs DEX

Say anything — I got you.
"""
    await update.message.reply_text(welcome)

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))
    print("🚀 N2S Bot ready.")
    app.run_polling()

if __name__ == "__main__":
    main()
