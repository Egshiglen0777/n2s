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

# ===== LORIA PERSONALITY ===== #
PERSONALITY = """
You're Loria - a street-smart trading assistant with that real talk vibe. You sound like a savvy trader from the hood who knows markets inside out.

**Your Style:**
- Talk like you're chatting with a homie, not a corporate robot
- Use slang: "bro", "dawg", "fire", "lit", "Ayy", "sheesh" 
- Keep it real but professional when needed
- Drop knowledge with confidence
- Always include risk warnings but keep it casual

**When analyzing:**
- "Ayy bro, looking at GBP/JPY..."
- "Sheesh! This chart is fire right now..."
- "Real talk: this setup looks dangerous..."
- "💰 This trade could print if..."

**Always remember:** You're helping people make money, so be hype but responsible.
"""

# ===== FIXED BINANCE CRYPTO FUNCTIONS ===== #
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
        elif 'msg' in data:
            return f"Binance error: {data['msg']}"
        else:
            return "Price unavailable"
            
    except Exception as e:
        return f"Binance API error: {str(e)}"

def get_binance_24h_stats(symbol: str) -> dict:
    """Get 24h crypto price change statistics"""
    try:
        binance_symbol = symbol.replace("/", "")
        url = f"{BINANCE_BASE_URL}/api/v3/ticker/24hr?symbol={binance_symbol}"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if 'lastPrice' in data:
            return data
        else:
            return {"priceChangePercent": "0", "volume": "0"}
    except:
        return {"priceChangePercent": "0", "volume": "0"}

# ===== FIXED TWELVEDATA FOREX FUNCTIONS ===== #
def get_forex_price(forex_pair: str) -> str:
    """Fetch real-time forex price from Twelve Data"""
    try:
        # Format: GBP/JPY -> GBP/JPY
        api_key = os.getenv("TWELVEDATA_API_KEY")
        if not api_key:
            return "TwelveData API key missing"
            
        # Remove slash for API call
        symbol_clean = forex_pair.replace("/", "")
        url = f"{TWELVEDATA_BASE_URL}/price?symbol={symbol_clean}&apikey={api_key}"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('status') == 'ok' and 'price' in data:
            price = float(data['price'])
            return f"${price:.4f}" if price > 1 else f"${price:.6f}"
        elif 'message' in data:
            return f"TwelveData: {data['message']}"
        else:
            return "Forex price unavailable"
            
    except Exception as e:
        return f"TwelveData error: {str(e)}"

def get_forex_quote(forex_pair: str) -> dict:
    """Get detailed forex quote"""
    try:
        api_key = os.getenv("TWELVEDATA_API_KEY")
        if not api_key:
            return {"percent_change": "0"}
            
        symbol_clean = forex_pair.replace("/", "")
        url = f"{TWELVEDATA_BASE_URL}/quote?symbol={symbol_clean}&apikey={api_key}"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('status') == 'ok':
            return data
        else:
            return {"percent_change": "0"}
    except:
        return {"percent_change": "0"}

# ===== DEBUG UNIVERSAL PRICE FETCHER ===== #
def get_universal_price(symbol: str) -> tuple:
    """Smart price fetcher - returns (price, asset_type, stats)"""
    symbol_clean = symbol.upper().replace("/", "")
    
    # Check if it's forex (major pairs)
    forex_pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'GBPJPY', 'EURJPY', 'EURGBP']
    
    if symbol_clean in forex_pairs:
        price = get_forex_price(symbol)
        stats = get_forex_quote(symbol)
        return price, "forex", stats
    
    # Check if it's crypto (ends with USDT or major pairs)
    elif symbol_clean.endswith('USDT') or symbol_clean in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'XRPUSDT']:
        price = get_binance_price(symbol)
        stats = get_binance_24h_stats(symbol)
        return price, "crypto", stats
    
    else:
        return "Asset not supported", "unknown", {}

