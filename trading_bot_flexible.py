import requests
import pandas as pd
import pandas_ta as ta

# مفاتيح التيليجرام الخاصة بك مباشرة
TELEGRAM_BOT_TOKEN = "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo"
TELEGRAM_CHAT_ID = "5620413191"

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

def run_flexible_bot():
    print("⚡ Flexible Bot Scan Started (Fast 1H Trend & Momentum)...")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"]
    
    for symbol in symbols:
        df = get_binance_klines(symbol, "1h", limit=100)
        
        if df is None or len(df) < 50:
            continue
            
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ema_fast'] = ta.ema(df['close'], length=20)
        df['ema_slow'] = ta.ema(df['close'], length=50)
        
        current_price = df['close'].iloc[-1]
        current_rsi = df['rsi'].iloc[-1]
        current_atr = df['atr'].iloc[-1]
        ema_fast = df['ema_fast'].iloc[-1]
        ema_slow = df['ema_slow'].iloc[-1]
        
        is_uptrend = ema_fast > ema_slow
        is_pullback = current_rsi < 50 and current_rsi > 35
        
        if is_uptrend and is_pullback:
            tp1 = current_price + (current_atr * 1.2)
            tp2 = current_price + (current_atr * 2.5)
            sl = current_price - (current_atr * 1.2)
            
            message = (
                f"⚡ *Flexible Signal: {symbol}*\n"
                f"💰 Price: {current_price}\n"
                f"📈 Trend (1H): Fast Bullish 🟢\n"
                f"🎯 Signal: FLEXIBLE BUY (Fast Momentum)\n"
                f"🎯 TP1: {tp1:.3f}\n"
                f"🎯 TP2: {tp2:.3f}\n"
                f"🛑 SL: {sl:.3f}\n"
                f"📊 RSI: {current_rsi:.1f} | ATR: {current_atr:.2f}"
            )
            send_telegram_message(message)
            
    print("⚡ Flexible Bot Scan Finished.")

if __name__ == "__main__":
    run_flexible_bot()
