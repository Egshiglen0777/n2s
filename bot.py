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

# ===== API CONFIG ===== #
BINANCE_BASE_URL = "https://api.binance.com"
TWELVEDATA_BASE_URL = "https://api.twelvedata.com"

# ===== INIT ===== #
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== CONFIGURATION ===== #
PERSONALITY = """
You're Tisxa - a professional trading assistant with:
1. **Chart Analysis**: Identify trends, S/R, patterns
2. **Market Data**: Real-time crypto + forex
3. **Economic Calendar**: Upcoming events
4. **Risk Warnings**: Always include risk disclaimers
5. **Casual Mode**: Trading humor when appropriate

Always provide clear, actionable insights with risk management notes.
"""

# ===== BINANCE CRYPTO FUNCTIONS ===== #
def get_binance_price(symbol: str) -> str:
    """Fetch real-time crypto price from Binance"""
    try:
        binance_symbol = symbol.replace("/", "")
        url = f"{BINANCE_BASE_URL}/api/v3/ticker/price?symbol={binance_symbol}"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if 'price' in data:
            price = float(data['price'])
            return f"${price:,.2f}" if price > 1 else f"${price:.6f}"
        else:
            return "Price unavailable"
            
    except Exception as e:
        return f"Error: {str(e)}"

def get_binance_24h_stats(symbol: str) -> dict:
    """Get 24h crypto price change statistics"""
    try:
        binance_symbol = symbol.replace("/", "")
        url = f"{BINANCE_BASE_URL}/api/v3/ticker/24hr?symbol={binance_symbol}"
        
        response = requests.get(url, timeout=5)
        return response.json()
    except:
        return {}

# ===== TWELVEDATA FOREX FUNCTIONS ===== #
def get_forex_price(forex_pair: str) -> str:
    """Fetch real-time forex price from Twelve Data"""
    try:
        # Format: EUR/USD -> EUR/USD
        api_key = os.getenv("TWELVEDATA_API_KEY")
        url = f"{TWELVEDATA_BASE_URL}/price?symbol={forex_pair}&apikey={api_key}"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('status') == 'ok' and 'price' in data:
            price = float(data['price'])
            return f"${price:.4f}"
        else:
            return "Forex price unavailable"
            
    except Exception as e:
        return f"Error: {str(e)}"

def get_forex_quote(forex_pair: str) -> dict:
    """Get detailed forex quote"""
    try:
        api_key = os.getenv("TWELVEDATA_API_KEY")
        url = f"{TWELVEDATA_BASE_URL}/quote?symbol={forex_pair}&apikey={api_key}"
        
        response = requests.get(url, timeout=5)
        return response.json()
    except:
        return {}

# ===== UNIVERSAL PRICE FETCHER ===== #
def get_universal_price(symbol: str) -> tuple:
    """Smart price fetcher - returns (price, asset_type, stats)"""
    symbol_clean = symbol.upper().replace("/", "")
    
    # Check if it's forex (major pairs)
    forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']
    
    if symbol_clean in forex_pairs:
        price = get_forex_price(symbol)
        stats = get_forex_quote(symbol)
        return price, "forex", stats
    
    # Check if it's crypto (ends with USDT or major pairs)
    elif symbol_clean.endswith('USDT') or symbol_clean in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']:
        price = get_binance_price(symbol)
        stats = get_binance_24h_stats(symbol)
        return price, "crypto", stats
    
    else:
        return "Asset not supported", "unknown", {}

# ===== IMPROVED IMAGE HANDLING ===== #
async def process_image(photo_file):
    """Download and optimize image for analysis"""
    img_data = io.BytesIO(await photo_file.download_as_bytearray())
    img = Image.open(img_data)
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    if img.size[0] > 2000 or img.size[1] > 2000:
        img = img.resize((1600, 900))
    
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=90)
    return base64.b64encode(buffered.getvalue()).decode()

# ===== CHART ANALYSIS ===== #
async def analyze_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_base64 = await process_image(photo_file)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze trading charts. Focus on: trends, support/resistance levels, chart patterns. Provide actionable insights with risk management notes."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this trading chart:"},
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
        await update.message.reply_text(f"📊 Chart Analysis\n\n{analysis}\n\n⚠️ Not financial advice")
        
    except Exception as e:
        await update.message.reply_text(
            "⚠️ Please send:\n"
            "• Clear price chart only\n"
            "• No indicators/overlays\n"
            "• 4H/Daily timeframe preferred\n"
            f"Error: {str(e)[:200]}"
        )

