import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- إعداد نظام تسجيل الأخطاء ---
logging.basicConfig(
    filename='bot_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# مفاتيح تيليجرام للبوت الجديد (Global S&R Scanner Bot)
TELEGRAM_BOT_TOKEN = "8988832604:AAGbhIC3iKCnCmacPDicf9vmP_qF4ujwsY0"
TELEGRAM_CHAT_ID = "5620413191"

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  

# --- ملفات السجلات والأرشيف ---
TRADE_FILE = "active_global_trades.csv"
BALANCE_FILE = "global_balance.txt"
CLOSED_FILE = "closed_global_trades_history.csv"
HEARTBEAT_FILE = "last_global_heartbeat.txt"

# قائمة العملات ذات السيولة العالية واحترام الدعم والمقاومة
GLOBAL_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "XRPUSDT": "XRP-USD",
    "AVAXUSDT": "AVAX-USD",
    "LINKUSDT": "LINK-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram Response: {response.status_code}")
    except Exception as e:
        error_msg = f"Telegram Error: {e}"
        print(error_msg)
        logging.error(error_msg)

def check_heartbeat():
    now = datetime.utcnow()
    send_hb = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r") as f:
                last_time = datetime.fromisoformat(f.read().strip())
                if (now - last_time) >= timedelta(hours=24):
                    send_hb = True
        except Exception:
            send_hb = True
    else:
        send_hb = True

    if send_hb:
        send_telegram_message("💓 *Global S&R Scanner Bot Heartbeat:* البوت المتقدم متعدد الأطر الزمنية يعمل بكفاءة عالية ويراقب الأسواق.")
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(now.isoformat())
        except Exception as e:
            logging.error(f"Error writing heartbeat file: {e}")

def save_closed_trade(trade_data):
    file_exists = os.path.exists(CLOSED_FILE)
    df = pd.DataFrame([trade_data])
    try:
        df.to_csv(CLOSED_FILE, mode='a', header=not file_exists, index=False)
    except Exception as e:
        logging.error(f"Error saving closed trade: {e}")

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
        logging.error(f"Error fetching {product_id}: {e}")
        return None

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def find_support_resistance(df, window=25):
    support = df['low'].rolling(window=window, center=False).min().iloc[-1]
    resistance = df['high'].rolling(window=window, center=False).max().iloc[-1]
    return support, resistance

