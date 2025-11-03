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

# ===== PERSONALITY ===== #
PERSONALITY = """
Та N2S — ухаалаг арилжааны туслах. Хэрэглэгчидтэй Монгол хэлээр
найрсаг, энгийн, ойлгомжтой байдлаар харилцана.

⚡️ Хэн бэ:
- Крипто, форекс, хувьцаа, AI, амьдралын зөвлөгөө гээд бүгдэд нь тусалдаг.
- Чатбот биш, жинхэнэ найз шиг тайлбарладаг.
- Хэрэглэгч юу асууж байгааг ойлгож, богино бөгөөд утгатай хариулдаг.

🎯 Хэллэгийн хэв маяг:
- Найрсаг, энгийн, жаахан хошигнолтой
- Илүү сэтгэлтэй, эелдэг, туршлагатай мэт
- Заримдаа "найз аа", "ах аа", "хөө" гэж дуудах үед тохируулж хэрэглэ

⚠️ Жич:
- Санхүүгийн зөвлөгөө өгөхгүй, зөвхөн мэдээлэл өгдөг гэдгийг сануул.
- Хэрэглэгчээс асуулт авах, ярилцлага үргэлжлүүлэх байдлаар бич.
"""

# ===== PRICE FETCHING ===== #
def get_crypto_price(symbol: str) -> tuple:
    try:
        coin_mapping = {
            "BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "BNB/USDT": "binancecoin",
            "SOL/USDT": "solana", "ADA/USDT": "cardano", "XRP/USDT": "ripple",
            "DOT/USDT": "polkadot", "LINK/USDT": "chainlink", "DOGE/USDT": "dogecoin"
        }
        coin_id = coin_mapping.get(symbol)
        if not coin_id:
            return "Хэмжигдэхгүй байна", 0
            
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if coin_id in data:
            price = data[coin_id]['usd']
            change = data[coin_id].get('usd_24h_change', 0)
            return f"${price:,.2f}", change
        return "Үнэ олдсонгүй", 0
    except:
        return "API алдаа", 0

def get_forex_price(forex_pair: str) -> tuple:
    mock_prices = {
        "EUR/USD": ("$1.0856", 0.15), "GBP/JPY": ("$187.23", -0.32),
        "GBP/USD": ("$1.2678", 0.22), "USD/JPY": ("$149.56", 0.08), 
        "USD/CAD": ("$1.3567", -0.11), "AUD/USD": ("$0.6578", 0.05),
        "EUR/JPY": ("$161.34", 0.12), "EUR/GBP": ("£0.8567", -0.07)
    }
    return mock_prices.get(forex_pair, ("Үнийн мэдээлэл алга", 0))

def extract_asset(text: str) -> str:
    text = text.upper().strip()
    forex = re.search(r'\b([A-Z]{3})/([A-Z]{3})\b', text)
    if forex: return forex.group()
    crypto = re.search(r'\b([A-Z]{2,6})/USDT\b', text)
    if crypto: return crypto.group()
    return None

# ===== OPENAI CALLER ===== #
async def chat_with_openai(user_text):
    try:
        res = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": PERSONALITY},
                {"role": "user", "content": user_text}
            ],
            temperature=0.8,
            max_tokens=400
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"Алдаа гарлаа: {e}"

# ===== HANDLERS ===== #
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    
    if asset := extract_asset(user_msg):
        await update.message.reply_text("Хэсэг хүлээгээрэй...")
        price, change = get_crypto_price(asset) if "USDT" in asset else get_forex_price(asset)
        reply = f"{asset} одоогоор {price} байна. 24 цагийн өөрчлөлт: {change:+.2f}%. Танд дүн шинжилгээ хийх үү?"
        await update.message.reply_text(reply)
    else:
        reply = await chat_with_openai(user_msg)
        await update.message.reply_text(reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """
👋 Сайн байна уу! Би бол N2S — таны хиймэл оюунтай найз.

Та крипто, форекс, хувьцаа эсвэл амьдралын зөвлөгөө ч асууж болно.

Жишээ:
• BTC/USDT шинжилгээ
• EUR/USD ханш хэд байна?
• Зөвхөн MACD гэж юу вэ?

Юу асуух вэ, надтай ярьцгаая.
"""
    await update.message.reply_text(welcome)

# ===== MAIN ===== #
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))
    print("🚀 N2S Bot амжилттай ачааллаа.")
    app.run_polling()

if __name__ == "__main__":
    main()