# ===== ENHANCED MARKET ANALYSIS ===== #
async def analyze_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        asset = extract_asset(user_msg)
        
        if asset:
            price, asset_type, stats = get_universal_price(asset)
            
            # Build analysis prompt based on asset type
            if asset_type == "crypto" and stats:
                change = float(stats.get('priceChangePercent', 0))
                volume = float(stats.get('volume', 0))
                prompt = f"Analyze {asset} at {price}. 24h change: {change:+.2f}%. Volume: ${volume:,.0f}. Provide key levels and short-term outlook with risk management."
                
            elif asset_type == "forex" and stats:
                change = float(stats.get('percent_change', 0))
                prompt = f"Analyze {asset} at {price}. Daily change: {change:+.2f}%. Provide key levels and short-term outlook with risk management."
                
            else:
                prompt = f"Analyze {asset} at {price}. Provide key levels and short-term outlook with risk management."
            
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Format response
            analysis = response.choices[0].message.content
            
            if asset_type == "crypto" and stats:
                change = float(stats.get('priceChangePercent', 0))
                volume = float(stats.get('volume', 0))
                reply_text = f"💰 {asset} @ {price}\n24h: {change:+.2f}% | Vol: ${volume:,.0f}\n\n{analysis}\n\n⚠️ Not financial advice"
            elif asset_type == "forex" and stats:
                change = float(stats.get('percent_change', 0))
                reply_text = f"💱 {asset} @ {price}\nChange: {change:+.2f}%\n\n{analysis}\n\n⚠️ Not financial advice"
            else:
                reply_text = f"📈 {asset} @ {price}\n\n{analysis}\n\n⚠️ Not financial advice"
                
            await update.message.reply_text(reply_text)
        else:
            await handle_general_query(update, user_msg)
            
    except Exception as e:
        await update.message.reply_text(f"💥 Market data error: {str(e)}")

# ===== ECONOMIC CALENDAR ===== #
async def get_economic_news():
    """Fetch upcoming economic events"""
    try:
        api_key = os.getenv("TWELVEDATA_API_KEY")
        url = f"{TWELVEDATA_BASE_URL}/economic_calendar?apikey={api_key}"
        response = requests.get(url, timeout=5)
        events = response.json().get("data", [])
        
        today_events = [
            f"• {e['event']} ({e['country']}) @ {e['time']}" 
            for e in events[:5]  # Show next 5 events
        ]
        return "\n".join(today_events) if today_events else "No major events today"
    except:
        return "⚠️ Economic calendar unavailable"

# ===== GENERAL QUERIES ===== #
async def handle_general_query(update: Update, query: str):
    query_lower = query.lower()
    
    if "news" in query_lower or "economic" in query_lower or "calendar" in query_lower:
        news = await get_economic_news()
        await update.message.reply_text(f"📅 Economic Calendar:\n\n{news}")
    
    elif "real time" in query_lower or "data" in query_lower:
        await update.message.reply_text(
            "🔄 Real-time Data Sources:\n"
            "• Crypto: Binance (100+ pairs)\n"
            "• Forex: Twelve Data (Major pairs)\n"
            "• Analysis: GPT-4 + Chart reading\n\n"
            "Try: 'Analyze BTC/USDT' or 'Analyze EUR/USD'"
        )
    
    elif "support" in query_lower or "pairs" in query_lower:
        await update.message.reply_text(
            "💎 Supported Markets:\n\n"
            "CRYPTO (Binance):\n"
            "• BTC/USDT, ETH/USDT, BNB/USDT\n"
            "• ADA/USDT, DOT/USDT, LINK/USDT\n"
            "• 100+ Binance pairs\n\n"
            "FOREX (Twelve Data):\n"
            "• EUR/USD, GBP/USD, USD/JPY\n"
            "• USD/CHF, AUD/USD, USD/CAD\n"
            "• NZD/USD\n\n"
            "Just send: 'Analyze [PAIR]'"
        )
    
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
    if match := re.search(r'([A-Z]{2,6})[/-]?([A-Z]{2,6})', text):
        base, quote = match.groups()
        return f"{base}/{quote}"
    return None

# ===== BOT SETUP ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
💎 TISXA TRADING BOT 💎

*Real-time Crypto + Forex Analysis*

📊 **Chart Analysis**: Send screenshot
💰 **Crypto Prices**: 'Analyze BTC/USDT'
💱 **Forex Prices**: 'Analyze EUR/USD'  
📅 **Economic News**: 'News today?'
🔄 **Data Sources**: 'Real-time data?'

*Supported Markets:*
• Crypto: 100+ Binance pairs
• Forex: Major pairs (EUR/USD, etc.)

⚠️ *Not financial advice - Always do your own research*
"""
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    print(f"Error: {context.error}")
    try:
        await update.message.reply_text("⚠️ Bot error. Please try again or check /start")
    except:
        pass

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_chart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_market))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    print("🚀 Tisxa Trading Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