def manage_and_scan_sr_market():
    current_balance = INITIAL_BALANCE
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE, "r") as f:
                current_balance = float(f.read().strip())
        except Exception:
            pass

    active_trades = []
    if os.path.exists(TRADE_FILE):
        try:
            active_trades = pd.read_csv(TRADE_FILE).to_dict('records')
        except Exception:
            pass

    updated_trades = []
    open_symbols = [t['Symbol'] for t in active_trades]

    # 1. إدارة الصفقات المفتوحة (متابعة السعر اللحظي على إطار الساعة)
    for trade in active_trades:
        symbol = trade['Symbol']
        df = get_coinbase_candles(GLOBAL_PRODUCTS.get(symbol, "BTC-USD"), granularity=3600, limit=5)
        if df is None or df.empty:
            updated_trades.append(trade)
            continue
            
        curr_price = df.iloc[-1]['close']
        entry = trade['Entry']
        tp1 = trade['TP1']
        sl = trade['SL']
        qty = trade['Qty']
        side = trade['Side']

        closed = False
        if side == "LONG":
            if curr_price >= tp1:
                profit = (tp1 - entry) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Global S&R TP Reached! (LONG {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price <= sl:
                loss = (entry - sl) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Global S&R Stop Loss! (LONG {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True
        elif side == "SHORT":
            if curr_price <= tp1:
                profit = (entry - tp1) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Global S&R TP Reached! (SHORT {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price >= sl:
                loss = (sl - entry) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Global S&R Stop Loss! (SHORT {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    # 2. فحص السوق عبر نظام الأطر الزمنية المتعددة (Daily + 4H + 1H + 15m)
    if len(updated_trades) < 4:
        for symbol, coinbase_id in GLOBAL_PRODUCTS.items():
            if symbol in open_symbols:
                continue
                
            # جلب البيانات للأطر الزمنية المختلفة
            df_daily = get_coinbase_candles(coinbase_id, granularity=86400, limit=50) # يومي
            df_4h = get_coinbase_candles(coinbase_id, granularity=21600, limit=50)    # 4 ساعات
            df_1h = get_coinbase_candles(coinbase_id, granularity=3600, limit=60)     # ساعة
            df_15m = get_coinbase_candles(coinbase_id, granularity=900, limit=30)     # 15 دقيقة
            
            if (df_daily is None or len(df_daily) < 30 or 
                df_4h is None or len(df_4h) < 30 or 
                df_1h is None or len(df_1h) < 40 or 
                df_15m is None or len(df_15m) < 10):
                continue
                
            # تحديد الاتجاه العام للإطار اليومي وإطار 4 ساعات (EMA 50)
            df_daily['ema50'] = df_daily['close'].ewm(span=50, adjust=False).mean()
            trend_daily = "BULLISH" if df_daily.iloc[-1]['close'] > df_daily.iloc[-1]['ema50'] else "BEARISH"

            df_4h['ema50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
            trend_4h = "BULLISH" if df_4h.iloc[-1]['close'] > df_4h.iloc[-1]['ema50'] else "BEARISH"

            # استخراج الدعوم والمقاومات من إطار الساعة
            df_1h['atr'] = calculate_atr(df_1h, 14)
            df_1h['avg_volume'] = df_1h['volume'].rolling(window=20).mean()
            support, resistance = find_support_resistance(df_1h, window=30)
            
            curr_price = df_1h.iloc[-1]['close']
            curr_volume = df_1h.iloc[-1]['volume']
            avg_volume = df_1h.iloc[-1]['avg_volume']
            curr_atr = df_1h.iloc[-1]['atr']

            is_volume_confirmed = curr_volume >= (avg_volume * 0.9)

            # تأكيد إضافي من إطار 15 دقيقة (التأكد من أن الشمعة الأخيرة تبدأ بالارتداد صعوداً أو هبوطاً)
            last_15m_close = df_15m.iloc[-1]['close']
            prev_15m_close = df_15m.iloc[-2]['close']

            # شروط صفقات الشراء LONG (توافق صاعد على اليومي والـ 4 ساعات + ارتداد 15 دقيقة)
            if (trend_daily == "BULLISH" and trend_4h == "BULLISH" and 
                abs(curr_price - support) <= (curr_atr * 0.4) and curr_price >= support and 
                is_volume_confirmed and last_15m_close >= prev_15m_close):
                
                entry = curr_price
                sl = support - (curr_atr * 1.0)
                tp1 = resistance
                risk_amount = current_balance * RISK_PERCENTAGE
                qty = risk_amount / (entry - sl) if (entry - sl) > 0 else 1.0
                margin = (entry * qty) / LEVERAGE

                if margin <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and tp1 > entry:
                    new_trade = {
                        'Symbol': symbol, 'Side': 'LONG', 'Entry': entry,
                        'TP1': tp1, 'SL': sl, 'Qty': qty
                    }
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    
                    send_telegram_message(
                        f"🛡️ *Global S&R Bot: Confirmed LONG (3x | Multi-TF Confluence)*\n"
                        f"🔹 Symbol: `{symbol}` | Entry: `{entry:.4f}`\n"
                        f"📈 Trend (Daily/4H): `UP / UP`\n"
                        f"🟢 Support: `{support:.4f}` | 📊 Vol & 15m Confirmed\n"
                        f"🎯 TP: `{tp1:.4f}` | 🛑 SL: `{sl:.4f}`\n"
                        f"⚖️ Margin: `${margin:.2f}`"
                    )
                    break

            # شروط صفقات البيع SHORT (توافق هابط على اليومي والـ 4 ساعات + ارتداد 15 دقيقة)
            elif (trend_daily == "BEARISH" and trend_4h == "BEARISH" and 
                  abs(curr_price - resistance) <= (curr_atr * 0.4) and curr_price <= resistance and 
                  is_volume_confirmed and last_15m_close <= prev_15m_close):
                
                entry = curr_price
                sl = resistance + (curr_atr * 1.0)
                tp1 = support
                risk_amount = current_balance * RISK_PERCENTAGE
                qty = risk_amount / (sl - entry) if (sl - entry) > 0 else 1.0
                margin = (entry * qty) / LEVERAGE

                if margin <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and entry > tp1:
                    new_trade = {
                        'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry,
                        'TP1': tp1, 'SL': sl, 'Qty': qty
                    }
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    
                    send_telegram_message(
                        f"🛡️ *Global S&R Bot: Confirmed SHORT (3x | Multi-TF Confluence)*\n"
                        f"🔹 Symbol: `{symbol}` | Entry: `{entry:.4f}`\n"
                        f"📉 Trend (Daily/4H): `DOWN / DOWN`\n"
                        f"🔴 Resistance: `{resistance:.4f}` | 📊 Vol & 15m Confirmed\n"
                        f"🎯 TP: `{tp1:.4f}` | 🛑 SL: `{sl:.4f}`\n"
                        f"⚖️ Margin: `${margin:.2f}`"
                    )
                    break

    if updated_trades:
        pd.DataFrame(updated_trades).to_csv(TRADE_FILE, index=False)
    else:
        if os.path.exists(TRADE_FILE):
            os.remove(TRADE_FILE)

    with open(BALANCE_FILE, "w") as f:
        f.write(str(current_balance))

if __name__ == "__main__":
    check_heartbeat()
    manage_and_scan_sr_market()
