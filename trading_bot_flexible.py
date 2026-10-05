import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# مفاتيح التيليجرام للبوت المرن الجديد
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر للبوت المرن
INITIAL_BALANCE = 200.0    
RISK_PERCENTAGE = 0.02    
LEVERAGE = 3    

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

# دالة اختبار إرسال رسالة فورية للتأكد من عمل التيليجرام
def send_test_startup_message():
    test_msg = "⚡ *CoreTech Flexible Bot:* تم ربط التيليجرام بنجاح وبدء فحص السوق الآلي!"
    send_telegram_message(test_msg)

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

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

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
        entry_price = row['Entry']
        tp1 = row['TP1']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            if curr_price >= tp1:
                profit = (tp1 - entry_price) * qty
                current_balance += profit
                msg = f"🎯 *Flexible TP Reached! ({symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                send_telegram_message(msg)
                continue
            elif curr_price <= sl:
                loss = (entry_price - sl) * qty
                current_balance -= loss
                msg = f"🛑 *Flexible Stop Loss Hit! ({symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
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
    print("⚡ Flexible Bot Scan (Coinbase + Paper Trading Mode) Started...")
    
    # إرسال رسالة تجريبية فورية للتحقق من الاتصال بالتيليجرام عند بدء التشغيل
    send_test_startup_message()
    
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
        active_trades_df = pd.read_csv(trade_file)
    else:
        active_trades_df = pd.DataFrame(columns=['Symbol', 'Entry', 'TP1', 'TP2', 'SL', 'Qty'])

    for symbol, cb_product in COINBASE_PRODUCTS.items():
        df = get_coinbase_candles(cb_product, granularity=3600, limit=100)
        
        if df is None or len(df) < 50:
            continue
            
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['atr'] = calculate_atr(df, 14)
        df['ema_fast'] = calculate_ema(df['close'], 20)
        df['ema_slow'] = calculate_ema(df['close'], 50)
        
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        price_change_pct = ((current_price - prev_price) / prev_price) * 100
        
        current_prices_map[symbol] = current_price
        
        current_rsi = df['rsi'].iloc[-1] if not np.isnan(df['rsi'].iloc[-1]) else 50.0
        current_atr = df['atr'].iloc[-1] if not np.isnan(df['atr'].iloc[-1]) else (current_price * 0.01)
        ema_fast = df['ema_fast'].iloc[-1] if not np.isnan(df['ema_fast'].iloc[-1]) else current_price
        ema_slow = df['ema_slow'].iloc[-1] if not np.isnan(df['ema_slow'].iloc[-1]) else current_price
        
        is_uptrend = ema_fast > ema_slow
        is_pullback = (current_rsi < 50) and (current_rsi > 35)
        
        signal_status = "No Signal"
        if is_uptrend and is_pullback:
            signal_status = "FLEXIBLE BUY"
            tp1 = current_price + (current_atr * 1.2)
            tp2 = current_price + (current_atr * 2.5)
            sl = current_price - (current_atr * 1.2)
            
            risk_amount = account_balance * RISK_PERCENTAGE
            risk_per_unit = current_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.01
            position_value = position_size * current_price
            margin_required = position_value / LEVERAGE
            
            already_open = False
            if not active_trades_df.empty and symbol in active_trades_df['Symbol'].values:
                already_open = True

            if not already_open:
                new_trades.append({
                    'Symbol': symbol,
                    'Entry': current_price,
                    'TP1': tp1,
                    'TP2': tp2,
                    'SL': sl,
                    'Qty': position_size
                })

                message = (
                    f"⚡ *Flexible Paper Trade: {symbol}*\n"
                    f"🟢 *Position Opened (Testnet)*\n"
                    f"💰 Entry: `{current_price}` (Change: `{price_change_pct:+.2f}%`)\n"
                    f"🎯 TP1: `{tp1:.3f}` | TP2: `{tp2:.3f}`\n"
                    f"🛑 Stop Loss: `{sl:.3f}`\n"
                    f"⚖️ *Risk & Leverage ({LEVERAGE}x):*\n"
                    f"• Qty: `{position_size:.4f}`\n"
                    f"• Margin: `${margin_required:.2f}`\n"
                    f"💼 *Balance:* `${account_balance:.2f}` USDT\n"
                    f"📊 RSI: `{current_rsi:.1f}`"
                )
                send_telegram_message(message)
            
        scan_results.append({
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "Bot_Type": "Flexible",
            "Symbol": symbol,
            "Price": current_price,
            "Change_Pct": round(price_change_pct, 2),
            "RSI": round(current_rsi, 1),
            "Signal": signal_status
        })
        
    account_balance = manage_flexible_paper_trades(current_prices_map)

    if len(new_trades) > 0:
        new_df = pd.DataFrame(new_trades)
        updated_active = pd.concat([active_trades_df, new_df], ignore_index=True)
        updated_active.to_csv(trade_file, index=False)

    log_df = pd.DataFrame(scan_results)
    log_df.to_csv("bot_activity_log_flexible.csv", index=False)
    print(f"⚡ Flexible Bot Scan Finished. Current Balance: ${account_balance:.2f}")

if __name__ == "__main__":
    run_flexible_bot()