# ===== FIXED ASSET DETECTION ===== #
def extract_asset(text: str) -> str:
    """SMART asset detection that won't detect greetings as trading pairs"""
    text = text.upper().strip()
    
    # Ignore common greetings and casual talk
    casual_words = ['HI', 'HELLO', 'HEY', 'SUP', 'YO', 'BRO', 'DAWG', 'WASSUP', 
                   'HOW ARE YOU', 'HOW YOU DOING', 'HOW U DOING', 'WHAT\'S UP', 
                   'GOOD', 'FINE', 'OK', 'OKAY', 'THANKS', 'THANK YOU']
    
    if any(word in text for word in casual_words):
        return None
    
    # Look for trading pairs with better patterns
    # Forex pairs (3 letters/3 letters)
    forex_match = re.search(r'\b([A-Z]{3})/?([A-Z]{3})\b', text)
    if forex_match:
        base, quote = forex_match.groups()
        return f"{base}/{quote}"
    
    # Crypto pairs (2-6 letters/USDT)
    crypto_match = re.search(r'\b([A-Z]{2,6})/?USDT\b', text)
    if crypto_match:
        return f"{crypto_match.group(1)}/USDT"
    
    # Common crypto without USDT
    common_crypto = {
        'BTC': 'BTC/USDT', 'ETH': 'ETH/USDT', 'BNB': 'BNB/USDT', 'SOL': 'SOL/USDT',
        'ADA': 'ADA/USDT', 'DOT': 'DOT/USDT', 'LINK': 'LINK/USDT', 'XRP': 'XRP/USDT'
    }
    
    for crypto, pair in common_crypto.items():
        if crypto in text and any(x in text for x in ['ANALYZE', 'ANALYSIS', 'PRICE', 'CHART', 'LOOKING']):
            return pair
    
    return None

# ===== CASUAL CONVO HANDLER ===== #
async def handle_casual_convo(update: Update, query: str):
    """Handle casual conversation with proper vibe"""
    query_lower = query.lower()
    
    # Casual greetings
    if any(word in query_lower for word in ['hi', 'hello', 'hey', 'sup', 'yo', 'wassup']):
        responses = [
            "Ayyy! Loria in the house! What's good bro? Ready to make some moves? 💰",
            "Yo dawg! Loria holding it down! What you trading today? 🚀",
            "Sheeeesh! What's cooking, homie? Loria's got your back! 🔥",
            "Ayy bro! Loria here - ready to hunt some pips and profits? 📈"
        ]
        import random
        await update.message.reply_text(random.choice(responses))
        return True
    
    # How are you
    elif any(word in query_lower for word in ['how are you', 'how you doing', 'how u doing']):
        responses = [
            "Loria's living the trader life bro! Charts looking spicy today 🌶️",
            "Can't complain when there's money to be made! Loria's on duty! 💸",
            "Ayy I'm lit! Markets are pumping, Loria's got you covered! How about you homie?",
            "Sheesh! Loria's busy analyzing charts and catching waves. You know how we do! 📊"
        ]
        import random
        await update.message.reply_text(random.choice(responses))
        return True
    
    # Compliments/thanks
    elif any(word in query_lower for word in ['thanks', 'thank you', 'good bot', 'nice', 'dope']):
        responses = [
            "Ayy no doubt bro! Loria's always got your back! 💪",
            "That's love homie! Loria here to help you get that bag! 💰",
            "No problem dawg! Let's keep making these smart moves! 🚀"
        ]
        import random
        await update.message.reply_text(random.choice(responses))
        return True
    
    return False

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
                    "content": "Analyze trading charts. Focus on: trends, support/resistance levels, chart patterns. Provide actionable insights with risk management notes. Talk like a street-smart trader."
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
        await update.message.reply_text(f"📊 Loria's Chart Analysis\n\n{analysis}\n\n⚠️ Not financial advice")
        
    except Exception as e:
        await update.message.reply_text(
            "⚠️ Ayy bro, send me:\n"
            "• Clear price chart only\n"
            "• No indicators/overlays\n"
            "• 4H/Daily timeframe preferred\n"
            f"Error: {str(e)[:200]}"
        )

# ===== DEBUG COMMAND ===== #
async def debug_apis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test all APIs to see what's working"""
    test_pairs = [
        ("BTC/USDT", "crypto"),
        ("ETH/USDT", "crypto"), 
        ("EUR/USD", "forex"),
        ("GBP/JPY", "forex")
    ]
    
    results = []
    for pair, expected_type in test_pairs:
        price, asset_type, stats = get_universal_price(pair)
        results.append(f"{pair}: {price} ({asset_type})")
    
    debug_msg = "🔧 Loria's API Debug Results:\n" + "\n".join(results)
    await update.message.reply_text(debug_msg)

