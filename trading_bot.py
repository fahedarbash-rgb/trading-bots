import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# مفاتيح التيليجرام للبوت الصارم المطور
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
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
    trade_file = "active_strict_trades.csv"
    balance_file = "strict_balance.txt"
    
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
                send_telegram_message(msg)
                continue
            elif curr_price <= sl:
                loss = (entry_price - sl) * qty if sl < entry_price else 0
                current_balance -= loss
                msg = f"🛑 *Strict Stop Loss Hit! ({symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`"
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

def run_strict_bot():
    print("🛡️ Strict Bot Scan (Advanced with MACD & Trailing Stop) Started...")
    
    balance_file = "strict_balance.txt"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            account_balance = float(f.read().strip())
    else:
        account_balance = INITIAL_BALANCE

    current_prices_map = {}
    scan_results = []
    new_trades = []
    
    trade_file = "active_strict_trades.csv"
    if os.path.exists(trade_file) and os.path.getsize(trade_file) > 0:
        active_trades_df = pd.read_csv(trade_file)
    else:
        active_trades_df = pd.DataFrame(columns=['Symbol', 'Entry', 'TP1', 'TP2', 'SL', 'Qty'])

    for symbol, cb_product in COINBASE_PRODUCTS.items():
        df_1h = get_coinbase_candles(cb_product, granularity=3600, limit=100)
        df_4h = get_coinbase_candles(cb_product, granularity=14400, limit=50)
        
        if df_1h is None or len(df_1h) < 50 or df_4h is None or len(df_4h) < 20:
            continue
            
        # مؤشرات فريم الساعة
        df_1h['rsi'] = calculate_rsi(df_1h['close'], 14)
        df_1h['mfi'] = calculate_mfi(df_1h, 14)
        df_1h['adx'] = calculate_adx(df_1h, 14)
        df_1h['atr'] = calculate_atr(df_1h, 14)
        _, _, df_1h['bbl'] = calculate_bollinger_bands(df_1h['close'])
        df_1h['macd'], df_1h['macd_signal'], df_1h['macd_hist'] = calculate_macd(df_1h['close'])
        
        # مؤشر فريم 4 ساعات لتأكيد الاتجاه العام
        df_4h['ema_trend'] = calculate_ema(df_4h['close'], 50)
        
        current_price = df_1h['close'].iloc[-1]
        prev_price = df_1h['close'].iloc[-2]
        price_change_pct = ((current_price - prev_price) / prev_price) * 100
        current_prices_map[symbol] = current_price
        
        current_rsi = df_1h['rsi'].iloc[-1] if not np.isnan(df_1h['rsi'].iloc[-1]) else 50.0
        current_mfi = df_1h['mfi'].iloc[-1] if not np.isnan(df_1h['mfi'].iloc[-1]) else 50.0
        current_adx = df_1h['adx'].iloc[-1] if not np.isnan(df_1h['adx'].iloc[-1]) else 25.0
        current_atr = df_1h['atr'].iloc[-1] if not np.isnan(df_1h['atr'].iloc[-1]) else (current_price * 0.01)
        bbl_val = df_1h['bbl'].iloc[-1] if not np.isnan(df_1h['bbl'].iloc[-1]) else current_price
        macd_hist = df_1h['macd_hist'].iloc[-1] if not np.isnan(df_1h['macd_hist'].iloc[-1]) else 0
        
        is_bullish_4h = df_4h['close'].iloc[-1] > df_4h['ema_trend'].iloc[-1]
        is_strong_trend = current_adx > 20
        is_oversold_or_support = (current_rsi < 42) or (current_mfi < 40) or (current_price <= bbl_val * 1.01)
        is_macd_positive = macd_hist > 0  # تأكيد الزخم عبر MACD
        
        signal_status = "No Signal"
        if is_bullish_4h and is_strong_trend and is_oversold_or_support and is_macd_positive:
            signal_status = "STRONG BUY (Advanced)"
            tp1 = current_price + (current_atr * 1.5)
            tp2 = current_price + (current_atr * 3.0)
            sl = current_price - (current_atr * 1.5)
            
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
                    f"🛡️ *Advanced Strict Trade: {symbol}*\n"
                    f"🟢 *Position Opened (Strict Rules + MACD)*\n"
                    f"💰 Entry: `{current_price}` (Change: `{price_change_pct:+.2f}%`)\n"
                    f"🎯 TP1: `{tp1:.3f}` | TP2: `{tp2:.3f}`\n"
                    f"🛑 Initial Stop Loss: `{sl:.3f}`\n"
                    f"⚖ *Risk & Leverage ({LEVERAGE}x):*\n"
                    f"• Qty: `{position_size:.4f}`\n"
                    f"• Margin: `${margin_required:.2f}`\n"
                    f"💼 *Balance:* `${account_balance:.2f}` USDT\n"
                    f"📊 RSI: `{current_rsi:.1f}` | MFI: `{current_mfi:.1f}` | ADX: `{current_adx:.1f}`"
                )
                send_telegram_message(message)
            
        scan_results.append({
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "Bot_Type": "Strict_Advanced",
            "Symbol": symbol,
            "Price": current_price,
            "Change_Pct": round(price_change_pct, 2),
            "RSI": round(current_rsi, 1),
            "ADX": round(current_adx, 1),
            "Signal": signal_status
        })
        
    account_balance = manage_strict_paper_trades(current_prices_map)

    if len(new_trades) > 0:
        new_df = pd.DataFrame(new_trades)
        updated_active = pd.concat([active_trades_df, new_df], ignore_index=True)
        updated_active.to_csv(trade_file, index=False)

    log_df = pd.DataFrame(scan_results)
    log_df.to_csv("bot_activity_log_strict.csv", index=False)
    print(f"🛡️ Advanced Strict Bot Scan Finished. Current Balance: ${account_balance:.2f}")

if __name__ == "__main__":
    run_strict_bot()
