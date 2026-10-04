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

def run_strict_bot():
    print("🛡️ Ultimate Strict Bot Scan (EMA + BB + RSI + Vol + ATR + ADX + MFI)...")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"]
    
    for symbol in symbols:
        df_4h = get_binance_klines(symbol, "4h", limit=100)
        df_1h = get_binance_klines(symbol, "1h", limit=100)
        
        if df_4h is None or df_1h is None or len(df_4h) < 50 or len(df_1h) < 50:
            continue
            
        df_1h['rsi'] = ta.rsi(df_1h['close'], length=14)
        df_1h['mfi'] = ta.mfi(df_1h['high'], df_1h['low'], df_1h['close'], df_1h['volume'], length=14)
        df_1h['atr'] = ta.atr(df_1h['high'], df_1h['low'], df_1h['close'], length=14)
        df_1h['vol_sma'] = ta.sma(df_1h['volume'], length=20)
        
        adx_df = ta.adx(df_1h['high'], df_1h['low'], df_1h['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df_1h['adx'] = adx_df.iloc[:, 0]
        else:
            df_1h['adx'] = 0

        bbands = ta.bbands(df_1h['close'], length=20, std=2)
        if bbands is not None and not bbands.empty:
            df_1h['BBL'] = bbands.iloc[:, 0]
        
        ema_4h = ta.ema(df_4h['close'], length=50)
        is_bullish_4h = df_4h['close'].iloc[-1] > ema_4h.iloc[-1]
        
        current_price = df_1h['close'].iloc[-1]
        current_rsi = df_1h['rsi'].iloc[-1]
        current_mfi = df_1h['mfi'].iloc[-1]
        current_adx = df_1h['adx'].iloc[-1]
        current_atr = df_1h['atr'].iloc[-1]
        current_vol = df_1h['volume'].iloc[-1]
        vol_sma = df_1h['vol_sma'].iloc[-1]
        bbl = df_1h['BBL'].iloc[-1] if 'BBL' in df_1h else current_price
        
        is_near_lower_band = current_price <= (bbl * 1.01)
        volume_confirmed = current_vol > vol_sma
        strong_trend = current_adx > 22
        
        if is_bullish_4h and strong_trend and (current_rsi < 38 or current_mfi < 35 or is_near_lower_band) and volume_confirmed:
            tp1 = current_price + (current_atr * 1.5)
            tp2 = current_price + (current_atr * 3.0)
            sl = current_price - (current_atr * 1.5)
            
            message = (
                f"🛡️ *Elite Strict Signal: {symbol}*\n"
                f"💰 Price: {current_price}\n"
                f"📈 Trend (4H): Bullish 🟢 | ADX: {current_adx:.1f}\n"
                f"🎯 Signal: STRONG BUY (Pro Filters)\n"
                f"🎯 TP1: {tp1:.3f}\n"
                f"🎯 TP2: {tp2:.3f}\n"
                f"🛑 SL: {sl:.3f}\n"
                f"📊 RSI: {current_rsi:.1f} | MFI: {current_mfi:.1f} | ATR: {current_atr:.2f}"
            )
            send_telegram_message(message)
            
    print("🛡️ Strict Bot Scan Finished.")

if __name__ == "__main__":
    run_strict_bot()
