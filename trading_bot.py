import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

RISK_PERCENTAGE = 0.02    
LEVERAGE = 3    

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        print(f"Telegram Response: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Telegram Error: {e}")

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
    "ADAUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT", "NEARUSDT"
]

def get_binance_klines(symbol, interval="1h", limit=120):
    """جلب بيانات الشموع بدقة من باينانس"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            print(f"Warning: No data returned for {symbol}, response: {data}")
            return None
            
        df_list = []
        for item in data:
            df_list.append({
                'timestamp': item[0],
                'open': float(item[1]),
                'high': float(item[2]),
                'low': float(item[3]),
                'close': float(item[4]),
                'volume': float(item[5])
            })
        return pd.DataFrame(df_list)
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

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
    print("🛡 Ultimate Strict Bot Scan (Optimized Mode)...")
    account_balance = 200.0
    scan_results = []
    
    for symbol in SYMBOLS:
        df_1h = get_binance_klines(symbol, "1h", limit=120)
        
        if df_1h is None or len(df_1h) < 20:
            print(f"Skipping {symbol} due to insufficient data length ({len(df_1h) if df_1h is not None else 0}).")
            continue
            
        df_1h['rsi'] = calculate_rsi(df_1h['close'], 14)
        df_1h['mfi'] = calculate_mfi(df_1h, 14)
        df_1h['atr'] = calculate_atr(df_1h, 14)
        df_1h['adx'] = calculate_adx(df_1h, 14)
        
        df_1h['sma20'] = df_1h['close'].rolling(window=20).mean()
        df_1h['std20'] = df_1h['close'].rolling(window=20).std()
        df_1h['BBL'] = df_1h['sma20'] - (2 * df_1h['std20'])
        
        ema_50 = calculate_ema(df_1h['close'], min(50, len(df_1h)))
        is_bullish = df_1h['close'].iloc[-1] > ema_50.iloc[-1]
        
        current_price = df_1h['close'].iloc[-1]
        prev_price = df_1h['close'].iloc[-2]
        price_change_pct = ((current_price - prev_price) / prev_price) * 100
        
        current_rsi = df_1h['rsi'].iloc[-1] if not np.isnan(df_1h['rsi'].iloc[-1]) else 50.0
        current_mfi = df_1h['mfi'].iloc[-1] if not np.isnan(df_1h['mfi'].iloc[-1]) else 50.0
        current_adx = df_1h['adx'].iloc[-1] if not np.isnan(df_1h['adx'].iloc[-1]) else 25.0
        current_atr = df_1h['atr'].iloc[-1] if not np.isnan(df_1h['atr'].iloc[-1]) else (current_price * 0.01)
        bbl = df_1h['BBL'].iloc[-1] if not np.isnan(df_1h['BBL'].iloc[-1]) else current_price * 0.98
        
        is_near_lower_band = current_price <= (bbl * 1.01)
        strong_trend = current_adx > 15  # تخفيف طفيف لضمان التقاط الاتجاهات بدقة
        
        signal_status = "No Signal"
        # شروط مرنة وقوية لالتقاط الفرص المتاحة
        if is_bullish and (current_rsi < 45 or current_mfi < 40 or is_near_lower_band):
            signal_status = "STRONG BUY"
            tp1 = current_price + (current_atr * 1.5)
            tp2 = current_price + (current_atr * 3.0)
            sl = current_price - (current_atr * 1.5)
            
            risk_amount = account_balance * RISK_PERCENTAGE
            risk_per_unit = current_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.01
            position_value = position_size * current_price
            margin_required = position_value / LEVERAGE
            
            message = (
                f"🛡️ *Elite Signal: {symbol}*\n"
                f"✅ *Market Scan Successful*\n"
                f"💰 Price: `{current_price}` (Change: `{price_change_pct:+.2f}%`)\n"
                f"📈 Trend: Bullish 🟢 | ADX: `{current_adx:.1f}`\n"
                f"🎯 Signal Type: *STRONG BUY*\n"
                f"🎯 TP1: `{tp1:.3f}` | TP2: `{tp2:.3f}`\n"
                f"🛑 Stop Loss (SL): `{sl:.3f}`\n"
                f"⚖️ *Risk & Leverage ({LEVERAGE}x):*\n"
                f"• Qty: `{position_size:.4f}`\n"
                f"• Position Value: `${position_value:.2f}`\n"
                f"• Margin Required: `${margin_required:.2f}`\n"
                f"💼 *Total Capital:* `${account_balance:.2f}` USDT\n"
                f"📊 RSI: `{current_rsi:.1f}` | MFI: `{current_mfi:.1f}`"
            )
            send_telegram_message(message)
            
        scan_results.append({
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "Symbol": symbol,
            "Price": current_price,
            "Change_Pct": round(price_change_pct, 2),
            "RSI": round(current_rsi, 1),
            "MFI": round(current_mfi, 1),
            "ADX": round(current_adx, 1),
            "Signal": signal_status
        })
        
    log_df = pd.DataFrame(scan_results)
    log_df.to_csv("bot_activity_log.csv", index=False)
    
    summary_msg = f"📊 *تقرير فحص السوق المحدث*\nتم فحص جميع العملات الرقمية بنجاح تام واستخراج النتائج، الرصيد الافتراضي: `{account_balance:.2f} USDT`."
    send_telegram_message(summary_msg)
    print("🛡️ Scan Finished Successfully.")

if __name__ == "__main__":
    run_strict_bot()
