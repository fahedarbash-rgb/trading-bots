import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# مفاتيح التيليجرام
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات إدارة رأس المال والمخاطر الافتراضية
INITIAL_BALANCE = 200.0    
RISK_PERCENTAGE = 0.02    
LEVERAGE = 3    

# خريطة الرموز لربط عملات المنصات بأسواق Coinbase
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
        print(f"Telegram Error: {e}")

def get_coinbase_candles(product_id, granularity=3600, limit=100):
    """
    جلب بيانات الشموع من Coinbase بدعم الفريمات 
    granularity: 3600 (1h), 14400 (4h)
    """
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity={granularity}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
            
        df_list = []
        # Coinbase format: [ time, low, high, open, close, volume ]
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

def manage_paper_trades(current_prices):
    """إدارة الصفقات التجريبية المفتوحة (تتبع TP و SL)"""
    trade_file = "active_paper_trades.csv"
    balance_file = "account_balance.txt"
    
    # قراءة الرصيد الحالي أو إنشاء الرصيد الأولي
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
            # فحص ضرب الهدف (TP1)
            if curr_price >= tp1:
                profit = (tp1 - entry_price) * qty
                current_balance += profit
                msg = f"🎯 *Paper Trade TP Reached! ({symbol})*\nClosed in profit: `+${profit:.2f}`\nNew Balance: `${current_balance:.2f}`"
                send_telegram_message(msg)
                continue
            # فحص ضرب وقف الخسارة (SL)
            elif curr_price <= sl:
                loss = (entry_price - sl) * qty
                current_balance -= loss
                msg = f"🛑 *Paper Trade Stop Loss Hit! ({symbol})*\nClosed with loss: `-${loss:.2f}`\nNew Balance: `${current_balance:.2f}`"
                send_telegram_message(msg)
                continue
        
        updated_trades.append(row)

    # تحديث ملف الصفقات والرصيد
    if len(updated_trades) > 0:
        pd.DataFrame(updated_trades).to_csv(trade_file, index=False)
    else:
        pd.DataFrame(columns=trades_df.columns).to_csv(trade_file, index=False)

    with open(balance_file, "w") as f:
        f.write(str(current_balance))

    return current_balance

