import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- إعدادات تيليجرام ---
TELEGRAM_BOT_TOKEN = "8772493944:AAGb4Y1VuBLrCq0vfvnhue7oRW4hjf_LYJE"
TELEGRAM_CHAT_ID = "5620413191"

# --- إعدادات رأس المال وإدارة المخاطر ---
INITIAL_BALANCE = 200.0       
RISK_PERCENTAGE = 0.02        
LEVERAGE = 3                  

# --- سلة العملات المعتمدة (صيغة كوينبيس لتفادي حظر بينانس) ---
COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "LINKUSDT": "LINK-USD",
    "ADAUSDT": "ADA-USD"
}

def send_telegram_message(message):
    """إرسال التنبيهات إلى تيليجرام"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def get_coinbase_candles(product_id, granularity=3600, limit=100):
    """جلب البيانات التاريخية من Coinbase API لتفادي الحظر الجغرافي"""
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

def calculate_atr(df, period=14):
    """حساب المدى الحقيقي المتوسط (ATR) للتقلب"""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def detect_support_resistance_and_fvg(df):
    """تحديد الدعم والمقاومة الهيكلية وفجوات الشموع (FVG)"""
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    support = df['low'].tail(15).min()
    resistance = df['high'].tail(15).max()
    
    bullish_fvg = prev['low'] > prev2['high']
    bearish_fvg = prev['high'] < prev2['low']
    
    return support, resistance, bullish_fvg, bearish_fvg

def manage_balanced_paper_trades(current_prices):
    """إدارة الصفقات المفتوحة (تتبع الـ TP والـ SL ونظام تأمين الصفقة Break-Even)"""
    trade_file = "active_balanced_trades.csv"
    balance_file = "balanced_balance.txt"
    
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
        side = row['Side'] # LONG أو SHORT
        entry_price = row['Entry']
        tp1 = row['TP1']
        tp2 = row['TP2']
        tp3 = row['TP3']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            
            if side == "LONG":
                # تفعيل وقف الخسارة المتحرك (Break-Even) عند الوصول لنصف المسافة نحو TP1
                if curr_price >= (entry_price + (tp1 - entry_price) * 0.5) and sl < entry_price:
                    sl = entry_price
                    row['SL'] = sl
                    send_telegram_message(f"🔄 *Balanced Trailing Stop ({symbol} LONG)*\nStop Loss moved to Entry Price: `{sl:.3f}`")

                if curr_price >= tp1:
                    profit = (tp1 - entry_price) * qty
                    current_balance += profit
                    send_telegram_message(f"🎯 *Balanced TP1 Reached! ({symbol} LONG)*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                    continue
                elif curr_price <= sl:
                    loss = (entry_price - sl) * qty if sl < entry_price else 0
                    current_balance -= loss
                    send_telegram_message(f"🛑 *Balanced Stop Loss Hit! ({symbol} LONG)*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                    continue
                    
            elif side == "SHORT":
                # تفعيل وقف الخسارة المتحرك للـ Short
                if curr_price <= (entry_price - (entry_price - tp1) * 0.5) and sl > entry_price:
                    sl = entry_price
                    row['SL'] = sl
                    send_telegram_message(f"🔄 *Balanced Trailing Stop ({symbol} SHORT)*\nStop Loss moved to Entry Price: `{sl:.3f}`")

                if curr_price <= tp1:
                    profit = (entry_price - tp1) * qty
                    current_balance += profit
                    send_telegram_message(f"🎯 *Balanced TP1 Reached! ({symbol} SHORT)*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                    continue
                elif curr_price >= sl:
                    loss = (sl - entry_price) * qty if sl > entry_price else 0
                    current_balance -= loss
                    send_telegram_message(f"🛑 *Balanced Stop Loss Hit! ({symbol} SHORT)*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                    continue
        
        updated_trades.append(row)

    if len(updated_trades) > 0:
        pd.DataFrame(updated_trades).to_csv(trade_file, index=False)
    else:
        pd.DataFrame(columns=trades_df.columns).to_csv(trade_file, index=False)

    with open(balance_file, "w") as f:
        f.write(str(current_balance))

    return current_balance

def run_balanced_bot():
    print("⚖️ Balanced Bot Scan (Bilateral with S/R, FVG & Paper Trading) Started...")
    
    balance_file = "balanced_balance.txt"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            account_balance = float(f.read().strip())
    else:
        account_balance = INITIAL_BALANCE

    current_prices_map = {}
    scan_results = []
    new_trades = []
    
    trade_file = "active_balanced_trades.csv"
    if os.path.exists(trade_file) and os.path.getsize(trade_file) > 0:
        active_trades_df = pd.read_csv(trade_file)
    else:
        active_trades_df = pd.DataFrame(columns=['Symbol', 'Side', 'Entry', 'TP1', 'TP2', 'TP3', 'SL', 'Qty'])

    for symbol, cb_product in COINBASE_PRODUCTS.items():
        df = get_coinbase_candles(cb_product, granularity=3600, limit=100)
        
        if df is None or len(df) < 30:
            continue
            
        df['atr'] = calculate_atr(df, 14)
        current_price = df['close'].iloc[-1]
        current_atr = df['atr'].iloc[-1] if not np.isnan(df['atr'].iloc[-1]) else (current_price * 0.01)
        
        current_prices_map[symbol] = current_price
        
        support, resistance, bullish_fvg, bearish_fvg = detect_support_resistance_and_fvg(df)
        
        already_open = False
        if not active_trades_df.empty and symbol in active_trades_df['Symbol'].values:
            already_open = True

        signal_status = "No Signal"

        # 1. شروط صفقة شراء (LONG)
        is_near_support = abs(current_price - support) <= (current_atr * 1.5)
        if (is_near_support or bullish_fvg) and not already_open:
            signal_status = "BALANCED LONG"
            entry_price = current_price
            sl = round(support - (current_atr * 1.0), 4)
            
            tp1 = round(entry_price + (entry_price - sl) * 1.0, 4)
            tp2 = round(entry_price + (entry_price - sl) * 2.0, 4)
            tp3 = round(resistance, 4) if resistance > entry_price else round(entry_price + (entry_price - sl) * 3.5, 4)
            
            risk_amount = account_balance * RISK_PERCENTAGE
            risk_per_unit = entry_price - sl
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.01
            position_value = position_size * entry_price
            margin_required = position_value / LEVERAGE

            new_trades.append({
                'Symbol': symbol,
                'Side': 'LONG',
                'Entry': entry_price,
                'TP1': tp1,
                'TP2': tp2,
                'TP3': tp3,
                'SL': sl,
                'Qty': position_size
            })

            message = (
                f"⚖️ *Balanced Bot: {symbol}*\n"
                f"🟢 *New LONG Position Opened*\n"
                f"💰 Entry: `{entry_price}`\n"
                f"🎯 TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
                f"🛑 Stop Loss: `{sl}`\n"
                f"⚖ *Risk & Leverage ({LEVERAGE}x):*\n"
                f"• Qty: `{position_size:.4f}`\n"
                f"• Margin: `${margin_required:.2f}`\n"
                f"💼 *Balance:* `${account_balance:.2f}` USDT"
            )
            send_telegram_message(message)

        # 2. شروط صفقة بيع (SHORT)
        is_near_resistance = abs(current_price - resistance) <= (current_atr * 1.5)
        if (is_near_resistance or bearish_fvg) and not already_open and signal_status == "No Signal":
            signal_status = "BALANCED SHORT"
            entry_price = current_price
            sl = round(resistance + (current_atr * 1.0), 4)
            
            tp1 = round(entry_price - (sl - entry_price) * 1.0, 4)
            tp2 = round(entry_price - (sl - entry_price) * 2.0, 4)
            tp3 = round(support, 4) if support < entry_price else round(entry_price - (sl - entry_price) * 3.5, 4)
            
            risk_amount = account_balance * RISK_PERCENTAGE
            risk_per_unit = sl - entry_price
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.01
            position_value = position_size * entry_price
            margin_required = position_value / LEVERAGE

            new_trades.append({
                'Symbol': symbol,
                'Side': 'SHORT',
                'Entry': entry_price,
                'TP1': tp1,
                'TP2': tp2,
                'TP3': tp3,
                'SL': sl,
                'Qty': position_size
            })

            message = (
                f"⚖️ *Balanced Bot: {symbol}*\n"
                f"🔴 *New SHORT Position Opened*\n"
                f"💰 Entry: `{entry_price}`\n"
                f"🎯 TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
                f"🛑 Stop Loss: `{sl}`\n"
                f"⚖ *Risk & Leverage ({LEVERAGE}x):*\n"
                f"• Qty: `{position_size:.4f}`\n"
                f"• Margin: `${margin_required:.2f}`\n"
                f"💼 *Balance:* `${account_balance:.2f}` USDT"
            )
            send_telegram_message(message)

        scan_results.append({
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "Bot_Type": "Balanced_Bot",
            "Symbol": symbol,
            "Price": current_price,
            "Signal": signal_status
        })
        
    account_balance = manage_balanced_paper_trades(current_prices_map)

    if len(new_trades) > 0:
        new_df = pd.DataFrame(new_trades)
        updated_active = pd.concat([active_trades_df, new_df], ignore_index=True)
        updated_active.to_csv(trade_file, index=False)

    log_df = pd.DataFrame(scan_results)
    log_df.to_csv("bot_activity_log_balanced.csv", index=False)
    print(f"⚖️ Balanced Bot Scan Finished. Current Balance: ${account_balance:.2f}")

if __name__ == "__main__":
    run_balanced_bot()
