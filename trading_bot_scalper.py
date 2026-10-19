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

TELEGRAM_BOT_TOKEN = "8733239782:AAFgTANZqzFSa1LF5E57_mPJIBOJIlHnou0"
TELEGRAM_CHAT_ID = "5620413191"

INITIAL_BALANCE = 200.0     
BASE_RISK_PERCENTAGE = 0.025   # زيادة طفيفة لزيادة نشاط الصفقات
LEVERAGE = 5     
MAX_TOTAL_MARGIN_RATIO = 0.6  

TRADE_FILE = "active_scalper_trades.csv"
CLOSED_FILE = "closed_scalper_trades_history.csv"
HEARTBEAT_FILE = "last_scalper_heartbeat.txt"

PIONEX_SYMBOLS = {
    "BTCUSDT": "BTC_USDT",
    "ETHUSDT": "ETH_USDT",
    "SOLUSDT": "SOL_USDT",
    "XRPUSDT": "XRP_USDT",
    "ADAUSDT": "ADA_USDT",
    "AVAXUSDT": "AVAX_USDT",
    "LINKUSDT": "LINK_USDT",
    "DOGEUSDT": "DOGE_USDT",
    "SUIUSDT": "SUI_USDT"
}

def get_default_keyboard():
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
            f"⚡ *Lightning Scalper (New Strategy - 5x - 1m)*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"📂 الصفقات النشطة: `{active_trades_count}`\n"
            f"🚀 *الحالة:* استراتيجية الزخم السريع تعمل بكفاءة."
        )
        send_telegram_message(report_msg)
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(now.isoformat())
        except Exception as e:
            logging.error(f"Error writing heartbeat: {e}")

def save_closed_trade(trade_data):
    file_exists = os.path.exists(CLOSED_FILE)
    df = pd.DataFrame([trade_data])
    try:
        df.to_csv(CLOSED_FILE, mode='a', header=not file_exists, index=False)
    except Exception as e:
        logging.error(f"Error saving closed trade: {e}")

def get_pionex_candles(symbol, interval="1m", limit=50):
    url = f"https://api.pionex.com/api/v1/market/klines?symbol={symbol}&interval={interval}&limit={limit}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get("result") and "klines" in data.get("data", {}):
            raw_klines = data["data"]["klines"]
            df_list = []
            for item in raw_klines:
                df_list.append({
                    'timestamp': int(item['time']),
                    'open': float(item['open']),
                    'high': float(item['high']),
                    'low': float(item['low']),
                    'close': float(item['close']),
                    'volume': float(item['volume'])
                })
            return pd.DataFrame(df_list)
        return None
    except Exception as e:
        logging.error(f"Error fetching {symbol}: {e}")
        return None

