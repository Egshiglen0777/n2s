import os
import re
import io
import base64
import requests
import logging
from datetime import datetime
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ===== SETUP ===== #
logging.basicConfig(level=logging.INFO)
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

# ===== FAST PRICE FUNCTIONS ===== #
def get_crypto_price(symbol: str) -> tuple:
    """Fetch real-time crypto price from CoinGecko"""
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
    """Mock forex prices - fast and reliable"""
    mock_prices = {
        "EUR/USD": ("$1.0856", 0.15), "GBP/JPY": ("$187.23", -0.32),
        "GBP/USD": ("$1.2678", 0.22), "USD/JPY": ("$149.56", 0.08), 
        "USD/CAD": ("$1.3567", -0.11), "AUD/USD": ("$0.6578", 0.05),
        "EUR/JPY": ("$161.34", 0.12), "EUR/GBP": ("£0.8567", -0.07)
    }
    return mock_prices.get(forex_pair, ("Forex price unavailable", 0))

def get_universal_price(symbol: str) -> tuple:
    """Smart price fetcher"""
    forex_pairs = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'USD/CAD', 'NZD/USD', 'GBP/JPY', 'EUR/JPY', 'EUR/GBP']
    
    if symbol in forex_pairs:
        price, change = get_forex_price(symbol)
        return price, "forex", {"percent_change": change}
    else:
        price, change = get_crypto_price(symbol)
        return price, "crypto", {"priceChangePercent": change}

# ===== FAST ASSET DETECTION ===== #
def extract_asset(text: str) -> str:
    text = text.upper().strip()
    
    casual_words = ['HI', 'HELLO', 'HEY', 'SUP', 'YO', 'BRO', 'DAWG', 'WASSUP', 'HOW ARE YOU']
    if any(word in text for word in casual_words):
        return None
    
    # Forex pairs
    forex_match = re.search(r'\b([A-Z]{3})/([A-Z]{3})\b', text)
    if forex_match:
        return f"{forex_match.group(1)}/{forex_match.group(2)}"
    
    # Crypto pairs
    crypto_match = re.search(r'\b([A-Z]{2,6})/USDT\b', text)
    if crypto_match:
        return f"{crypto_match.group(1)}/USDT"
    
    common_crypto = {'BTC': 'BTC/USDT', 'ETH': 'ETH/USDT', 'SOL': 'SOL/USDT', 'ADA': 'ADA/USDT'}
    for crypto, pair in common_crypto.items():
        if crypto in text and any(x in text for x in ['ANALYZE', 'PRICE', 'CHART']):
            return pair
    
    return None

# ===== FAST HANDLERS ===== #
async def handle_casual_convo(update: Update, query: str):
    query_lower = query.lower()
    
    if any(word in query_lower for word in ['hi', 'hello', 'hey', 'sup', 'yo']):
        responses = [
            "Ayyy! Loria in the house! What's good bro? 💰",
            "Yo dawg! Loria holding it down! 🚀",
            "Sheeeesh! What's cooking, homie? 🔥"
        ]
        import random
        await update.message.reply_text(random.choice(responses))
        return True
    return False

async def analyze_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_msg = update.message.text
        
        # Send immediate response
        await update.message.reply_text("⚡ Loria's on it...")
        
        if await handle_casual_convo(update, user_msg):
            return
            
        asset = extract_asset(user_msg)
        
        if asset:
            price, asset_type, stats = get_universal_price(asset)
            
            if "unavailable" in price or "error" in price:
                await update.message.reply_text(f"🔄 Ayy bro, no data for *{asset}*. Try: BTC/USDT, ETH/USDT, EUR/USD, GBP/JPY")
                return
            
            # FAST GPT-3.5 Analysis
            prompt = f"Ayy bro, analyze {asset} at {price}. Give me key levels and short-term vibe. Keep it street but smart."
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # 🚀 FAST!
                messages=[
                    {"role": "system", "content": PERSONALITY},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=400  # 🚀 SHORT & FAST!
            )
            
            analysis = response.choices[0].message.content
            
            if asset_type == "crypto":
                change = stats.get('priceChangePercent', 0)
                reply_text = f"💰 *{asset}* @ {price}\n24h: {change:+.2f}%\n\n{analysis}\n\n⚠️ Not financial advice"
            else:
                change = stats.get('percent_change', 0)
                reply_text = f"💱 *{asset}* @ {price}\nChange: {change:+.2f}%\n\n{analysis}\n\n⚠️ Stay safe bro"
                
            await update.message.reply_text(reply_text)
        else:
            await update.message.reply_text("Ayy homie! Try: 'analyze BTC/USDT' or 'analyze EUR/USD'")
            
    except Exception as e:
        await update.message.reply_text(f"💥 Quick error: {str(e)[:50]}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
💎 *LORIA TRADING BOT* 💎  
*Inspired by real love* 💖

*Ayy homie! Ready to make some moves?* 🤝

💰 *Crypto*: "analyze btc/usdt"  
💱 *Forex*: "analyze eur/usd"  
📊 *Charts*: Send screenshot

*Examples:*
• "yo analyze btc/usdt"
• "what's gbp/jpy looking like?"
• "eth analysis"

⚠️ *Not financial advice - your homie with charts*
"""
    await update.message.reply_text(help_text)

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_market))
    
    print("🚀 LORIA FAST EDITION - READY!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
