import os
import re
import io
import base64
import requests
from datetime import datetime
from PIL import Image
from telegram import Update
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

# ===== CONFIGURATION ===== #
PERSONALITY = """
You're Tisxa - a professional trading assistant with:
1. **Chart Analysis**: Identify trends, S/R, patterns
2. **Market Data**: Real-time prices + news
3. **Economic Calendar**: Upcoming events
4. **Casual Mode**: Trading humor when appropriate
"""

# ===== IMPROVED IMAGE HANDLING ===== #
async def process_image(photo_file):
    """Download and optimize image for analysis"""
    img_data = io.BytesIO(await photo_file.download_as_bytearray())
    img = Image.open(img_data)
    
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize if too large
    if img.size[0] > 2000 or img.size[1] > 2000:
        img = img.resize((1600, 900))
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=90)
    return base64.b64encode(buffered.getvalue()).decode()

# ===== FIXED CHART ANALYSIS ===== #
async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_base64 = await process_image(photo_file)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze trading charts. Focus on: trends, S/R levels, patterns."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this chart:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        
        analysis = response.choices[0].message.content
        await update.message.reply_text(f"📊 Chart Analysis\n\n{analysis}")
        
    except Exception as e:
        await update.message.reply_text(
            "⚠️ Please send:\n"
            "1. Clear price chart only\n"
            "2. No indicators/overlays\n"
            "3. 4H/Daily timeframe preferred\n"
            f"Error: {str(e)[:200]}"
        )

# ===== ENHANCED MARKET ANALYSIS ===== #
async def analyze_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        asset = extract_asset(user_msg)
        
        if asset:
            is_crypto = 'USDT' in asset
            symbol = asset.replace("/", "")
            
            try:
                price = get_crypto_price(symbol) if is_crypto else get_forex_price(symbol)
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": PERSONALITY},
                        {"role": "user", "content": f"Analyze {asset} at {price}. Include key levels and news."}
                    ]
                )
                await update.message.reply_text(f"📈 {asset} @ {price}\n\n{response.choices[0].message.content}")
            except Exception as e:
                await update.message.reply_text(f"🔴 Data error: {str(e)}\nTry crypto pairs like BTC/USDT")
        else:
            await handle_general_query(update, user_msg)
            
    except Exception as e:
        await update.message.reply_text(f"💥 Oops: {str(e)}")

# ===== ECONOMIC CALENDAR ===== #
async def get_economic_news():
    """Fetch upcoming economic events"""
    try:
        url = f"https://api.twelvedata.com/economic_calendar?apikey={os.getenv('TWELVEDATA_API_KEY')}"
        events = requests.get(url).json().get("data", [])
        return "\n".join(
            f"• {e['event']} ({e['country']}) @ {e['time']}" 
            for e in events[:5]  # Show next 5 events
        )
    except:
        return "⚠️ News data unavailable"

# ===== GENERAL QUERIES ===== #
async def handle_general_query(update: Update, query: str):
    if "news" in query.lower() or "economic" in query.lower():
        news = await get_economic_news()
        await update.message.reply_text(f"📅 Upcoming Events:\n\n{news}")
    elif "real time" in query.lower():
        await update.message.reply_text("🔄 I track real-time prices via:\n• Bybit (crypto)\n• TwelveData (forex)")
    else:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": PERSONALITY},
                {"role": "user", "content": query}
            ],
            temperature=0.7
        )
        await update.message.reply_text(response.choices[0].message.content)

# ===== HELPER FUNCTIONS ===== #
def extract_asset(text: str) -> str:
    text = text.upper().strip()
    if match := re.search(r'([A-Z]{3,6})[/-]?([A-Z]{3,6})', text):
        base, quote = match.groups()
        return f"{base}/{quote or 'USDT'}"
    return None

# ===== BOT SETUP ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
💎 Tisxa Trading Bot 💎

Commands:
• Send chart screenshots
• "Analyze GBP/JPY"
• "News tomorrow?"
• "Real-time data?"
"""
    await update.message.reply_text(help_text)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_chart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_market))
    app.run_polling()

if __name__ == "__main__":
    main()
