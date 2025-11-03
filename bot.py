import os
import re
import requests
import logging
from typing import Tuple, Optional, Dict

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from openai import OpenAI

# ===== SETUP ===== #
logging.basicConfig(level=logging.INFO)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Per-chat language memory: 'en' or 'mn'
LANG: Dict[int, str] = {}

# ===== PERSONALITY (neutral core) ===== #
PERSONALITY_CORE = """
You are N2S — a sharp, friendly trading assistant who speaks clearly, stays practical, and never gives financial advice.
You analyze markets (crypto, forex, metals, stocks) and give structured, actionable insights: trend, key levels, indicators, risk notes.
Be concise but complete. No hype, no guarantees. Always include a brief NFA reminder at the end.
"""

# Language wrappers
PERSONALITY_MN = """
Та Монгол хэлээр ойлгомжтой, найрсаг, шууд утгатайгаар ярь. Робот маягийн биш, бодит трейдер шиг энгийнээр тайлбарла.
Төгсгөлд богино 'Санхүүгийн зөвлөгөө биш' сануулга оруул.
"""
PERSONALITY_EN = """
Speak in natural, modern English — calm, trader-to-trader tone. End with a short 'Not financial advice' reminder.
"""

def system_prompt_for_lang(lang: str) -> str:
    return PERSONALITY_CORE + (PERSONALITY_EN if lang == "en" else PERSONALITY_MN)

# ===== PRICE FETCHING ===== #
def get_crypto_price(symbol: str) -> Tuple[str, float]:
    """Returns (display_price, change_pct_24h)."""
    try:
        coin_mapping = {
            "BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "BNB/USDT": "binancecoin",
            "SOL/USDT": "solana", "ADA/USDT": "cardano", "XRP/USDT": "ripple",
            "DOT/USDT": "polkadot", "LINK/USDT": "chainlink", "DOGE/USDT": "dogecoin"
        }
        coin_id = coin_mapping.get(symbol)
        if not coin_id:
            return "Price unavailable", 0.0

        url = f"https://api.coingecko.com/api/v3/simple/price"
        resp = requests.get(url, params={
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }, timeout=10)
        data = resp.json()
        if coin_id in data:
            price = data[coin_id]["usd"]
            change = float(data[coin_id].get("usd_24h_change", 0.0))
            return f"${price:,.2f}", change
        return "Price unavailable", 0.0
    except Exception:
        return "API error", 0.0

def get_forex_price(pair: str) -> Tuple[str, float]:
    """Mocked forex price — replace with your data provider later."""
    mock = {
        "EUR/USD": ("$1.0856", 0.15), "GBP/JPY": ("¥187.23", -0.32),
        "GBP/USD": ("$1.2678", 0.22), "USD/JPY": ("¥149.56", 0.08),
        "USD/CAD": ("$1.3567", -0.11), "AUD/USD": ("$0.6578", 0.05),
        "EUR/JPY": ("¥161.34", 0.12), "EUR/GBP": ("£0.8567", -0.07),
        "XAU/USD": ("Price unavailable", 0.00)  # will try metals API below
    }
    return mock.get(pair, ("Price unavailable", 0.0))

def get_gold_price() -> Tuple[str, float]:
    """
    Try Metals-API if METALS_API_KEY is set.
    Returns (display_price_usd_per_oz, change_pct_24h_guess=0.0).
    """
    key = os.getenv("METALS_API_KEY")
    if not key:
        return "Price unavailable", 0.0
    try:
        # MetalsAPI returns rates like: 1 USD = rate XAU ? or vice versa depending on plan.
        # We'll request base=USD & symbols=XAU and invert if needed.
        url = "https://metals-api.com/api/latest"
        resp = requests.get(url, params={"access_key": key, "base": "USD", "symbols": "XAU"}, timeout=10)
        data = resp.json()
        # Expect data["rates"]["XAU"] = ounces of gold per USD  (varies by plan)
        # If it's XAU per USD, then USD per XAU = 1 / rate.
        rate = float(data["rates"]["XAU"])
        if rate <= 0:
            return "Price unavailable", 0.0
        usd_per_xau = 1.0 / rate
        return f"${usd_per_xau:,.2f}", 0.0
    except Exception:
        return "Price unavailable", 0.0

def get_universal_price(symbol: str) -> Tuple[str, str, float]:
    """
    Returns (display_price, asset_type, change_pct).
    asset_type in {"crypto","forex","metal","unknown"}
    """
    if symbol == "XAU/USD":
        price, chg = get_gold_price()
        return price, "metal", chg

    forex_pairs = {
        'EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','USD/CAD',
        'NZD/USD','GBP/JPY','EUR/JPY','EUR/GBP','XAU/USD'
    }
    if symbol in forex_pairs:
        price, change = get_forex_price(symbol)
        return price, "forex", change
    else:
        price, change = get_crypto_price(symbol)
        # If not in mapping, crypto fetch returns "Price unavailable"
        return price, "crypto", change

# ===== ASSET DETECTION ===== #
def extract_asset(text: str) -> Optional[str]:
    t = text.upper()
    m = re.search(r'\b([A-Z]{3})/([A-Z]{3})\b', t)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m2 = re.search(r'\b([A-Z]{2,6})/USDT\b', t)
    if m2:
        return f"{m2.group(1)}/USDT"
    # quick aliases
    if "XAU" in t and "USD" in t:
        return "XAU/USD"
    if t.strip() in {"XAUUSD","GOLD"}:
        return "XAU/USD"
    return None

