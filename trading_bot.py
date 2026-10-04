import requests
import pandas as pd
import numpy as np

# مفاتيح التيليجرام الخاصة بك
TELEGRAM_BOT_TOKEN = "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo"
TELEGRAM_CHAT_ID = "5620413191"

# إعدادات إدارة رأس المال والمخاطر
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

# دوال حساب المؤشرات الفنية يدوياً باستخدام Pandas و Numpy بدقة تامة
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_mfi(df, period=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(window=period).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(window=period).sum()
    mfr = pos_mf / neg_mf
    return 100 - (100 / (1 + mfr))

def calculate_ema(series, period=50):
    return series.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_adx(df, period=14):
    alpha = 1 / period
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()
    
    pos_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    neg_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    
    atr14 = calculate_atr(df, period)
    plus_di = 100 * pd.Series(pos_dm).ewm(alpha=alpha, adjust=False).mean() / atr14
    minus_di = 100 * pd.Series(neg_dm).ewm(alpha=alpha, adjust=False).mean() / atr14
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.ewm(alpha=alpha, adjust=False).mean()

def run_strict_bot():
    print("🛡️ Ultimate Strict Bot Scan (All Indicators Restored)...")
    
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
        "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT"
    ]
    
    for symbol in symbols:
        df_4h = get_binance_klines(symbol, "4h", limit=100)
        df_1h = get_binance_klines(symbol, "1h", limit=100)
        
        if df_4h is None or df_1h is None or len(df_4h) < 50 or len(df_1h) < 50:
            continue
            
        # حساب المؤشرات الفنية كاملة
        df_1h['rsi'] = calculate_rsi(df_1h['close'], 14)
        df_1h['mfi'] = calculate_mfi(df_1h, 14)
        df_1h['atr'] = calculate_atr(df_1h, 14)
        df_1h['adx'] = calculate_adx(df_1h, 14)
        df_1h['vol_sma'] = df_1h['volume'].rolling(window=20).mean()
        
        # Bollinger Bands
        df_1h['sma20'] = df_1h['close'].rolling(window=20).mean()
        df_1h['std20'] = df_1h['close'].rolling(window=20).std()
        df_1h['BBL'] = df_1h['sma20'] - (2 * df_1h['std20'])
        
        ema_4h = calculate_ema(df_4h['close'], 50)
        is_bullish_4h = df_4h['close'].iloc[-1] > ema_4h.iloc[-1]
        
        current_price = df_1h['close'].iloc[-1]
        current_rsi = df_1h['rsi'].iloc[-1]
        current_mfi = df_1h['mfi'].iloc[-1]
        current_adx = df_1h['adx'].iloc[-1]
        current_atr = df_1h['atr'].iloc[-1]
        current_vol = df_1h['volume'].iloc[-1]
        vol_sma = df_1h['vol_sma'].iloc[-1]
        bbl = df_1h['BBL'].iloc[-1]
        
        is_near_lower_band = current_price <= (bbl * 1.01)
        volume_confirmed = current_vol > vol_sma
        strong_trend = current_adx > 22
        
        # الشروط الاحترافية الكاملة للبوت الصارم
        if is_bullish_4h and strong_trend and (current_rsi < 38 or current_mfi < 35 or is_near_lower_band) and volume_confirmed:
            tp1 = current_price + (current_atr * 1.5)
            tp2 = current_price + (current_atr * 3.0)
            sl = current_price - (current_atr * 1.5)
            
            risk_amount = ACCOUNT_BALANCE * RISK_PERCENTAGE
            risk_per_unit = current_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
            position_value = position_size * current_price
            margin_required = position_value / LEVERAGE
            
            message = (
                f"🛡️ *Elite Strict Signal: {symbol}*\n"
                f"💰 Price: {current_price}\n"
                f"📈 Trend (4H): Bullish 🟢 | ADX: {current_adx:.1f}\n"
                f"🎯 Signal: STRONG BUY (Pro Filters)\n"
                f"🎯 TP1: {tp1:.3f}\n"
                f"🎯 TP2: {tp2:.3f}\n"
                f"🛑 SL: {sl:.3f}\n"
                f"⚖️ *Risk Mgt & Leverage ({LEVERAGE}x):*\n"
                f"• Suggested Qty: `{position_size:.4f}`\n"
                f"• Position Value: `${position_value:.2f}`\n"
                f"• Margin Required: `${margin_required:.2f}`\n"
                f"📊 RSI: {current_rsi:.1f} | MFI: {current_mfi:.1f} | ATR: {current_atr:.2f}"
            )
            send_telegram_message(message)
            
    print("🛡️ Strict Bot Scan Finished.")

if __name__ == "__main__":
    run_strict_bot()