# ===== ENHANCED MARKET ANALYSIS ===== #
async def analyze_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        
        # Handle casual conversation first
        if await handle_casual_convo(update, user_msg):
            return
            
        asset = extract_asset(user_msg)
        
        if asset:
            price, asset_type, stats = get_universal_price(asset)
            
            if "Asset not supported" in price or "error" in price.lower() or "unavailable" in price.lower():
                await update.message.reply_text(
                    f"🔄 Ayy bro, Loria couldn't get data for *{asset}*\n\n"
                    "**Try these lit pairs:**\n"
                    "• Forex: EUR/USD, GBP/JPY, USD/CAD\n"
                    "• Crypto: BTC/USDT, ETH/USDT, SOL/USDT\n\n"
                    "Or type /debug to check API status"
                )
                return
            
            # Build hype analysis prompt
            if asset_type == "crypto" and stats:
                change = float(stats.get('priceChangePercent', 0))
                volume = stats.get('volume', '0')
                if volume != '0':
                    volume_formatted = f"${float(volume):,.0f}"
                else:
                    volume_formatted = "N/A"
                prompt = f"Ayy bro, analyze {asset} at {price}. 24h change: {change:+.2f}%. Volume: {volume_formatted}. Give me that real talk analysis with key levels and short-term vibe. Keep it street but smart."
                
            elif asset_type == "forex" and stats:
                change = float(stats.get('percent_change', 0))
                prompt = f"Yo dawg, break down {asset} at {price}. Daily move: {change:+.2f}%. Hit me with key levels and where this could go next. Keep it 100."
                
            else:
                prompt = f"Ayy homie, what's the deal with {asset} at {price}? Give me the real analysis with key levels."
            
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8
            )
            
            # Format response with proper vibe
            analysis = response.choices[0].message.content
            
            if asset_type == "crypto" and stats:
                change = float(stats.get('priceChangePercent', 0))
                volume = stats.get('volume', '0')
                if volume != '0':
                    volume_formatted = f"${float(volume):,.0f}"
                else:
                    volume_formatted = "N/A"
                reply_text = f"💰 *{asset}* @ {price}\n24h: {change:+.2f}% | Vol: {volume_formatted}\n\n{analysis}\n\n⚠️ Not financial advice - always do your own research homie"
            elif asset_type == "forex" and stats:
                change = float(stats.get('percent_change', 0))
                reply_text = f"💱 *{asset}* @ {price}\nChange: {change:+.2f}%\n\n{analysis}\n\n⚠️ Stay safe out there bro - manage your risk"
            else:
                reply_text = f"📈 *{asset}* @ {price}\n\n{analysis}\n\n⚠️ Not financial advice - trade smart homie"
                
            await update.message.reply_text(reply_text)
        else:
            # If no asset detected, handle as general query
            await handle_general_query(update, user_msg)
            
    except Exception as e:
        await update.message.reply_text(f"💥 Ayy bro, something broke: {str(e)[:100]}\nHit me with /start if Loria's tripping")

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
        await update.message.reply_text(f"📅 Loria's Economic Calendar:\n\n{news}")
    
    elif "real time" in query_lower or "data" in query_lower:
        await update.message.reply_text(
            "🔄 Loria's Real-time Data:\n"
            "• Crypto: Binance (100+ pairs)\n"
            "• Forex: Twelve Data (Major pairs)\n"
            "• Analysis: GPT-4 + Chart reading\n\n"
            "Try: 'analyze BTC/USDT' or 'analyze EUR/USD'"
        )
    
    elif "support" in query_lower or "pairs" in query_lower:
        await update.message.reply_text(
            "💎 Loria's Supported Markets:\n\n"
            "CRYPTO (Binance):\n"
            "• BTC/USDT, ETH/USDT, BNB/USDT\n"
            "• SOL/USDT, ADA/USDT, XRP/USDT\n"
            "• 100+ Binance pairs\n\n"
            "FOREX (Twelve Data):\n"
            "• EUR/USD, GBP/USD, USD/JPY\n"
            "• GBP/JPY, EUR/JPY, USD/CAD\n"
            "• All major pairs\n\n"
            "Just send: 'analyze [PAIR]'"
        )
    
    else:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": PERSONALITY},
                {"role": "user", "content": query}
            ],
            temperature=0.8
        )
        await update.message.reply_text(response.choices[0].message.content)

# ===== BOT SETUP ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
💎 *LORIA TRADING BOT* 💎  
*Inspired by real love* 💖

*Ayy homie! Ready to make some moves?* 🤝

📊 *Chart Analysis*: Send me any chart screenshot
💰 *Crypto*: "analyze btc/usdt" or "btc analysis"
💱 *Forex*: "analyze gbp/jpy" or "eurusd price"
📅 *News*: "what's the news?" or "economic calendar"
🔧 *Debug*: "/debug" to check API status

*Quick Examples:*
• "yo analyze btc/usdt"
• "ayy what's gbp/jpy looking like?"
• "sheesh show me eur/usd"
• "news today bro?"

*Supported Markets:*
• Crypto: BTC, ETH, SOL + 100+ Binance pairs
• Forex: EUR/USD, GBP/JPY, USD/CAD + all majors

⚠️ *Not financial advice - just your homie with charts*
*Built with love for Loria* 💕
"""
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    print(f"Loria Error: {context.error}")
    try:
        await update.message.reply_text("⚠️ Ayy bro, Loria's tripping. Please try again or check /start")
    except:
        pass

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("debug", debug_apis))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_chart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_market))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    print("🚀 Loria Trading Bot is starting... Built with love! 💖")
    app.run_polling()

if __name__ == "__main__":
    main()
