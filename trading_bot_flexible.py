import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# مفاتيح التيليجرام للبوت المرن (Mean Reversion)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها من الرصيد كإجمالي هوامش مفتوحة (60%)

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
        response = requests.post(url, json=payload)
        print(f"Telegram Response: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

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
        print(f"Error fetching {product_id}: {e}")
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
    trade_file = "active_flexible_trades.csv"
    balance_file = "flexible_balance.txt"
    
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            current_balance = float(f.read().strip())
    else:
        current_balance = INITIAL_BALANCE

    if not os.path.exists(trade_file):
        return current_balance

    trades_df = pd.read_csv(trade_file)
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
                    continue
                elif curr_price <= sl:
                    loss = (entry_price - sl) * qty
                    current_balance -= loss
                    msg = f"🛑 *Flexible Stop Loss Hit! (LONG {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    continue
            
            elif side == "SHORT":
                if curr_price <= tp1:
                    profit = (entry_price - tp1) * qty
                    current_balance += profit
                    msg = f"🎯 *Flexible Mean-Reversion TP Reached! (SHORT {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    continue
                elif curr_price >= sl:
                    loss = (sl - entry_price) * qty
                    current_balance -= loss
                    msg = f"🛑 *Flexible Stop Loss Hit! (SHORT {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
                    send_telegram_message(msg)
                    continue
        
        updated_trades.append(row)

    if len(updated_trades) > 0:
        pd.DataFrame(updated_trades).to_csv(trade_file, index=False)
    else:
        pd.DataFrame(columns=trades_df.columns).to_csv(trade_file, index=False)

    with open(balance_file, "w") as f:
        f.write(str(current_balance))

    return current_balance

def run_flexible_bot():
    print("🔄 Flexible Bot (Mean Reversion Strategy) Scan Started...")
    
    balance_file = "flexible_balance.txt"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            account_balance = float(f.read().strip())
    else:
        account_balance = INITIAL_BALANCE

    current_prices_map = {}
    scan_results = []
    new_trades = []
    
    trade_file = "active_flexible_trades.csv"
    if os.path.exists(trade_file) and os.path.getsize(trade_file) > 0:
        active
