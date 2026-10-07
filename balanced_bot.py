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

# --- إعدادات تيليجرام ---
TELEGRAM_BOT_TOKEN = "8772493944:AAGb4Y1VuBLrCq0vfvnhue7oRW4hjf_LYJE"
TELEGRAM_CHAT_ID = "5620413191"

# --- إعدادات رأس المال وإدارة المخاطر ---
INITIAL_BALANCE = 200.0       
RISK_PERCENTAGE = 0.02        
LEVERAGE = 3                  
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها من الرصيد كإجمالي هوامش مفتوحة (60%)

# --- ملفات السجلات والأرشيف ---
TRADE_FILE = "active_balanced_trades.csv"
BALANCE_FILE = "balanced_balance.txt"
CLOSED_FILE = "closed_trades_history.csv"
HEARTBEAT_FILE = "last_heartbeat.txt"

# --- سلة العملات المعتمدة ---
COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "LINKUSDT": "LINK-USD",
    "ADAUSDT": "ADA-USD"
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
    """إرسال نبضة قلب دورية (كل 24 ساعة) لتأكيد أن البوت يعمل بانتظام"""
    now = datetime.utcnow()
    send_hb = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r") as f:
                last_time = datetime.fromisoformat(f.read().strip())
                if (now - last_time) >= timedelta(hours=24):
                    send_hb = True
        except Exception:
            send_hb = True
    else:
        send_hb = True

    if send_hb:
        send_telegram_message("💓 *Balanced Bot Heartbeat:* البوت يعمل بشكل سليم ومستقر ومتصل بنجاح.")
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(now.isoformat())
        except Exception as e:
            logging.error(f"Error writing heartbeat file: {e}")

def save_closed_trade(trade_data):
    """حفظ تفاصيل الصفقة المغلقة في أرشيف مستقل لتحليل الأداء"""
    file_exists = os.path.exists(CLOSED_FILE)
    df = pd.DataFrame([trade_data])
    try:
        df.to_csv(CLOSED_FILE, mode='a', header=not file_exists, index=False)
    except Exception as e:
        logging.error(f"Error saving closed trade: {e}")

def send_performance_summary(current_balance):
    """إرسال تقرير الأداء اليومي وملخص الإحصائيات (Win Rate)"""
    if not os.path.exists(CLOSED_FILE):
        return
    try:
        df = pd.read_csv(CLOSED_FILE)
        if df.empty:
            return
        total_trades = len(df)
        wins = len(df[df['Result'] == 'WIN'])
        losses = len(df[df['Result'] == 'LOSS'])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = df['PnL'].sum()

        msg = (
            f"📊 *تقرير الأداء الدوري - Balanced Bot*\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` USDT\n"
            f"📈 إجمالي الصفقات: `{total_trades}`\n"
            f"🏆 صفقات رابحة: `{wins}` | ❌ خاسرة: `{losses}`\n"
            f"🎯 نسبة النجاح (Win Rate): `{win_rate:.1f}%`\n"
            f"💵 صافي الأرباح/الخسائر: `${pnl_sign}{total_pnl:.2f}`"
        )
        # سيتم استخدام الإشارة لصافي الأرباح
        msg = msg.replace(f"${pnl_sign if 'pnl_sign' in locals() else ''}", f"${'+' if total_pnl >= 0 else ''}")
        send_telegram_message(msg)
    except Exception as e:
        logging.error(f"Error generating performance summary: {e}")

def get_coinbase_candles(product_id, granularity=3600, limit=100):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity={granularity}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
            
        df_list = []
        for item in reversed(data):
            df_list.append({
                'timestamp': item[0] * 1000,
                'low': float(item[1]),
                'high': float(item[2]),
                'open': float(item[3]),
                'close': float(item[4]),
                'volume': float(item[5])
            })
        df = pd.DataFrame(df_list)
        if len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)
        return df
    except Exception as e:
        error_msg = f"Error fetching {product_id}: {e}"
        print(error_msg)
        logging.error(error_msg)
        return None

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def detect_support_resistance_and_fvg(df):
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    support = df['low'].tail(15).min()
    resistance = df['high'].tail(15).max()
