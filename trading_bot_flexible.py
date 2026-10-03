import datetime
import time
import requests
import numpy as np
import pandas as pd
import pandas_ta as ta

TELEGRAM_BOT_TOKEN = "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo"
TELEGRAM_CHAT_ID = "5620413191"

watchlist = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}", flush=True)

def analyze_flexible_market(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
        response = requests.get(url, timeout=10)
        if response.status_code != 200: 
            print(f"Fails to fetch {symbol} - Status: {response.status_code}", flush=True)
            return None
        
        df = pd.DataFrame(response.json(), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        current_price = df['close'].iloc[-1]
        
        df['RSI'] = ta.rsi(df['close'], length=14)
        bollinger = ta.bbands(df['close'], length=20, std=2.0)
        
        bbu_col = [c for c in bollinger.columns if c.startswith('BBU')][0]
        bbl_col = [c for c in bollinger.columns if c.startswith('BBL')][0]
        
        df['BBU'] = bollinger[bbu_col]
        df['BBL'] = bollinger[bbl_col]
        df['EMA'] = ta.ema(df['close'], length=20)  # المؤشر المرن EMA 20
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        last_rsi = df['RSI'].iloc[-1]
        last_bbu = df['BBU'].iloc[-1]
        last_bbl = df['BBL'].iloc[-1]
        last_ema = df['EMA'].iloc[-1]
        last_atr = df['ATR'].iloc[-1]
        
        market_trend = "Bullish Trend" if current_price > last_ema else "Bearish Trend"
        
        # شروط مرنة وأوسع قليلاً
        if last_rsi < 45 and current_price <= last_bbl:
            signal_status = "🟢 FLEXIBLE LONG"
            tp1 = current_price + (last_atr * 1.2)
            tp2 = current_price + (last_atr * 2.5)
            sl = current_price - (last_atr * 1.2)
        elif last_rsi > 55 and current_price >= last_bbu:
            signal_status = "🔴 FLEXIBLE SHORT"
            tp1 = current_price - (last_atr * 1.2)
            tp2 = current_price - (last_atr * 2.5)
            sl = current_price + (last_atr * 1.2)
        else:
            signal_status = "⏳ FLEXIBLE WAIT"
            tp1 = current_price * 1.015
            tp2 = current_price * 1.03
            sl = current_price * 0.985

        change_24h = ((current_price - df['close'].iloc[0]) / df['close'].iloc[0]) * 100
        return {"price": current_price, "change_24h": change_24h, "market_trend": market_trend, "signal_status": signal_status, "tp1": tp1, "tp2": tp2, "sl": sl, "rsi": last_rsi, "atr": last_atr}
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}", flush=True)
        return None

print("⚡ Flexible Bot Started and Running...", flush=True)
send_telegram_message("⚡ **Flexible Bot Started** (RSI, EMA 20, BOLL, ATR)")

while True:
    try:
        current_hour = datetime.datetime.now().hour
        print(f"Current Hour: {current_hour}", flush=True)
        
        if current_hour % 2 != 0:  # الساعات الفردية فقط
            print("⚡ Flexible Bot started scanning coins...", flush=True)
            for symbol in watchlist:
                print(f"Checking symbol: {symbol}", flush=True)
                res = analyze_flexible_market(symbol)
                if res:
                    print(f"Checked successfully {symbol} - Price: {res['price']:,.2f} - Status: {res['signal_status']}", flush=True)
                    msg = f"⚡ **Flexible Signal**: {symbol}\n💰 Price: {res['price']:,.2f}\n📈 24h: {res['change_24h']:+.2f}%\n🌍 Market: {res['market_trend']}\n🎯 Signal: {res['signal_status']}\n🎯 TP1: {res['tp1']:.3f}\n🎯 TP2: {res['tp2']:.3f}\n🛡️ SL: {res['sl']:.3f}\n📊 RSI: {res['rsi']:.1f} | ATR: {res['atr']:.2f}"
                    send_telegram_message(msg)
                time.sleep(4)
            print("Finished current cycle, waiting for next round...", flush=True)
            time.sleep(3000)
        else:
            print("Current hour is even, Flexible Bot is waiting...", flush=True)
            time.sleep(300)
    except Exception as e:
        print(f"General Error in main loop: {e}", flush=True)
        time.sleep(60)