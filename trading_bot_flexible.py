import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- إعداد نظام تسجيل الأخطاء (Error Logging) ---
logging.basicConfig(
    filename='bot_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# مفاتيح التيليجرام للبوت المرن
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها من الرصيد كإجمالي هوامش مفتوحة (60%)

# --- ملفات السجلات والأرشيف ---
TRADE_FILE = "active_flexible_trades.csv"
BALANCE_FILE = "flexible_balance.txt"
CLOSED_FILE = "closed_flexible_trades_history.csv"
HEARTBEAT_FILE = "last_flexible_heartbeat.txt"

# خريطة الرموز للتوافق مع Coinbase API
COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "LINKUSDT": "LINK-USD",
    "ADAUSDT": "ADA-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        error_msg = f"Telegram Error: {e}"
        logging.error(error_msg)
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 *Emergency Alert (Flexible Bot):* فشل الاتصال بتيليجرام: {e}", "parse_mode": "Markdown"}, timeout=5)
        except:
            pass

def check_daily_report(active_trades_count, current_balance):
    now = datetime.utcnow()
    send_report = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r") as f:
                last_time = datetime.fromisoformat(f.read().strip())
                if (now - last_time) >= timedelta(hours=24):
                    send_report = True
        except Exception:
            send_report = True
    else:
        send_report = True

    if send_report:
        wins, losses, total_pnl = 0, 0, 0.0
        if os.path.exists(CLOSED_FILE):
            try:
                df_closed = pd.read_csv(CLOSED_FILE)
                if not df_closed.empty:
                    wins = len(df_closed[df_closed['Result'] == 'WIN'])
                    losses = len(df_closed[df_closed['Result'] == 'LOSS'])
                    total_pnl = df_closed['PnL'].sum()
            except Exception:
                pass

        roi_percent = ((current_balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        report_msg = (
            f"📊 *Flexible Fast Bot: التقرير اليومي الشامل الاحترافي*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح/الخسائر: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"📂 الصفقات النشطة حالياً: `{active_trades_count} صفقات`\n"
            f"🚀 *الحالة:* البوت المرن السريع يقتنص الفرص على فريم الـ 15 دقيقة بكفاءة."
        )
        send_telegram_message(report_msg)
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

def get_coinbase_candles(product_id, granularity=900, limit=100): # تم التعديل إلى 900 ثانية (15 دقيقة) للسرعة
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
        error_msg = f"Error fetching {product_id}: {e}"
        logging.error(error_msg)
        send_telegram_message(f"🚨 *Emergency Alert (Flexible Fast Bot):* فشل جلب الشموع للعملة `{product_id}` - الخطأ: {e}")
        return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_bollinger_bands(series, period=20, std_dev=2):
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return middle, upper, lower

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def manage_and_scan_flexible_market():
    current_balance = INITIAL_BALANCE
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE, "r") as f:
                current_balance = float(f.read().strip())
        except Exception:
            pass

    # 1. إدارة الصفقات المفتوحة (LONG & SHORT) مع Trailing Stop الأوتوماتيكي
    active_trades = []
    if os.path.exists(TRADE_FILE):
        try:
            active_trades = pd.read_csv(TRADE_FILE).to_dict('records')
        except Exception:
            pass

    updated_trades = []
    open_symbols = [t['Symbol'] for t in active_trades]

    for trade in active_trades:
        symbol = trade['Symbol']
        df = get_coinbase_candles(COINBASE_PRODUCTS.get(symbol, "BTC-USD"), granularity=900, limit=5)
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
            if curr_price >= (entry + (tp1 - entry) * 0.5) and sl < entry:
                trade['SL'] = entry
                send_telegram_message(f"🔄 *Flexible Fast Trailing Stop Activated! (LONG {symbol})*\nStop Loss moved to Entry Price.")

            if curr_price >= tp1:
                profit = (tp1 - entry) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Flexible Fast TP Reached! (LONG {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price <= sl:
                loss = (entry - sl) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Flexible Fast Stop Loss Hit! (LONG {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True
        elif side == "SHORT":
            if curr_price <= (entry - (entry - tp1) * 0.5) and sl > entry:
                trade['SL'] = entry
                send_telegram_message(f"🔄 *Flexible Fast Trailing Stop Activated! (SHORT {symbol})*\nStop Loss moved to Entry Price.")

            if curr_price <= tp1:
                profit = (entry - tp1) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Flexible Fast TP Reached! (SHORT {symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price >= sl:
                loss = (sl - entry) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Flexible Fast Stop Loss Hit! (SHORT {symbol})*\nLoss: `-${loss:.2f}`\nBalance: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    # 2. فحص السوق السريع (فريم 15 دقيقة مع شروط RSI مرنة: أقل من 40 للشراء، وأعلى من 60 للبيع)
    if len(updated_trades) < 4: # رفع السماحية حتى 4 صفقات لاقتناص فرص أكثر
        for symbol, coinbase_id in COINBASE_PRODUCTS.items():
            if symbol in open_symbols:
                continue
                
            df = get_coinbase_candles(coinbase_id, granularity=900, limit=50)
            if df is None or len(df) < 30:
                continue
                
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['mid_band'], df['upper_band'], df['lower_band'] = calculate_bollinger_bands(df['close'], 20, 2)
            df['atr'] = calculate_atr(df, 14)
            
            curr_price = df.iloc[-1]['close']
            curr_rsi = df.iloc[-1]['rsi']
            lower_b = df.iloc[-1]['lower_band']
            upper_b = df.iloc[-1]['upper_band']
            mid_b = df.iloc[-1]['mid_band']
            curr_atr = df.iloc[-1]['atr']

            # أ. شروط صفقات الشراء السريعة (LONG) - مرونة RSI < 40 واقتراب من الحد السفلي
            if curr_price <= (lower_b * 1.005) and curr_rsi < 40:
                entry = curr_price
                sl = entry - (curr_atr * 1.5)
                tp1 = mid_b
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
                    
                    msg = (
                        f"🚀 *Flexible Fast Bot: New LONG Signal*\n"
                        f"🔹 Symbol: `{symbol}` | Entry: `{entry:.4f}`\n"
                        f"🎯 TP (Mid): `{tp1:.4f}` | 🛑 SL: `{sl:.4f}` | RSI: `{curr_rsi:.1f}`"
                    )
                    send_telegram_message(msg)
                    break

            # ب. شروط صفقات البيع السريعة (SHORT) - مرونة RSI > 60 واقتراب من الحد العلوي
            elif curr_price >= (upper_b * 0.995) and curr_rsi > 60:
                entry = curr_price
                sl = entry + (curr_atr * 1.5)
                tp1 = mid_b
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
                    
                    msg = (
                        f"📉 *Flexible Fast Bot: New SHORT Signal*\n"
                        f"🔹 Symbol: `{symbol}` | Entry: `{entry:.4f}`\n"
                        f"🎯 TP (Mid): `{tp1:.4f}` | 🛑 SL: `{sl:.4f}` | RSI: `{curr_rsi:.1f}`"
                    )
                    send_telegram_message(msg)
                    break

    if updated_trades:
        pd.DataFrame(updated_trades).to_csv(TRADE_FILE, index=False)
    else:
        if os.path.exists(TRADE_FILE):
            os.remove(TRADE_FILE)

    with open(BALANCE_FILE, "w") as f:
        f.write(str(current_balance))

    check_daily_report(len(updated_trades), current_balance)

if __name__ == "__main__":
    manage_and_scan_flexible_market()
