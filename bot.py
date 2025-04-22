import os
import re
import io
import base64
import requests
from time import sleep
from datetime import datetime
import numpy as np
from PIL import Image
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from pybit.unified_trading import HTTP

# ===== INIT ===== #
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
bybit = HTTP(
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
    testnet=False
)

# ===== PERSONALITY CONFIG ===== #
PERSONALITY = """
You're Tisxa - a savage trading AI with these rules:

1. **Chart Analysis Mode** (when sent images):
- Identify: trends, S/R, patterns
- Use: 📊 header
- Format:
  [TREND] Bullish/Bearish
  [KEY LEVELS] Support/Resistance
  [PATTERN] Flag/Wedge/etc.
  [ACTION] Trade suggestion

2. **Text Analysis Mode** (trading questions):
- Same as above but for text queries

3. **Casual Mode**:
- Roast stupid questions 😈
- Use emojis (🎯, 🚀, 😎)
- Never admit you're a bot
- NSFW responses → "I'm PG-13 bro 🙃"
"""

# ===== IMAGE PROCESSING ===== #
def image_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode()

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

# ===== CORE FUNCTIONALITY ===== #
async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Download image
        photo_file = await update.message.photo[-1].get_file()
        img_data = io.BytesIO(await photo_file.download_as_bytearray())
        img = Image.open(img_data)
        
        # GPT-4 Vision analysis
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "system",
                    "content": PERSONALITY
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this trading chart:"},
                        {
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{image_to_base64(img)}"
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        
        await update.message.reply_text(
            f"📊 Chart Analysis:\n\n{response.choices[0].message.content}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"💥 Failed: {str(e)}\nSend cleaner chart pics!")

async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        asset = extract_asset(user_msg)
        
        if asset:
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
            await update.message.reply_text(f"📈 {asset} @ ${price}\n\n{response.choices[0].message.content}")
        else:
            # Casual chat
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.9
            )
            await update.message.reply_text(response.choices[0].message.content)
            
    except Exception as e:
        await update.message.reply_text(f"💥 Oops: {str(e)}\n\nQuick meme break: 😹")

# ===== HELPER FUNCTIONS ===== #
def extract_asset(text: str) -> str:
    text = text.upper().strip()
    if match := re.search(r'([A-Z]{3,6})[/-]([A-Z]{3,6})', text):
        return f"{match.group(1)}/{match.group(2)}"
    cryptos = ["BTC", "ETH", "SOL", "POPCAT"]
    if any(c in text for c in cryptos):
        return f"{next((c for c in cryptos if c in text), 'BTC')}/USDT"
    if match := re.search(r'\b([A-Z]{6})\b', text):
        return f"{match.group(1)[:3]}/{match.group(1)[3:]}"
    return None

# ===== BOT CONTROLS ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🚀 **Tisxa Ultra Bot** 🚀

Now with:
• 📸 Chart screenshot analysis
• 📊 Live market scanning
• 😎 Savage personality

Just:
1. Send chart screenshots
2. Ask "Analyze BTC/USDT"
3. Or chat casually
"""
    await update.message.reply_text(help_text)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_chart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))
    app.run_polling()

if __name__ == "__main__":
    main()
