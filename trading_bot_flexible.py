import os
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logging.basicConfig(filename='bot_errors.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  

TRADE_FILE = "active_flexible_trades.csv"
CLOSED_FILE = "closed_flexible_trades_history.csv"
HEARTBEAT_FILE = "last_flexible_heartbeat.txt"

COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD", "LINKUSDT": "LINK-USD", "ADAUSDT": "ADA-USD"
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

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
            f"📊 *Flexible Bot: التقرير اليومي الشامل*\n"
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

def get_coinbase_candles(product_id, granularity=900, limit=100):
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

def calculate_stoch_rsi(series, period=14, k_period=3, d_period=3):
    rsi = calculate_rsi(series, period)
    stoch_rsi = (rsi - rsi.rolling(window=period).min()) / (rsi.rolling(window=period).max() - rsi.rolling(window=period).min())
    return stoch_rsi.rolling(window=k_period).mean() * 100, stoch_rsi.rolling(window=k_period).mean().rolling(window=d_period).mean() * 100

def calculate_bollinger_bands(series, period=20, std_dev=2):
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return middle, middle + (std * std_dev), middle - (std * std_dev)

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(window=period).mean()

def manage_and_scan_flexible_market():
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
        df = get_coinbase_candles(COINBASE_PRODUCTS.get(symbol, "BTC-USD"), granularity=900, limit=5)
        if df is None or df.empty:
            updated_trades.append(trade)
            continue
            
        curr_price = df.iloc[-1]['close']
        entry = trade['Entry']
        tp1 = trade['TP1']
        tp2 = trade.get('TP2', entry + (tp1 - entry) * 1.5 if trade['Side'] == 'LONG' else entry - (entry - tp1) * 1.5)
        sl = trade['SL']
        qty = trade['Qty']
        side = trade['Side']
        tp1_hit = trade.get('TP1_Hit', False)

        closed = False
        close_reason = ""

        if side == "LONG":
            if not tp1_hit and curr_price >= tp1:
                trade['TP1_Hit'] = True
                trade['SL'] = entry
                send_telegram_message(f"🎯 *Flexible Bot: TP1 Reached! (LONG {symbol})*\n🛡️ تم نقل وقف الخسارة إلى سعر الدخول.")

            if curr_price >= tp2:
                profit = (tp2 - entry) * qty
                profit_percent = ((tp2 - entry) / entry) * 100 * LEVERAGE
                current_balance += profit
                close_reason = "TP2 Hit (Final Target)"
                send_telegram_message(f"🎉 *Flexible Bot: TP2 Final Hit! (LONG {symbol})*\n💰 الربح: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp2, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                closed = True

            elif curr_price <= sl:
                loss = 0.0 if sl == entry else (entry - sl) * qty
                loss_percent = 0.0 if sl == entry else ((entry - sl) / entry) * 100 * LEVERAGE
                result_status = 'NEUTRAL' if sl == entry else 'LOSS'
                close_reason = "SL Hit at Break-Even (Protected)" if sl == entry else "SL Hit"
                current_balance -= loss
                send_telegram_message(f"🛑 *Flexible Bot: Stop Loss Hit! (LONG {symbol})*\n📋 `{close_reason}`\n📉 الأثر: `-${loss:.2f}`\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True

        elif side == "SHORT":
            if not tp1_hit and curr_price <= tp1:
                trade['TP1_Hit'] = True
                trade['SL'] = entry
                send_telegram_message(f"🎯 *Flexible Bot: TP1 Reached! (SHORT {symbol})*\n🛡️ تم نقل وقف الخسارة إلى سعر الدخول.")

            if curr_price <= tp2:
                profit = (entry - tp2) * qty
                profit_percent = ((entry - tp2) / entry) * 100 * LEVERAGE
                current_balance += profit
                close_reason = "TP2 Hit (Final Target)"
                send_telegram_message(f"🎉 *Flexible Bot: TP2 Final Hit! (SHORT {symbol})*\n💰 الربح: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp2, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                closed = True

            elif curr_price >= sl:
                loss = 0.0 if sl == entry else (sl - entry) * qty
                loss_percent = 0.0 if sl == entry else ((sl - entry) / entry) * 100 * LEVERAGE
                result_status = 'NEUTRAL' if sl == entry else 'LOSS'
                close_reason = "SL Hit at Break-Even (Protected)" if sl == entry else "SL Hit"
                current_balance -= loss
                send_telegram_message(f"🛑 *Flexible Bot: Stop Loss Hit! (SHORT {symbol})*\n📋 `{close_reason}`\n📉 الأثر: `-${loss:.2f}`\n💵 الرصيد الجديد: `${current_balance:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    if len(updated_trades) < 4:
        for symbol, coinbase_id in COINBASE_PRODUCTS.items():
            if symbol in open_symbols:
                continue
            df = get_coinbase_candles(coinbase_id, granularity=900, limit=60)
            if df is None or len(df) < 40:
                continue
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['mid_band'], df['upper_band'], df['lower_band'] = calculate_bollinger_bands(df['close'], 20, 2)
            df['atr'] = calculate_atr(df, 14)
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            
            curr_candle = df.iloc[-1]
            curr_price = curr_candle['close']
            curr_open = curr_candle['open']
            curr_low = curr_candle['low']
            curr_high = curr_candle['high']
            curr_rsi = curr_candle['rsi']
            lower_b = curr_candle['lower_band']
            mid_b = curr_candle['mid_band']
            curr_atr = curr_candle['atr']
            ema50 = curr_candle['ema50']
            vol_ma = curr_candle['volume_ma']

            body_size = abs(curr_price - curr_open)
            lower_wick = min(curr_open, curr_price) - curr_low
            upper_wick = curr_high - max(curr_open, curr_price)
            has_good_volume = curr_candle['volume'] >= (vol_ma * 0.6)

            if (curr_price < ema50 or curr_price >= mid_b) and (curr_rsi < 60) and (curr_price < curr_open or upper_wick >= body_size) and has_good_volume:
                entry = curr_price
                sl = entry + (curr_atr * 1.5)
                tp1 = min(lower_b, entry - (sl - entry) * 1.5)
                tp2 = min(lower_b * 0.98, entry - (sl - entry) * 2.5)
                qty = (current_balance * RISK_PERCENTAGE) / (sl - entry) if (sl - entry) > 0 else 1.0
                if ((entry * qty) / LEVERAGE) <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and entry > tp1:
                    updated_trades.append({'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry, 'TP1': tp1, 'TP2': tp2, 'SL': sl, 'Qty': qty, 'TP1_Hit': False})
                    open_symbols.append(symbol)
                    send_telegram_message(f"📉 *Flexible Bot: New SHORT* `{symbol}`\n📍 الدخول: `{entry:.4f}` | الرصيد: `${current_balance:.2f}`")
                    break
            elif (curr_price > ema50) and (curr_price <= lower_b * 1.01) and (curr_rsi < 45) and (curr_price > curr_open or lower_wick >= body_size) and has_good_volume:
                entry = curr_price
                sl = entry - (curr_atr * 1.5)
                tp1 = max(mid_b, entry + (entry - sl) * 1.5)
                tp2 = max(mid_b * 1.02, entry + (entry - sl) * 2.5)
                qty = (current_balance * RISK_PERCENTAGE) / (entry - sl) if (entry - sl) > 0 else 1.0
                if ((entry * qty) / LEVERAGE) <= (current_balance * MAX_TOTAL_MARGIN_RATIO) and tp1 > entry:
                    updated_trades.append({'Symbol': symbol, 'Side': 'LONG', 'Entry': entry, 'TP1': tp1, 'TP2': tp2, 'SL': sl, 'Qty': qty, 'TP1_Hit': False})
                    open_symbols.append(symbol)
                    send_telegram_message(f"🚀 *Flexible Bot: New LONG* `{symbol}`\n📍 الدخول: `{entry:.4f}` | الرصيد: `${current_balance:.2f}`")
                    break

    if updated_trades:
        pd.DataFrame(updated_trades).to_csv(TRADE_FILE, index=False)
    elif os.path.exists(TRADE_FILE):
        os.remove(TRADE_FILE)

    check_daily_report(len(updated_trades), current_balance)

if __name__ == "__main__":
    manage_and_scan_flexible_market()
