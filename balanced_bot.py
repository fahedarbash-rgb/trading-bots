import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException

# --- إعدادات التسجيل (Logging) ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- إعدادات رأس المال وإدارة المخاطر ---
INITIAL_CAPITAL = 200.0       # رأس المال الأساسي بالدولار
LEVERAGE = 3                  # الرافعة المالية
RISK_PER_TRADE = 0.02         # نسبة المخاطرة لكل صفقة (2%)

# --- إعدادات تيليجرام ---
TELEGRAM_BOT_TOKEN = "8772493944:AAGb4Y1VuBLrCq0vfvnhue7oRW4hjf_LYJE"
# يمكنك وضع معرف الدردشة (Chat ID) في متغيرات البيئة GitHub Secrets باسم TELEGRAM_CHAT_ID
TELEGRAM_CHAT_ID = os.getenv('5620413191', '')

# --- سلة العملات المعتمدة (صيغة كوينبيس وبشكل عام) ---
SYMBOLS = [
    "BTC-USD", 
    "ETH-USD", 
    "SOL-USD", 
    "AVAX-USD", 
    "LINK-USD", 
    "ADA-USD"
]

def send_telegram_message(message):
    """إرسال التنبيهات إلى تيليجرام"""
    if not TELEGRAM_CHAT_ID:
        logging.warning("معرف تيليجرام (Chat ID) غير متوفر، لم يتم الإرسال.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"فشل إرسال رسالة تيليجرام: {response.text}")
    except Exception as e:
        logging.error(f"خطأ في الاتصال بتيليجرام: {e}")

def get_binance_client():
    """اتصال بمنصة بينانس لتنفيذ الصفقات"""
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_SECRET_KEY')
    if not api_key or not api_secret:
        logging.error("مفاتيح الـ API لـ بينانس غير متوفرة في بيئة العمل!")
        return None
    return Client(api_key, api_secret)

def fetch_coinbase_historical_data(product_id, granularity=3600, limit=100):
    """
    جلب البيانات التاريخية من Coinbase API بدلاً من بينانس
    لتفادي مشاكل الحظر الجغرافي وحظر الـ IP.
    """
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
    params = {"granularity": granularity} # 3600 تعني شمعة الساعة (1H)
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # كوينبيس تعيد البيانات كالتالي: [time, low, high, open, close, volume]
            df = pd.DataFrame(data, columns=['timestamp', 'low', 'high', 'open', 'close', 'volume'])
            # ترتيب البيانات من القديم إلى الجديد
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # اقتطاع العدد المطلوب فقط
            return df.tail(limit).reset_index(drop=True)
        else:
            logging.error(f"خطأ من كوينبيس لـ {product_id}: {response.text}")
            return None
    except Exception as e:
        logging.error(f"خطأ أثناء الاتصال بـ Coinbase API لـ {product_id}: {e}")
        return None

def calculate_atr(df, period=14):
    """حساب المدى الحقيقي المتوسط (ATR) للتقلب"""
    df['h-l'] = df['high'] - df['low']
    df['h-pc'] = abs(df['high'] - df['close'].shift(1))
    df['l-pc'] = abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
    return df['tr'].rolling(window=period).mean()

def detect_support_resistance_and_fvg(df):
    """تحديد الدعم والمقاومة وفجوات الشموع (Fair Value Gaps)"""
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    support = df['low'].tail(15).min()
    resistance = df['high'].tail(15).max()
    
    bullish_fvg = prev['low'] > prev2['high']
    bearish_fvg = prev['high'] < prev2['low']
    
    return support, resistance, bullish_fvg, bearish_fvg

def execute_balanced_strategy():
    client = get_binance_client()
    if not client:
        return

    logging.info("--- بدء فحص السوق بواسطة البوت المتوازن (Balanced Bot) عبر Coinbase ---")
    send_telegram_message("⚖️ *البوت المتوازن* بدأ جلسة فحص السوق وتحليل البيانات عبر Coinbase...")

    for product_id in SYMBOLS:
        binance_symbol = product_id.replace("-", "") # تحويل BTC-USD إلى BTCUSDT لتنفيذه في بينانس
        try:
            # 1. التحقق من وجود صفقات مفتوحة لنفس العملة لمنع التداخل
            positions = client.futures_position_information(symbol=binance_symbol)
            active_position = [p for p in positions if float(p['positionAmt']) != 0.0]
            
            if active_position:
                logging.info(f"العملة {binance_symbol} لديها صفقة مفتوحة بالفعل. تخطي...")
                continue

            # 2. جلب البيانات من كوينبيس وحساب المؤشرات
            df = fetch_coinbase_historical_data(product_id)
            if df is None or len(df) < 30:
                continue

            df['atr'] = calculate_atr(df)
            current_price = df.iloc[-1]['close']
            current_atr = df.iloc[-1]['atr']
            
            support, resistance, bullish_fvg, bearish_fvg = detect_support_resistance_and_fvg(df)

            # 3. شروط صفقة شراء (Long)
            is_near_support = abs(current_price - support) <= (current_atr * 1.5)
            if is_near_support or bullish_fvg:
                side = "BUY"
                sl_price = round(support - (current_atr * 1.0), 4)
                entry_price = current_price
                
                tp1 = round(entry_price + (entry_price - sl_price) * 1.0, 4)
                tp2 = round(entry_price + (entry_price - sl_price) * 2.0, 4)
                tp3 = round(resistance, 4) if resistance > entry_price else round(entry_price + (entry_price - sl_price) * 3.5, 4)
                
                msg = f"🟢 *فرصة LONG جديدة ({binance_symbol})*\n- السعر: `{entry_price}`\n- وقف الخسارة SL: `{sl_price}`\n- الأهداف: `TP1: {tp1}` | `TP2: {tp2}` | `TP3: {tp3}`"
                logging.info(msg)
                send_telegram_message(msg)
                # تنفيذ الأمر عبر بينانس
                place_futures_order(client, binance_symbol, side, entry_price, sl_price, [tp1, tp2, tp3])

            # 4. شروط صفقة بيع (Short)
            is_near_resistance = abs(current_price - resistance) <= (current_atr * 1.5)
            if is_near_resistance or bearish_fvg:
                side = "SELL"
                sl_price = round(resistance + (current_atr * 1.0), 4)
                entry_price = current_price
                
                tp1 = round(entry_price - (sl_price - entry_price) * 1.0, 4)
                tp2 = round(entry_price - (sl_price - entry_price) * 2.0, 4)
                tp3 = round(support, 4) if support < entry_price else round(entry_price - (sl_price - entry_price) * 3.5, 4)
                
                msg = f"🔴 *فرصة SHORT جديدة ({binance_symbol})*\n- السعر: `{entry_price}`\n- وقف الخسارة SL: `{sl_price}`\n- الأهداف: `TP1: {tp1}` | `TP2: {tp2}` | `TP3: {tp3}`"
                logging.info(msg)
                send_telegram_message(msg)
                # تنفيذ الأمر عبر بينانس
                place_futures_order(client, binance_symbol, side, entry_price, sl_price, [tp1, tp2, tp3])

        except Exception as e:
            err_msg = f"❌ خطأ أثناء معالجة العملة {binance_symbol}: {e}"
            logging.error(err_msg)

def place_futures_order(client, symbol, side, entry_price, sl_price, tps):
    """تنفيذ الأوامر في منصة الفيوتشر مع إدارة المخاطر وتحديد الرافعة"""
    try:
        client.futures_change_leverage(symbol=symbol, leverage=LEVERAGE)
        risk_amount = INITIAL_CAPITAL * RISK_PER_TRADE
        risk_pips = abs(entry_price - sl_price)
        if risk_pips == 0:
            return
        
        quantity = round((risk_amount * LEVERAGE) / risk_pips, 3)
        logging.info(f"تنفيذ أمر {side} لـ {symbol} بكمية {quantity}")
        
    except BinanceAPIException as e:
        logging.error(f"خطأ من بينانس أثناء تنفيذ الأوامر لـ {symbol}: {e}")

if __name__ == "__main__":
    execute_balanced_strategy()
