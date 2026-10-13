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

TELEGRAM_BOT_TOKEN = "8988832604:AAGbhIC3iKCnCmacPDicf9vmP_qF4ujwsY0"
TELEGRAM_CHAT_ID = "5620413191"

INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  

TRADE_FILE = "active_global_trades.csv"
BALANCE_FILE = "global_balance.txt"
CLOSED_FILE = "closed_global_trades_history.csv"
HEARTBEAT_FILE = "last_global_heartbeat.txt"

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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

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
            f"📊 *Global S&R Bot (Active): التقرير اليومي الشامل*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح/الخسائر: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"📂 الصفقات النشطة حالياً: `{active_trades_count} صفقات`\n"
            f"⚡ *الرافعة المستخدمة:* `{LEVERAGE}x` | *المخاطرة لكل صفقة:* `{RISK_PERCENTAGE*100}%`\n"
            f"🛡️ *الحالة:* بوت الدعم والمقاومة يعمل بنطاق مرن لاقتناص الفرص."
        )
        send_telegram_message(report_msg)
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(now.isoformat())
        except Exception as e:
            logging.error(f"Error writing heartbeat: {e}")

def save_closed_trade(trade_data):
    file_exists = os.path.exists(CLOSED_FILE)
    try:
        pd.DataFrame([trade_data]).to_csv(CLOSED_FILE, mode='a', header=not file_exists, index=False)
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
        df_list = [{'timestamp': item[0] * 1000, 'low': float(item[1]), 'high': float(item[2]), 'open': float(item[3]), 'close': float(item[4]), 'volume': float(item[5])} for item in reversed(data)]
        df = pd.DataFrame(df_list)
        return df.tail(limit).reset_index(drop=True) if len(df) > limit else df
    except Exception as e:
        logging.error(f"Error fetching {product_id}: {e}")
        return None

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def find_support_resistance(df, window=15):
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
            if curr_price >= (entry + (tp1 - entry) * 0.5) and sl < entry:
                trade['SL'] = entry
                send_telegram_message(f"🔄 *Global S&R Trailing Stop Activated! (LONG {symbol})*")

            if curr_price >= tp1:
                profit = (tp1 - entry) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Global S&R TP Reached! (LONG {symbol})* - Profit: `+${profit:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price <= sl:
                loss = (entry - sl) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Global S&R Stop Loss Hit! (LONG {symbol})* - Loss: `-${loss:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True
        elif side == "SHORT":
            if curr_price <= (entry - (entry - tp1) * 0.5) and sl > entry:
                trade['SL'] = entry
                send_telegram_message(f"🔄 *Global S&R Trailing Stop Activated! (SHORT {symbol})*")

            if curr_price <= tp1:
                profit = (entry - tp1) * qty
                current_balance += profit
                send_telegram_message(f"🎯 *Global S&R TP Reached! (SHORT {symbol})* - Profit: `+${profit:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price >= sl:
                loss = (sl - entry) * qty
                current_balance -= loss
                send_telegram_message(f"🛑 *Global S&R Stop Loss Hit! (SHORT {symbol})* - Loss: `-${loss:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    if len(updated_trades) < 4:
        for symbol, coinbase_id in GLOBAL_PRODUCTS.items():
            if symbol in open_symbols:
                continue

            df_1h = get_coinbase_candles(coinbase_id, granularity=3600, limit=40)
            if df_1h is None or len(df_1h) < 25:
                continue

            df_1h['atr'] = calculate_atr(df_1h, 14)
            df_1h['avg_volume'] = df_1h['volume'].rolling(window=15).mean()
            support, resistance = find_support_resistance(df_1h, window=15)

            curr_price = df_1h.iloc[-1]['close']
            curr_volume = df_1h.iloc[-1]['volume']
            avg_volume = df_1h.iloc[-1]['avg_volume']
            curr_atr = df_1h.iloc[-1]['atr']

            is_volume_ok = curr_volume >= (avg_volume * 0.6)

            # تفعيل مرن للشراء عند الدعم (نطاق اقتراب أوسع 1.5 ATR)
            if abs(curr_price - support) <= (curr_atr * 1.5) and is_volume_ok:
                entry = curr_price
                sl = support - (curr_atr * 1.2)
                tp1 = resistance if resistance > entry else entry + (curr_atr * 2.5)
                
                risk_amount = current_balance * RISK_PERCENTAGE
                qty = risk_amount / (entry - sl) if (entry - sl) > 0 else 1.0
                margin = (entry * qty) / LEVERAGE

                if margin <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and tp1 > entry:
                    new_trade = {'Symbol': symbol, 'Side': 'LONG', 'Entry': entry, 'TP1': tp1, 'SL': sl, 'Qty': qty}
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    msg = (
                        f"🛡️ *Global S&R Bot: Flexible LONG Signal*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | الدعم المكتشف: `{support:.4f}`\n"
                        f"📍 سعر الدخول: `{entry:.4f}` | هدف الربح: `{tp1:.4f}`\n"
                        f"🛑 وقف الخسارة: `{sl:.4f}` | الرافعة: `{LEVERAGE}x`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                    )
                    send_telegram_message(msg)
                    break

            # تفعيل مرن للبيع عند المقاومة (نطاق اقتراب أوسع 1.5 ATR)
            elif abs(curr_price - resistance) <= (curr_atr * 1.5) and is_volume_ok:
                entry = curr_price
                sl = resistance + (curr_atr * 1.2)
                tp1 = support if support < entry else entry - (curr_atr * 2.5)
                
                risk_amount = current_balance * RISK_PERCENTAGE
                qty = risk_amount / (sl - entry) if (sl - entry) > 0 else 1.0
                margin = (entry * qty) / LEVERAGE

                if margin <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and entry > tp1:
                    new_trade = {'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry, 'TP1': tp1, 'SL': sl, 'Qty': qty}
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    msg = (
                        f"🛡️ *Global S&R Bot: Flexible SHORT Signal*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | المقاومة المكتشفة: `{resistance:.4f}`\n"
                        f"📍 سعر الدخول: `{entry:.4f}` | هدف الربح: `{tp1:.4f}`\n"
                        f"🛑 وقف الخسارة: `{sl:.4f}` | الرافعة: `{LEVERAGE}x`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
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
    manage_and_scan_sr_market()
