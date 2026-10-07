import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- إعداد نظام تسجيل الأخطاء (Error Logging) ---
logging.basicConfig(
    filename='bot_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# مفاتيح التيليجرام للبوت الصارم المطور
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0    
RISK_PERCENTAGE = 0.02    
LEVERAGE = 3    
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها من الرصيد كإجمالي هوامش مفتوحة (60%)

# --- ملفات السجلات والأرشيف الخاصة بالبوت الصارم ---
TRADE_FILE = "active_strict_trades.csv"
BALANCE_FILE = "strict_balance.txt"
CLOSED_FILE = "closed_strict_trades_history.csv"
HEARTBEAT_FILE = "last_strict_heartbeat.txt"

# خريطة الرموز للتوافق مع Coinbase API
COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD",
    "XRPUSDT": "XRP-USD",
    "ADAUSDT": "ADA-USD",
    "LINKUSDT": "LINK-USD",
    "AVAXUSDT": "AVAX-USD",
    "DOTUSDT": "DOT-USD",
    "NEARUSDT": "NEAR-USD",
    "MATICUSDT": "MATIC-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response: {response.status_code}")
    except Exception as e:
        error_msg = f"Telegram Error: {e}"
        print(error_msg)
        logging.error(error_msg)

def check_heartbeat():
    """إرسال نبضة قلب دورية (كل 24 ساعة) لتأكيد أن البوت الصارم يعمل بانتظام"""
    now = datetime.utcnow()
    send_hb = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "
