import requests
import pandas as pd
import numpy as np
from datetime import datetime

# مفاتيح التيليجرام الخاصة بك
TELEGRAM_BOT_TOKEN = "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo"
TELEGRAM_CHAT_ID = "5620413191"

# إعدادات رأس المال والمخاطر
ACCOUNT_BALANCE = 200.0   
RISK_PERCENTAGE = 0.02    
LEVERAGE = 3              

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error: {e}")

def get_binance_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url)
        data = response.json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'not', 'tbav', 'tbqav', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
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

def run_flexible_bot():
    print("⚡ Flexible Bot Scan Started (Expanded Coins & Advanced Logs)...")
    
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
        "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
        "DOTUSDT", "NEARUSDT", "MATICUSDT"
    ]
    
    scan_results = []
    
    for symbol in symbols:
        df = get_binance_klines(symbol, "1h", limit=100)
        
        if df is None or len(df) < 50:
            continue
            
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['atr'] = calculate_atr(df, 14)
        df['ema_fast'] = calculate_ema(df['close'], 20)
        df['ema_slow'] = calculate_ema(df['close'], 50)
        
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        price_change_pct = ((current_price - prev_price) / prev_price) * 100
        
        current_rsi = df['rsi'].iloc[-1]
        current_atr = df['atr'].iloc[-1]
        ema_fast = df['ema_fast'].iloc[-1]
        ema_slow = df['ema_slow'].iloc[-1]
        
        is_uptrend = ema_fast > ema_slow
        is_pullback = current_rsi < 50 and current_rsi > 35
        
        signal_status = "No Signal"
        if is_uptrend and is_pullback:
            signal_status = "FLEXIBLE BUY"
            tp1 = current_price + (current_atr * 1.2)
            tp2 = current_price + (current_atr * 2.5)
            sl = current_price - (current_atr * 1.2)
            
            risk_amount = ACCOUNT_BALANCE * RISK_PERCENTAGE
            risk_per_unit = current_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
            position_value = position_size * current_price
            margin_required = position_value / LEVERAGE
            
            message = (
                f"⚡ *Flexible Signal: {symbol}*\n"
                f"💰 Price: `{current_price}` (Change: `{price_change_pct:+.2f}%`)\n"
                f"📈 Trend (1H): Fast Uptrend 🟢\n"
                f"🎯 Signal Type: *FLEXIBLE BUY*\n"
                f"🎯 TP1: `{tp1:.3f}` | TP2: `{tp2:.3f}`\n"
                f"🛑 Stop Loss (SL): `{sl:.3f}`\n"
                f"⚖️ *Risk & Leverage ({LEVERAGE}x):*\n"
                f"• Suggested Qty: `{position_size:.4f}`\n"
                f"• Position Value: `${position_value:.2f}`\n"
                f"• Margin Required: `${margin_required:.2f}`\n"
                f"📊 RSI: `{current_rsi:.1f}` | ATR: `{current_atr:.2f}`"
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
        
    log_df = pd.DataFrame(scan_results)
    log_df.to_csv("bot_activity_log_flexible.csv", index=False)
    print("⚡ Flexible Bot Scan Finished & Log Saved.")

if __name__ == "__main__":
    run_flexible_bot()
