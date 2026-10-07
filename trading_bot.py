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
            with open(HEARTBEAT_FILE, "r") as f:
                last_time = datetime.fromisoformat(f.read().strip())
                if (now - last_time) >= timedelta(hours=24):
                    send_hb = True
        except Exception:
            send_hb = True
    else:
        send_hb = True

    if send_hb:
        send_telegram_message("💓 *Strict Bot Heartbeat:* البوت الصارم يعمل بشكل سليم ومستقر ومتصل بنجاح.")
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

        sign_str = '+' if total_pnl >= 0 else ''
        msg = (
            f"📊 *تقرير الأداء الدوري - Strict Bot*\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` USDT\n"
            f"📈 إجمالي الصفقات: `{total_trades}`\n"
            f"🏆 صفقات رابحة: `{wins}` | ❌ خاسرة: `{losses}`\n"
            f"🎯 نسبة النجاح (Win Rate): `{win_rate:.1f}%`\n"
            f"💵 صافي الأرباح/الخسائر: `${sign_str}{total_pnl:.2f}`"
        )
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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = calculate_ema(series, fast)
    exp2 = calculate_ema(series, slow)
    macd_line = exp1 - exp2
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_mfi(df, period=14):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    delta = typical_price.diff()
    pos_flow = money_flow.where(delta > 0, 0).rolling(window=period).sum()
    neg_flow = money_flow.where(delta < 0, 0).rolling(window=period).sum()
    mfr = pos_flow / neg_flow
    return 100 - (100 / (1 + mfr))

def calculate_adx(df, period=14):
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    tr1 = df['high'] - df['low']
    tr2 = np.abs(df['high'] - df['close'].shift())
    tr3 = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.rolling(window=period).mean()

def calculate_bollinger_bands(series, period=20, std_dev=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def manage_strict_paper_trades(current_prices):
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE, "r") as f:
                current_balance = float(f.read().strip())
        except Exception:
            current_balance = INITIAL_BALANCE
    else:
        current_balance = INITIAL_BALANCE

    if not os.path.exists(TRADE_FILE):
        return current_balance

    try:
        trades_df = pd.read_csv(TRADE_FILE)
    except Exception as e:
        logging.error(f"Error reading {TRADE_FILE}: {e}")
        return current_balance

    if trades_df.empty:
        return current_balance

    updated_trades = []
    for index, row in trades_df.iterrows():
        symbol = row['Symbol']
        entry_price = row['Entry']
        tp1 = row['TP1']
        tp2 = row['TP2']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            
            # نظام وقف الخسارة المتحرك (Trailing Stop) للبوت الصارم
            if curr_price >= (entry_price + (tp1 - entry_price) * 0.5) and sl < entry_price:
                sl = entry_price
                row['SL'] = sl
                send_telegram_message(f"🔄 *Strict Trailing Stop Activated! ({symbol})*\nStop Loss moved to Entry Price: `{sl:.3f}`")

            if curr_price >= tp1:
                profit = (tp1 - entry_price) * qty
                current_balance += profit
                msg = f"🎯 *Strict TP Reached! ({symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                send_telegram_message(msg
