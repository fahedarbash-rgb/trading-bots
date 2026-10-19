import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logging.basicConfig(filename='bot_errors.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

INITIAL_BALANCE = 200.0     
BASE_RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  

TRADE_FILE = "active_strict_trades.csv"
CLOSED_FILE = "closed_strict_trades_history.csv"
HEARTBEAT_FILE = "last_strict_heartbeat.txt"

COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD", "XRPUSDT": "XRP-USD", "ADAUSDT": "ADA-USD",
    "LINKUSDT": "LINK-USD", "AVAXUSDT": "AVAX-USD", "DOTUSDT": "DOT-USD",
    "NEARUSDT": "NEAR-USD", "MATICUSDT": "MATIC-USD"
}

def get_default_keyboard():
    """أزرار تفاعلية سريعة تظهر مع التنبيهات"""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 ملخص الرصيد والأداء", "callback_data": "get_balance"},
                {"text": "📂 الصفقات النشطة", "callback_data": "get_active_trades"}
            ]
        ]
    }

def send_telegram_message(message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "reply_markup": reply_markup if reply_markup else get_default_keyboard()
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

def get_dynamic_risk_percentage():
    """إدارة المخاطر الديناميكية العكسية (Anti-Drawdown Guard)"""
    if os.path.exists(CLOSED_FILE):
        try:
            df_closed = pd.read_csv(CLOSED_FILE)
            if len(df_closed) >= 2:
                last_two = df_closed.tail(2)['Result'].tolist()
                if last_two == ['LOSS', 'LOSS']:
                    return BASE_RISK_PERCENTAGE * 0.5  # تخفيض المخاطرة مؤقتاً لحماية رصيد الـ 200$
        except Exception as e:
            logging.error(f"Error checking anti-drawdown: {e}")
    return BASE_RISK_PERCENTAGE

def is_volatility_suitable(df):
    """فلتر التذبذب الذكي (ATR Volatility Filter)"""
    if df is None or len(df) < 20:
        return False
    curr_atr = df.iloc[-1]['atr']
    avg_atr = df['atr'].tail(20).mean()
    curr_price = df.iloc[-1]['close']
    
    relative_atr = (curr_atr / curr_price) * 100
    if relative_atr < 0.04 or curr_atr > (avg_atr * 3.0):
        return False
    return True

def check_daily_report(active_trades_count, current_balance):
    now = datetime.utcnow()
    send_report = False
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r") as f:
                if (now - datetime.fromisoformat(f.read().strip())) >= timedelta(hours=24):
                    send_report = True
        except:
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
            except:
                pass
        roi_percent = ((current_balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        send_telegram_message(
            f"📊 *Strict Bot: التقرير اليومي الشامل*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح/الخسائر: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"📂 الصفقات النشطة حالياً: `{active_trades_count} صفقات`"
        )
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
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            return None
        df_list = [{'timestamp': item[0] * 1000, 'low': float(item[1]), 'high': float(item[2]), 'open': float(item[3]), 'close': float(item[4]), 'volume': float(item[5])} for item in reversed(data)]
        df = pd.DataFrame(df_list)
        return df.tail(limit).reset_index(drop=True) if len(df) > limit else df
    except Exception as e:
        logging.error(f"Error fetching {product_id}: {e}")
        return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def manage_and_scan_strict_market():
    current_balance = INITIAL_BALANCE
    if os.path.exists(CLOSED_FILE):
        try:
            df_closed = pd.read_csv(CLOSED_FILE)
            if not df_closed.empty and 'PnL' in df_closed.columns:
                current_balance = INITIAL_BALANCE + df_closed['PnL'].sum()
        except Exception as e:
            logging.error(f"Error reading closed history for balance: {e}")

    active_trades = []
    if os.path.exists(TRADE_FILE):
        try:
            active_trades = pd.read_csv(TRADE_FILE).to_dict('records')
        except:
            pass

    updated_trades = []
    open_symbols = [t['Symbol'] for t in active_trades]

    for trade in active_trades:
        symbol = trade['Symbol']
        df = get_coinbase_candles(COINBASE_PRODUCTS.get(symbol, "BTC-USD"), granularity=3600, limit=5)
        if df is None or df.empty:
            updated_trades.append(trade)
            continue

        curr_price = df.iloc[-1]['close']
        entry_price = trade['Entry']
        tp1 = trade['TP1']
        tp2 = trade.get('TP2', entry_price + (tp1 - entry_price) * 1.4 if trade.get('Side', 'LONG') == 'LONG' else entry_price - (entry_price - tp1) * 1.4)
        sl = trade['SL']
        qty = trade['Qty']
        side = trade.get('Side', 'LONG')
        tp1_hit = trade.get('TP1_Hit', False)

        closed = False
        close_reason = ""

        if side == "LONG":
            if not tp1_hit and curr_price >= tp1:
                trade['TP1_Hit'] = True
                trade['SL'] = entry_price
                send_telegram_message(
                    f"🎯 *Strict Bot: TP1 Reached! (LONG {symbol})*\n"
                    f"🛡️ *Break-Even Guard:* تم نقل وقف الخسارة إلى سعر الدخول `{entry_price:.4f}` الصفقة آمنة 100%! ✅"
                )

            if curr_price >= tp2:
                profit = (tp2 - entry_price) * qty
                profit_percent = ((tp2 - entry_price) / entry_price) * 100 * LEVERAGE
                current_balance += profit
                close_reason = "TP2 Hit (Final Target)"
                send_telegram_message(f"🎉 *Strict Bot: TP2 Final Hit! (LONG {symbol})*\n💰 الربح: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': tp2, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                closed = True

            elif curr_price <= sl:
                loss = 0.0 if sl == entry_price else (entry_price - sl) * qty
                loss_percent = 0.0 if sl == entry_price else ((entry_price - sl) / entry_price) * 100 * LEVERAGE
                result_status = 'NEUTRAL' if sl == entry_price else 'LOSS'
                close_reason = "SL Hit at Break-Even (Protected)" if sl == entry_price else "SL Hit"
                current_balance -= loss
                send_telegram_message(f"🛑 *Strict Bot: Stop Loss Hit! (LONG {symbol})*\n📋 `{close_reason}`\n📉 الأثر: `-${loss:.2f}`\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True

        elif side == "SHORT":
            if not tp1_hit and curr_price <= tp1:
                trade['TP1_Hit'] = True
                trade['SL'] = entry_price
                send_telegram_message(
                    f"🎯 *Strict Bot: TP1 Reached! (SHORT {symbol})*\n"
                    f"🛡️ *Break-Even Guard:* تم نقل وقف الخسارة إلى سعر الدخول `{entry_price:.4f}` الصفقة آمنة 100%! ✅"
                )

            if curr_price <= tp2:
                profit = (entry_price - tp2) * qty
                profit_percent = ((entry_price - tp2) / entry_price) * 100 * LEVERAGE
                current_balance += profit
                close_reason = "TP2 Hit (Final Target)"
                send_telegram_message(f"🎉 *Strict Bot: TP2 Final Hit! (SHORT {symbol})*\n💰 الربح: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': tp2, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                closed = True

            elif curr_price >= sl:
                loss = 0.0 if sl == entry_price else (sl - entry_price) * qty
                loss_percent = 0.0 if sl == entry_price else ((sl - entry_price) / entry_price) * 100 * LEVERAGE
                result_status = 'NEUTRAL' if sl == entry_price else 'LOSS'
                close_reason = "SL Hit at Break-Even (Protected)" if sl == entry_price else "SL Hit"
                current_balance -= loss
                send_telegram_message(f"🛑 *Strict Bot: Stop Loss Hit! (SHORT {symbol})*\n📋 `{close_reason}`\n📉 الأثر: `-${loss:.2f}`\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry_price, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    dynamic_risk = get_dynamic_risk_percentage()

    if len(updated_trades) < 3:
        for symbol, coinbase_id in COINBASE_PRODUCTS.items():
            if symbol in open_symbols:
                continue
            df = get_coinbase_candles(coinbase_id, granularity=3600, limit=50)
            if df is None or len(df) < 30:
                continue
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['atr'] = calculate_atr(df, 14)
            
            if not is_volatility_suitable(df):
                continue

            curr_price = df.iloc[-1]['close']
            curr_rsi = df.iloc[-1]['rsi']
            ema50 = df.iloc[-1]['ema50']
            curr_atr = df.iloc[-1]['atr']

            if curr_price > ema50 and curr_rsi < 38:
                entry = curr_price
                sl = entry - (curr_atr * 1.5)
                tp1 = entry + (curr_atr * 1.8)
                tp2 = entry + (curr_atr * 3.0)
                qty = (current_balance * dynamic_risk) / (entry - sl) if (entry - sl) > 0 else 1.0
                if ((entry * qty) / LEVERAGE) <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and tp1 > entry:
                    updated_trades.append({'Symbol': symbol, 'Side': 'LONG', 'Entry': entry, 'TP1': tp1, 'TP2': tp2, 'SL': sl, 'Qty': qty, 'TP1_Hit': False})
                    open_symbols.append(symbol)
                    send_telegram_message(
                        f"🛡️ *Strict Bot: New LONG* `{symbol}`\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"📍 سعر الدخول: `{entry:.4f}`\n"
                        f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}`\n"
                        f"🛑 Stop Loss: `{sl:.4f}`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                    )
                    break
            elif curr_price < ema50 and curr_rsi > 62:
                entry = curr_price
                sl = entry + (curr_atr * 1.5)
                tp1 = entry - (curr_atr * 1.8)
                tp2 = entry - (curr_atr * 3.0)
                qty = (current_balance * dynamic_risk) / (sl - entry) if (sl - entry) > 0 else 1.0
                if ((entry * qty) / LEVERAGE) <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and entry > tp1:
                    updated_trades.append({'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry, 'TP1': tp1, 'TP2': tp2, 'SL': sl, 'Qty': qty, 'TP1_Hit': False})
                    open_symbols.append(symbol)
                    send_telegram_message(
                        f"🛡️ *Strict Bot: New SHORT* `{symbol}`\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"📍 سعر الدخول: `{entry:.4f}`\n"
                        f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}`\n"
                        f"🛑 Stop Loss: `{sl:.4f}`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                    )
                    break

    if updated_trades:
        pd.DataFrame(updated_trades).to_csv(TRADE_FILE, index=False)
    elif os.path.exists(TRADE_FILE):
        os.remove(TRADE_FILE)

    check_daily_report(len(updated_trades), current_balance)

if __name__ == "__main__":
    manage_and_scan_strict_market()
