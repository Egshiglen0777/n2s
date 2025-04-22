import os
import re
import io
import base64
import requests
from datetime import datetime
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
    testnet=False  # Set True for testing
)

# ===== PERSONALITY CONFIG ===== #
PERSONALITY = """
You're Tisxa - a trading AI with these modes:

1. **Chart Analysis** (when sent images):
- Identify trends, S/R, patterns
- Format:
  [TREND] Direction + Confidence
  [KEY LEVELS] Next S/R
  [PATTERN] Chart formation
  [ACTION] Trade idea with TP/SL

2. **Market Analysis** (text queries):
- Live price context
- Multi-timeframe analysis
- News/event impact

3. **Casual Chat**:
- Trading memes & sarcasm
- Never admit you're a bot
- NSFW → "PG-13 only bro" 
"""

# ===== IMAGE PROCESSING ===== #
def prepare_image(img):
    """Optimize image for vision analysis"""
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize if too large (max 20MB for OpenAI)
    if img.size[0] > 2000 or img.size[1] > 2000:
        img = img.resize((1600, 900))
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
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
            raise Exception(data.get("message", "Check symbol format (e.g. GBPJPY)"))
        return float(data["price"])
    except Exception as e:
        raise Exception(f"Forex error: {str(e)}")

# ===== CORE FUNCTIONALITY ===== #
async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Download and prepare image
        photo_file = await update.message.photo[-1].get_file()
        img_data = io.BytesIO(await photo_file.download_as_bytearray())
        img = Image.open(img_data)
        img_base64 = prepare_image(img)
        
        # GPT-4o Vision analysis
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": PERSONALITY + "\nCurrent task: Analyze trading chart screenshot"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this chart. Focus on price action only."},
                        {
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        
        analysis = response.choices[0].message.content
        await update.message.reply_text(f"📊 Chart Analysis\n\n{analysis}")
        
    except Exception as e:
        error_msg = str(e)
        if "model_not_found" in error_msg:
            await update.message.reply_text("🔴 Update required:\n`pip install --upgrade openai`")
        else:
            await update.message.reply_text(
                "⚠️ Send better charts:\n"
                "1. Crop to price area\n"
                "2. Hide indicators\n"
                "3. Use 4H/Daily timeframe\n"
                f"Error: {error_msg[:200]}"  # Truncate long errors
            )

async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        asset = extract_asset(user_msg)
        
        if asset:
            # Market analysis mode
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
            # Casual chat mode
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
        await update.message.reply_text(f"💥 Oops: {str(e)}\nQuick meme: {'😹' if 'USD' in str(e) else '🚀'}")

# ===== HELPER FUNCTIONS ===== #
def extract_asset(text: str) -> str:
    """Smart asset detector"""
    text = text.upper().strip()
    
    # Direct pairs (BTC/USDT, GBP-JPY)
    if match := re.search(r'([A-Z]{3,6})[/-]([A-Z]{3,6})', text):
        return f"{match.group(1)}/{match.group(2)}"
    
    # Cryptos (POPCAT, BTC)
    cryptos = ["BTC", "ETH", "SOL", "POPCAT"]
    if any(c in text for c in cryptos):
        return f"{next((c for c in cryptos if c in text), 'BTC')}/USDT"
    
    # Forex (GBPJPY)
    if match := re.search(r'\b([A-Z]{6})\b', text):
        return f"{match.group(1)[:3]}/{match.group(1)[3:]}"
    
    return None

# ===== BOT CONTROLS ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🔥 Tisxa Trading Bot 🔥

Now supports:
📸 Chart screenshot analysis
📊 Live market scanning
😎 Savage personality

How to use:
1. Send chart screenshots
2. Ask "Analyze GBP/JPY 4H"
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