def run_strict_bot():
    print("🛡️ Ultimate Strict Bot (Coinbase + Paper Trading Mode) Started...")
    
    balance_file = "account_balance.txt"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            account_balance = float(f.read().strip())
    else:
        account_balance = INITIAL_BALANCE

    current_prices_map = {}
    scan_results = []
    new_trades = []
    
    if os.path.exists("active_paper_trades.csv") and os.path.getsize("active_paper_trades.csv") > 0:
        active_trades_df = pd.read_csv("active_paper_trades.csv")
    else:
        active_trades_df = pd.DataFrame(columns=['Symbol', 'Entry', 'TP1', 'TP2', 'SL', 'Qty'])

    for symbol, cb_product in COINBASE_PRODUCTS.items():
        # جلب فريم 4 ساعات (14400 ثانية) وفريم الساعة (3600 ثانية)
        df_4h = get_coinbase_candles(cb_product, granularity=14400, limit=100)
        df_1h = get_coinbase_candles(cb_product, granularity=3600, limit=100)
        
        if df_4h is None or df_1h is None or len(df_4h) < 30 or len(df_1h) < 30:
            continue
            
        df_1h['rsi'] = calculate_rsi(df_1h['close'], 14)
        df_1h['mfi'] = calculate_mfi(df_1h, 14)
        df_1h['atr'] = calculate_atr(df_1h, 14)
        df_1h['adx'] = calculate_adx(df_1h, 14)
        df_1h['vol_sma'] = df_1h['volume'].rolling(window=20).mean()
        
        df_1h['sma20'] = df_1h['close'].rolling(window=20).mean()
        df_1h['std20'] = df_1h['close'].rolling(window=20).std()
        df_1h['BBL'] = df_1h['sma20'] - (2 * df_1h['std20'])
        
        ema_4h = calculate_ema(df_4h['close'], min(50, len(df_4h)))
        is_bullish_4h = df_4h['close'].iloc[-1] > ema_4h.iloc[-1]
        
        current_price = df_1h['close'].iloc[-1]
        prev_price = df_1h['close'].iloc[-2]
        price_change_pct = ((current_price - prev_price) / prev_price) * 100
        
        current_prices_map[symbol] = current_price
        
        current_rsi = df_1h['rsi'].iloc[-1] if not np.isnan(df_1h['rsi'].iloc[-1]) else 50.0
        current_mfi = df_1h['mfi'].iloc[-1] if not np.isnan(df_1h['mfi'].iloc[-1]) else 50.0
        current_adx = df_1h['adx'].iloc[-1] if not np.isnan(df_1h['adx'].iloc[-1]) else 25.0
        current_atr = df_1h['atr'].iloc[-1] if not np.isnan(df_1h['atr'].iloc[-1]) else (current_price * 0.01)
        current_vol = df_1h['volume'].iloc[-1]
        vol_sma = df_1h['vol_sma'].iloc[-1] if not np.isnan(df_1h['vol_sma'].iloc[-1]) else current_vol
        bbl = df_1h['BBL'].iloc[-1] if not np.isnan(df_1h['BBL'].iloc[-1]) else current_price * 0.98
        
        is_near_lower_band = current_price <= (bbl * 1.01)
        volume_confirmed = current_vol > vol_sma
        strong_trend = current_adx > 20
        
        signal_status = "No Signal"
        # شروط الإستراتيجية الصارمة
        if is_bullish_4h and strong_trend and (current_rsi < 42 or current_mfi < 40 or is_near_lower_band):
            signal_status = "STRONG BUY"
            tp1 = current_price + (current_atr * 1.5)
            tp2 = current_price + (current_atr * 3.0)
            sl = current_price - (current_atr * 1.5)
            
            risk_amount = account_balance * RISK_PERCENTAGE
            risk_per_unit = current_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.01
            position_value = position_size * current_price
            margin_required = position_value / LEVERAGE
            
            # التحقق مما إذا كانت الصفقة مفتوحة مسبقاً لتجنب التكرار
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
                    f"🛡️ *Paper Trade Execution: {symbol}*\n"
                    f"🟢 *New Position Opened (Testnet)*\n"
                    f"💰 Entry Price: `{current_price}` (Change: `{price_change_pct:+.2f}%`)\n"
                    f"🎯 TP1: `{tp1:.3f}` | TP2: `{tp2:.3f}`\n"
                    f"🛑 Stop Loss: `{sl:.3f}`\n"
                    f"⚖️️ *Risk & Leverage ({LEVERAGE}x):*\n"
                    f"• Qty: `{position_size:.4f}`\n"
                    f"• Margin Required: `${margin_required:.2f}`\n"
                    f"💼 *Virtual Balance:* `${account_balance:.2f}` USDT\n"
                    f"📊 RSI: `{current_rsi:.1f}` | MFI: `{current_mfi:.1f}` | ADX: `{current_adx:.1f}`"
                )
                send_telegram_message(message)
            
        scan_results.append({
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "Symbol": symbol,
            "Price": current_price,
            "Change_Pct": round(price_change_pct, 2),
            "RSI": round(current_rsi, 1),
            "Signal": signal_signal if 'signal_signal' in locals() else signal_status
        })
        
    # إدارة الصفقات النشطة ومتابعة الأهداف
    account_balance = manage_paper_trades(current_prices_map)

    # حفظ الصفقات الجديدة إن وجدت
    if len(new_trades) > 0:
        new_df = pd.DataFrame(new_trades)
        updated_active = pd.concat([active_trades_df, new_df], ignore_index=True)
        updated_active.to_csv("active_paper_trades.csv", index=False)

    # حفظ السجل العام
    pd.DataFrame(scan_results).to_csv("bot_activity_log.csv", index=False)
    print(f"🛡️ Bot Cycle Finished Successfully. Current Balance: ${account_balance:.2f}")

if __name__ == "__main__":
    run_strict_bot()
