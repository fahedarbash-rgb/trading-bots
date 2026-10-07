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

# مفاتيح التيليجرام للبوت المرن (Mean Reversion)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها من الرصيد كإجمالي هوامش مفتوحة (60%)

# --- ملفات السجلات والأرشيف الخاصة بالبوت المرن ---
TRADE_FILE = "active_flexible_trades.csv"
BALANCE_FILE = "flexible_balance.txt"
CLOSED_FILE = "closed_flexible_trades_history.csv"
HEARTBEAT_FILE = "last_flexible_heartbeat.txt"

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
    """إرسال نبضة قلب دورية (كل 24 ساعة) لتأكيد أن البوت المرن يعمل بانتظام"""
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
        send_telegram_message("💓 *Flexible Bot Heartbeat:* البوت المرن يعمل بشكل سليم ومستقر ومتصل بنجاح.")
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

def calculate_bollinger_bands(series, period=20, std_dev=2):
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return middle, upper, lower

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def manage_flexible_paper_trades(current_prices):
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
        side = row['Side']
        entry_price = row['Entry']
        tp1 = row['TP1']
        tp2 = row['TP2']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            
            if side == "LONG":
                if curr_price >= tp1:
                    profit = (tp1 - entry_price) * qty
                    current_balance += profit
                    msg = f"🎯 *Flexible Mean-Reversion TP Reached! (LONG {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    save_closed_trade({
                        'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': tp1,
                        'Result': 'WIN', 'PnL': round(profit, 2), 'Reason': 'TP_Reached'
                    })
                    continue
                elif curr_price <= sl:
                    loss = (entry_price - sl) * qty
                    current_balance -= loss
                    msg = f"🛑 *Flexible Stop Loss Hit! (LONG {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    save_closed_trade({
                        'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': sl,
                        'Result': 'LOSS', 'PnL': round(-loss, 2), 'Reason': 'Stop_Loss'
                    })
                    continue
            
            elif side == "SHORT":
                if curr_price <= tp1:
                    profit = (entry_price - tp1) * qty
                    current_balance += profit
                    msg = f"🎯 *Flexible Mean-Reversion TP Reached! (SHORT {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    save_closed_trade({
                        'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': tp1,
                        'Result': 'WIN', 'PnL': round(profit, 2), 'Reason': 'TP_Reached'
                    })
                    continue
                elif curr_price >= sl:
                    loss = (sl - entry_price) * qty
                    current_balance -= loss
                    msg = f"🛑 *Flexible Stop Loss Hit! (SHORT {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    save_closed_trade({
                        'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': sl,
                        'Result': 'LOSS', 'PnL': round(-loss, 2), 'Reason': 'Stop_Loss'
                    })
                    continue
                    
        updated_trades.append(row)

    if updated_trades:
        pd.DataFrame(updated_trades).to_csv(TRADE_FILE, index=False)
    else:
        if os.path.exists(TRADE_FILE):
            os.remove(TRADE_FILE)
            
    return current_balance

if __name__ == "__main__":
    check_heartbeat()
    current_prices = {}
    for sym, coinbase_id in COINBASE_PRODUCTS.items():
        df = get_coinbase_candles(coinbase_id, granularity=3600, limit=5)
        if df is not None and not df.empty:
            current_prices[sym] = df.iloc[-1]['close']
            
    bal = manage_flexible_paper_trades(current_prices)
    with open(BALANCE_FILE, "w") as f:
        f.write(str(bal))
