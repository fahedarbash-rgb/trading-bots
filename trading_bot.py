import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logging.basicConfig(filename='bot_errors.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

INITIAL_BALANCE = 200.0    
TRADE_FILE = "active_strict_trades.csv"
BALANCE_FILE = "strict_balance.txt"
CLOSED_FILE = "closed_strict_trades_history.csv"
HEARTBEAT_FILE = "last_strict_heartbeat.txt"

COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD", "XRPUSDT": "XRP-USD", "ADAUSDT": "ADA-USD",
    "LINKUSDT": "LINK-USD", "AVAXUSDT": "AVAX-USD", "DOTUSDT": "DOT-USD",
    "NEARUSDT": "NEAR-USD", "MATICUSDT": "MATIC-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

def check_heartbeat():
    now = datetime.utcnow()
    send_hb = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r") as f:
                if (now - datetime.fromisoformat(f.read().strip())) >= timedelta(hours=24):
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

def get_coinbase_candles(product_id, granularity=3600, limit=100):
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity={granularity}"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        df_list = [{'timestamp': item[0] * 1000, 'low': float(item[1]), 'high': float(item[2]), 'open': float(item[3]), 'close': float(item[4]), 'volume': float(item[5])} for item in reversed(data)]
        df = pd.DataFrame(df_list)
        return df.tail(limit).reset_index(drop=True) if len(df) > limit else df
    except Exception as e:
        logging.error(f"Error fetching {product_id}: {e}")
        return None

def manage_strict_paper_trades(current_prices):
    current_balance = INITIAL_BALANCE
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE, "r") as f:
                current_balance = float(f.read().strip())
        except Exception:
            pass

    if not os.path.exists(TRADE_FILE):
        return current_balance

    try:
        trades_df = pd.read_csv(TRADE_FILE)
    except Exception:
        return current_balance

    if trades_df.empty:
        return current_balance

    for _, row in trades_df.iterrows():
        symbol = row['Symbol']
        entry_price = row['Entry']
        tp1 = row['TP1']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            if curr_price >= (entry_price + (tp1 - entry_price) * 0.5) and sl < entry_price:
                send_telegram_message(f"🔄 *Strict Trailing Stop Activated! ({symbol})*\nStop Loss moved to Entry Price.")

            if curr_price >= tp1:
                profit = (tp1 - entry_price) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Strict TP Reached! ({symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")

    return current_balance

if __name__ == "__main__":
    check_heartbeat()
    current_prices = {}
    for sym, coinbase_id in COINBASE_PRODUCTS.items():
        df = get_coinbase_candles(coinbase_id, granularity=3600, limit=5)
        if df is not None and not df.empty:
            current_prices[sym] = df.iloc[-1]['close']
    
    bal = manage_strict_paper_trades(current_prices)
    with open(BALANCE_FILE, "w") as f:
        f.write(str(bal))