# ===== OPENAI HELPERS ===== #
def build_ta_prompt(lang: str, asset: str, price: str, change: float, user_msg: str) -> str:
    """Structured TA prompt so responses are complete & trader-grade."""
    if lang == "en":
        return f"""
Instrument: {asset}
Last price: {price}
24h change: {change:+.2f}%

Task: Provide a concise, trader-grade technical analysis in English with bullet points:
- Overall bias (bullish/bearish/neutral) and why (trend, structure)
- 3–5 key support/resistance levels (numbers)
- Indicators snapshot: RSI (overbought/oversold/neutral), 20/50 EMA or 200 EMA context
- Possible trade plan ideas: entry zone(s), invalidation/stop, take-profits
- Risk notes specific to this chart (volatility, news times)
Close with: "Not financial advice."

User context: {user_msg}
"""
    else:
        return f"""
Хөрөнгө: {asset}
Сүүлийн үнэ: {price}
24 цагийн өөрчлөлт: {change:+.2f}%

Даалгавар: Монгол хэл дээр трейдерийн түвшний техникийн анализыг богино, жагсаалтаар өг:
- Үндсэн чиг хандлага (өсөх/унах/төв) ба шалтгаан (тренд, бүтэц)
- 3–5 гол дэмжлэг/эсэргүүцлийн түвшин (тоогоор)
- Индикаторын зураг: RSI (хэт их/хэт бага/төв), 20/50 эсвэл 200 EMA-ийн орчин
- Боломжит арилжааны санаа: оролтын бүс, хүчингүй болгох/стоп, зорилтот түвшин
- Эрсдэлийн анхааруулга (уялдаа, мэдээний цаг, савлагаа)
Төгсгөлд: "Санхүүгийн зөвлөгөө биш." гэж бич.

Хэрэглэгчийн хүсэлт: {user_msg}
"""

async def chat_with_openai(user_text: str, lang: str) -> str:
    try:
        res = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt_for_lang(lang)},
                {"role": "user", "content": user_text}
            ],
            max_completion_tokens=400  # gpt-5: use this param
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error: {e}" if lang == "en" else f"⚠️ Алдаа: {e}"

async def ta_with_openai(asset: str, price: str, change: float, user_msg: str, lang: str) -> str:
    try:
        prompt = build_ta_prompt(lang, asset, price, change, user_msg)
        res = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt_for_lang(lang)},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=450
        )
        return res.choices[0].message.content
    except Exception as e:
        return (f"⚠️ Error during analysis: {e}" if lang == "en"
                else f"⚠️ Анализын үеийн алдаа: {e}")

# ===== LANGUAGE COMMANDS ===== #
async def set_english(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    LANG[chat_id] = "en"
    await update.message.reply_text("Got it — I’ll reply in English from now on. ✅")

async def set_mongolian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    LANG[chat_id] = "mn"
    await update.message.reply_text("Ойлголоо — одооноос Монгол хэлээр хариулна. ✅")

def current_lang(update: Update) -> str:
    chat_id = update.effective_chat.id
    return LANG.get(chat_id, "mn")  # default to MN unless user switches

# ===== HANDLERS ===== #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Keep prior language if already chosen
    if chat_id not in LANG:
        LANG[chat_id] = "mn"
    welcome_mn = """
👋 Сайн уу? Би бол N2S — таны хиймэл оюунтай найз.

Жишээ:
• BTC/USDT шинжилгээ
• XAU/USD юу гэж байна?
• Swing trade яаж эхлэх вэ?

Хэл солих: /english  эсвэл  /mongolian
"""
    welcome_en = """
👋 Hey! I’m N2S — your AI trading buddy.

Examples:
• Analyze BTC/USDT
• What’s your view on XAU/USD?
• How to start swing trading?

Switch language: /english or /mongolian
"""
    if current_lang(update) == "en":
        await update.message.reply_text(welcome_en.strip())
    else:
        await update.message.reply_text(welcome_mn.strip())

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg = (update.message.text or "").strip()

    # Quick language auto-switch if user says "english"
    if msg.lower() in {"english", "eng", "pls english", "speak english"}:
        LANG[chat_id] = "en"
        await update.message.reply_text("Switched to English. ✅")
        return

    lang = current_lang(update)

    asset = extract_asset(msg)
    if asset:
        # Step 1: fetch price
        price, asset_type, change = get_universal_price(asset)

        # Step 2: short status then full TA
        if lang == "en":
            await update.message.reply_text("Analyzing… one sec.")
            header = f"{asset} — last price: {price} | 24h: {change:+.2f}%"
        else:
            await update.message.reply_text("Дүн шинжилж байна, түр хүлээгээрэй…")
            header = f"{asset} — одоогийн үнэ: {price} | 24ц: {change:+.2f}%"

        await update.message.reply_text(header)
        ta = await ta_with_openai(asset, price, change, msg, lang)
        await update.message.reply_text(ta)
    else:
        # Free chat
        reply = await chat_with_openai(msg, lang)
        await update.message.reply_text(reply)

# ===== MAIN ===== #
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("english", set_english))
    app.add_handler(CommandHandler("mongolian", set_mongolian))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))

    print("✅ N2S Bot ready.")
    app.run_polling()

if __name__ == "__main__":
    main()
