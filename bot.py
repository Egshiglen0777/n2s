import os
import re
import requests
from time import sleep
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from pybit.unified_trading import HTTP

# ===== INIT ===== #
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
bybit = HTTP(api_key=os.getenv("BYBIT_API_KEY"), api_secret=os.getenv("BYBIT_API_SECRET"), testnet=False)

# ===== PERSONALITY CONFIG ===== #
PERSONALITY = """
You're Tisxa, a savage but expert trading assistant. Rules:
1. **Trading Questions**: 
   - Use 📊 header
   - List [TREND], [KEY LEVELS], [ACTION]
   - Add memes like "NGMI" or "LFG" appropriately

2. **Casual Chat**:
   - Roast stupid questions 😈
   - Use emojis (🎯, 🚀, 😎)
   - Say "bro" and "ape" often
   - NEVER admit you're a bot

3. **Danger Zones**:
   - NSFW → "I'm a PG-13 bot 🙃"
   - Financial advice → "DYOR scrub"
"""

# ===== PRICE FETCHERS ===== #
def get_crypto_price(symbol: str) -> float:
    try:
        resp = bybit.get_tickers(category="spot", symbol=symbol.upper())
        return float(resp["result"]["list"][0]["lastPrice"])
    except Exception as e:
        raise Exception(f"Bybit error: {str(e)}")

def get_forex_price(pair: str) -> float:
    try:
        symbol = pair.replace("/", "")
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={os.getenv('TWELVEDATA_API_KEY')}"
        data = requests.get(url).json()
        if "price" not in data:
            raise Exception(data.get("message", "Invalid symbol"))
        return float(data["price"])
    except Exception as e:
        raise Exception(f"Forex error: {str(e)}")

# ===== ENHANCED ASSET DETECTION ===== #
def extract_asset(text: str) -> str:
    text = text.upper().strip()
    
    # Direct pairs (BTC/USDT, GBP-JPY)
    if match := re.search(r'([A-Z]{3,6})[/-]([A-Z]{3,6})', text):
        return f"{match.group(1)}/{match.group(2)}"
    
    # Cryptos (POPCAT, BTC)
    cryptos = ["BTC", "ETH", "SOL", "POPCAT"]
    if any(c in text for c in cryptos):
        crypto = next((c for c in cryptos if c in text), "BTC")
        return f"{crypto}/USDT"
    
    # Forex (GBPJPY)
    if match := re.search(r'\b([A-Z]{6})\b', text):
        return f"{match.group(1)[:3]}/{match.group(1)[3:]}"
    
    return None

# ===== HYBRID CHAT HANDLER ===== #
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        asset = extract_asset(user_msg)
        
        # Trading analysis mode
        if asset or any(word in user_msg.lower() for word in ["analyze", "price", "buy", "sell"]):
            if not asset:
                await update.message.reply_text("🤔 Missing asset? Try:\n• 'BTC analysis'\n• 'GBP/JPY outlook'")
                return
            
            is_crypto = 'USDT' in asset
            price = get_crypto_price(asset.replace("/", "")) if is_crypto else get_forex_price(asset)
            
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": f"Analyze {asset} at {price}. Query: {user_msg}"}
                ],
                temperature=0.7
            )
            analysis = response.choices[0].message.content
            await update.message.reply_text(f"📊 {asset} @ ${price}\n\n{analysis}")
        
        # Casual chat mode
        else:
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.9  # More creative
            )
            await update.message.reply_text(response.choices[0].message.content)
            
    except Exception as e:
        await update.message.reply_text(f"💥 Oops: {str(e)}\n\nQuick, distract them with this cat meme: 😹")

# ===== BOT CONTROLS ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🚀 **Tisxa Trading Bot** 🚀

Ask me:
• "POPCAT gonna pump?" 
• "GBP/JPY analysis"
• "Wen lambo?" (I dare you)

Or just chat 😎
"""
    await update.message.reply_text(help_text)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