def calculate_rsi(series, period=7):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def manage_and_scan_scalper_market():
    current_balance = INITIAL_BALANCE
    if os.path.exists(CLOSED_FILE):
        try:
            df_closed = pd.read_csv(CLOSED_FILE)
            if not df_closed.empty and 'PnL' in df_closed.columns:
                current_balance = INITIAL_BALANCE + df_closed['PnL'].sum()
        except Exception as e:
            logging.error(f"Error reading history: {e}")

    active_trades = []
    if os.path.exists(TRADE_FILE):
        try:
            active_trades = pd.read_csv(TRADE_FILE).to_dict('records')
        except Exception:
            pass

    updated_trades = []
    open_symbols = [t['Symbol'] for t in active_trades]

    # --- إدارة الصفقات النشطة ---
    for trade in active_trades:
        symbol = trade['Symbol']
        pionex_symbol = PIONEX_SYMBOLS.get(symbol, f"{symbol.replace('USDT', '_USDT')}")
        df = get_pionex_candles(pionex_symbol, interval="1m", limit=5)
        if df is None or df.empty:
            updated_trades.append(trade)
            continue
            
        curr_price = df.iloc[-1]['close']
        entry = trade['Entry']
        tp1 = trade['TP1']
        tp2 = trade['TP2']
        tp3 = trade['TP3']
        sl = trade['SL']
        qty = trade['Qty']
        side = trade['Side']
        hit_stage = int(trade.get('HitStage', 0))

        closed = False

        if side == "LONG":
            if curr_price <= sl:
                loss = (entry - sl) * qty if sl != entry else 0.0
                result_status = 'NEUTRAL' if sl == entry else 'LOSS'
                send_telegram_message(f"🛑 *Lightning Scalper: SL Hit (LONG {symbol})*\nالأثر: `-${loss:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': 'SL Hit', 'PnL': round(-loss, 2)})
                closed = True
            else:
                if hit_stage < 3 and curr_price >= tp3:
                    profit = (tp3 - entry) * qty
                    send_telegram_message(f"🎉 *Lightning Scalper: TP3 Hit (LONG {symbol})*\nربح: `+${profit:.2f}`")
                    save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp3, 'Result': 'WIN', 'Reason': 'TP3', 'PnL': round(profit, 2)})
                    closed = True
                elif hit_stage < 2 and curr_price >= tp2:
                    trade['HitStage'] = 2
                    trade['SL'] = tp1
                    send_telegram_message(f"🚀 *Lightning Scalper: TP2 Reached (LONG {symbol})*\nتم نقل وقف الخسارة إلى TP1 🔒")
                    updated_trades.append(trade)
                elif hit_stage < 1 and curr_price >= tp1:
                    trade['HitStage'] = 1
                    trade['SL'] = entry
                    send_telegram_message(f"📈 *Lightning Scalper: TP1 Reached (LONG {symbol})*\nتم تأمين الصفقة عند الدخول ✅")
                    updated_trades.append(trade)
                else:
                    if not closed and trade not in updated_trades:
                        updated_trades.append(trade)

        elif side == "SHORT":
            if curr_price >= sl:
                loss = (sl - entry) * qty if sl != entry else 0.0
                result_status = 'NEUTRAL' if sl == entry else 'LOSS'
                send_telegram_message(f"🛑 *Lightning Scalper: SL Hit (SHORT {symbol})*\nالأثر: `-${loss:.2f}`")
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': 'SL Hit', 'PnL': round(-loss, 2)})
                closed = True
            else:
                if hit_stage < 3 and curr_price <= tp3:
                    profit = (entry - tp3) * qty
                    send_telegram_message(f"🎉 *Lightning Scalper: TP3 Hit (SHORT {symbol})*\nربح: `+${profit:.2f}`")
                    save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp3, 'Result': 'WIN', 'Reason': 'TP3', 'PnL': round(profit, 2)})
                    closed = True
                elif hit_stage < 2 and curr_price <= tp2:
                    trade['HitStage'] = 2
                    trade['SL'] = tp1
                    send_telegram_message(f"🚀 *Lightning Scalper: TP2 Reached (SHORT {symbol})*\nتم نقل وقف الخسارة إلى TP1 🔒")
                    updated_trades.append(trade)
                elif hit_stage < 1 and curr_price <= tp1:
                    trade['HitStage'] = 1
                    trade['SL'] = entry
                    send_telegram_message(f"📉 *Lightning Scalper: TP1 Reached (SHORT {symbol})*\nتم تأمين الصفقة عند الدخول ✅")
                    updated_trades.append(trade)
                else:
                    if not closed and trade not in updated_trades:
                        updated_trades.append(trade)

    # --- استراتيجية الزخم الجديدة كلياً (EMA Crossover + RSI 7) ---
    for symbol, pionex_symbol in PIONEX_SYMBOLS.items():
        if len(updated_trades) >= 5:
            break  
        if symbol in open_symbols:
            continue
            
        df = get_pionex_candles(pionex_symbol, interval="1m", limit=30)
        if df is None or len(df) < 15:
            continue
            
        df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['ema13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], period=7)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        curr_price = curr['close']
        
        # شروط تقاطع EMA السريع (5 مع 13) مع مؤشر RSI
        is_long = (prev['ema5'] <= prev['ema13']) and (curr['ema5'] > curr['ema13']) and (curr['rsi'] > 45) and (curr['rsi'] < 70)
        is_short = (prev['ema5'] >= prev['ema13']) and (curr['ema5'] < curr['ema13']) and (curr['rsi'] < 55) and (curr['rsi'] > 30)

        if is_long:
            entry = curr_price
            sl = entry * 0.996  # وقف خسارة 0.4%
            risk_dist = entry - sl
            
            tp1 = entry + (risk_dist * 1.2)
            tp2 = entry + (risk_dist * 2.2)
            tp3 = entry + (risk_dist * 3.5)

            risk_amount = current_balance * BASE_RISK_PERCENTAGE
            max_margin = current_balance * MAX_TOTAL_MARGIN_RATIO
            qty = risk_amount / risk_dist if risk_dist > 0 else 1.0
            if ((entry * qty) / LEVERAGE) > max_margin:
                qty = (max_margin * LEVERAGE) / entry

            if qty > 0:
                new_trade = {
                    'Symbol': symbol, 'Side': 'LONG', 'Entry': entry,
                    'TP1': tp1, 'TP2': tp2, 'TP3': tp3, 'SL': sl, 'Qty': qty, 'HitStage': 0
                }
                updated_trades.append(new_trade)
                open_symbols.append(symbol)
                
                send_telegram_message(
                    f"⚡ *Lightning Scalper: LONG Signal (EMA Momentum)*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 الرمز: `{symbol}` | الدخول: `{entry:.4f}`\n"
                    f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}` | TP3: `{tp3:.4f}`\n"
                    f"🛑 Stop Loss: `{sl:.4f}`\n"
                    f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                )

        elif is_short:
            entry = curr_price
            sl = entry * 1.004  # وقف خسارة 0.4%
            risk_dist = sl - entry
            
            tp1 = entry - (risk_dist * 1.2)
            tp2 = entry - (risk_dist * 2.2)
            tp3 = entry - (risk_dist * 3.5)

            risk_amount = current_balance * BASE_RISK_PERCENTAGE
            max_margin = current_balance * MAX_TOTAL_MARGIN_RATIO
            qty = risk_amount / risk_dist if risk_dist > 0 else 1.0
            if ((entry * qty) / LEVERAGE) > max_margin:
                qty = (max_margin * LEVERAGE) / entry

            if qty > 0:
                new_trade = {
                    'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry,
                    'TP1': tp1, 'TP2': tp2, 'TP3': tp3, 'SL': sl, 'Qty': qty, 'HitStage': 0
                }
                updated_trades.append(new_trade)
                open_symbols.append(symbol)
                
                send_telegram_message(
                    f"⚡ *Lightning Scalper: SHORT Signal (EMA Momentum)*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 الرمز: `{symbol}` | الدخول: `{entry:.4f}`\n"
                    f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}` | TP3: `{tp3:.4f}`\n"
                    f"🛑 Stop Loss: `{sl:.4f}`\n"
                    f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                )

    if updated_trades:
        df_out = pd.DataFrame(updated_trades).drop_duplicates(subset=['Symbol'])
        df_out.to_csv(TRADE_FILE, index=False)
    else:
        if os.path.exists(TRADE_FILE):
            os.remove(TRADE_FILE)

    check_daily_report(len(updated_trades), current_balance)

if __name__ == "__main__":
    manage_and_scan_scalper_market()
