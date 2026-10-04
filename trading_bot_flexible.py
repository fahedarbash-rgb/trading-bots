import datetime
import requests
import pandas as pd
import pandas_ta as ta
import time

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
        url_15m = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
        response_15m = requests.get(url_15m, timeout=10)
        if response_15m.status_code != 200: 
            return None
        
        df = pd.DataFrame(response_15m.json(), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        current_price = df['close'].iloc[-1]
        
        # فلتر الاتجاه المرن على فريم الساعة (1H Trend Filter)
        url_1h = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50"
        resp_1h = requests.get(url_1h, timeout=10)
        trend_1h = "Neutral"
        if resp_1h.status_code == 200:
            df_1h = pd.DataFrame(resp_1h.json(), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'])
            df_1h['close'] = df_1h['close'].astype(float)
            ema_1h = ta.ema(df_1h['close'], length=30)
            trend_1h = "Bullish" if df_1h['close'].iloc[-1] > ema_1h.iloc[-1] else "Bearish"

        df['RSI'] = ta.rsi(df['close'], length=14)
        bollinger = ta.bbands(df['close'], length=20, std=2.0)
        
        bbu_col = [c for c in bollinger.columns if c.startswith('BBU')][0]
        bbl_col = [c for c in bollinger.columns if c.startswith('BBL')][0]
        
        df['BBU'] = bollinger[bbu_col]
        df['BBL'] = bollinger[bbl_col]
        df['EMA'] = ta.ema(df['close'], length=20)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['Vol_SMA'] = ta.sma(df['volume'], length=20)
        
        last_rsi = df['RSI'].iloc[-1]
        last_bbu = df['BBU'].iloc[-1]
        last_bbl = df['BBL'].iloc[-1]
        last_ema = df['EMA'].iloc[-1]
        last_atr = df['ATR'].iloc[-1]
        last_vol = df['volume'].iloc[-1]
        last_vol_sma = df['Vol_SMA'].iloc[-1]
        
        market_trend = "Bullish Trend" if current_price > last_ema else "Bearish Trend"
        is_volume_ok = last_vol > last_vol_sma * 0.8
        
        if last_rsi < 45 and current_price <= last_bbl and trend_1h == "Bullish" and is_volume_ok:
            signal_status = "🟢 FLEXIBLE LONG (1H Filtered & Volume OK)"
            tp1 = current_price + (last_atr * 1.2)
            tp2 = current_price + (last_atr * 2.5)
            sl = current_price - (last_atr * 1.2)
        elif last_rsi > 55 and current_price >= last_bbu and trend_1h == "Bearish" and is_volume_ok:
            signal_status = "🔴 FLEXIBLE SHORT (1H Filtered & Volume OK)"
            tp1 = current_price - (last_atr * 1.2)
            tp2 = current_price - (last_atr * 2.5)
            sl = current_price + (last_atr * 1.2)
        else:
            signal_status = "⏳ FLEXIBLE WAIT"
            tp1 = current_price * 1.015
            tp2 = current_price * 1.03
            sl = current_price * 0.985

        change_24h = ((current_price - df['close'].iloc[0]) / df['close'].iloc[0]) * 100
        return {"price": current_price, "change_24h": change_24h, "market_trend": market_trend, "trend_1h": trend_1h, "signal_status": signal_status, "tp1": tp1, "tp2": tp2, "sl": sl, "rsi": last_rsi, "atr": last_atr}
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}", flush=True)
        return None

print("⚡ Flexible Bot Scan Started...", flush=True)

for symbol in watchlist:
    print(f"Checking symbol: {symbol}", flush=True)
    res = analyze_flexible_market(symbol)
    if res:
        msg = f"⚡ **Flexible Signal**: {symbol}\n💰 Price: {res['price']:,.2f}\n📈 24h: {res['change_24h']:+.2f}%\n🌍 15m Trend: {res['market_trend']}\n🚀 1H Trend: {res['trend_1h']}\n🎯 Signal: {res['signal_status']}\n🎯 TP1: {res['tp1']:.3f}\n🎯 TP2: {res['tp2']:.3f}\n🛡️ SL: {res['sl']:.3f}\n📊 RSI: {res['rsi']:.1f} | ATR: {res['atr']:.2f}"
        send_telegram_message(msg)
    time.sleep(3)

print("⚡ Flexible Bot Scan Finished.", flush=True)
