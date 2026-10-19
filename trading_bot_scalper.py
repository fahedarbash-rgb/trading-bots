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

# بيانات بوت التيليجرام الخاص بالسكالبينج
TELEGRAM_BOT_TOKEN = "8733239782:AAFgTANZqzFSa1LF5E57_mPJIBOJIlHnou0"
TELEGRAM_CHAT_ID = "5620413191"

INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.015    
LEVERAGE = 5     # رافعة مالية 5x تناسب السكالبينج اللحظي السريع
MAX_TOTAL_MARGIN_RATIO = 0.6  

TRADE_FILE = "active_scalper_trades.csv"
CLOSED_FILE = "closed_scalper_trades_history.csv"
HEARTBEAT_FILE = "last_scalper_heartbeat.txt"

# رموز Pionex المتاحة على فريم الدقيقة (1m)
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
            f"⚡ *Lightning Scalper (5x - 1m): التقرير اليومي النشط*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"🚀 *الحالة:* البوت يعمل بكفاءة عالية عبر Pionex API."
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

def get_pionex_candles(symbol, interval="1m", limit=80):
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
            df = pd.DataFrame(df_list)
            return df
        return None
    except Exception as e:
        logging.error(f"Error fetching {symbol} from Pionex: {e}")
        return None

def calculate_rsi(series, period=9):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_stoch_rsi(series, period=9, k_period=3, d_period=3):
    rsi = calculate_rsi(series, period)
    stoch_rsi = (rsi - rsi.rolling(window=period).min()) / (rsi.rolling(window=period).max() - rsi.rolling(window=period).min())
    stoch_k = stoch_rsi.rolling(window=k_period).mean() * 100
    stoch_d = stoch_k.rolling(window=d_period).mean() * 100
    return stoch_k, stoch_d

def calculate_atr(df, period=10):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def manage_and_scan_scalper_market():
    current_balance = INITIAL_BALANCE
    if os.path.exists(CLOSED_FILE):
        try:
            df_closed = pd.read_csv(CLOSED_FILE)
            if not df_closed.empty and 'PnL' in df_closed.columns:
                current_balance = INITIAL_BALANCE + df_closed['PnL'].sum()
        except Exception as e:
            logging.error(f"Error reading closed history for scalper balance: {e}")

    active_trades = []
    if os.path.exists(TRADE_FILE):
        try:
            active_trades = pd.read_csv(TRADE_FILE).to_dict('records')
        except Exception:
            pass

    updated_trades = []
    open_symbols = [t['Symbol'] for t in active_trades]

    # إدارة الصفقات النشطة
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
        close_reason = ""

        if side == "LONG":
            if curr_price <= sl:
                if sl == entry:
                    loss, result_status, close_reason = 0.0, 'NEUTRAL', "SL Hit at Break-Even"
                else:
                    loss = (entry - sl) * qty
                    result_status, close_reason = 'LOSS', "SL Hit"

                send_telegram_message(
                    f"🛑 *Lightning Scalper: Stop Loss Hit! (LONG {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 دخول: `{entry:.4f}` | إغلاق: `{sl:.4f}` | السبب: `{close_reason}`\n"
                    f"📉 الأثر: `-${loss:.2f}`"
                )
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True
            else:
                if hit_stage < 3 and curr_price >= tp3:
                    profit = (tp3 - entry) * qty
                    close_reason = "TP3 Final Target Reached"
                    send_telegram_message(
                        f"🎉 *Lightning Scalper: TP3 Final Hit! (LONG {symbol})*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 دخول: `{entry:.4f}` | إغلاق: `{tp3:.4f}` | ربح: `+${profit:.2f}`"
                    )
                    save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp3, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                    closed = True
                elif hit_stage < 2 and curr_price >= tp2:
                    trade['HitStage'] = 2
                    trade['SL'] = entry
                    send_telegram_message(f"🚀 *Lightning Scalper TP2 Reached! (LONG {symbol})* - SL moved to Entry.")
                    updated_trades.append(trade)
                elif hit_stage < 1 and curr_price >= tp1:
                    trade['HitStage'] = 1
                    send_telegram_message(f"📈 *Lightning Scalper TP1 Reached! (LONG {symbol})*")
                    updated_trades.append(trade)
                else:
                    if not closed and trade not in updated_trades:
                        updated_trades.append(trade)

        elif side == "SHORT":
            if curr_price >= sl:
                if sl == entry:
                    loss, result_status, close_reason = 0.0, 'NEUTRAL', "SL Hit at Break-Even"
                else:
                    loss = (sl - entry) * qty
                    result_status, close_reason = 'LOSS', "SL Hit"

                send_telegram_message(
                    f"🛑 *Lightning Scalper: Stop Loss Hit! (SHORT {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 دخول: `{entry:.4f}` | إغلاق: `{sl:.4f}` | السبب: `{close_reason}`\n"
                    f"📉 الأثر: `-${loss:.2f}`"
                )
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': result_status, 'Reason': close_reason, 'PnL': round(-loss, 2)})
                closed = True
            else:
                if hit_stage < 3 and curr_price <= tp3:
                    profit = (entry - tp3) * qty
                    close_reason = "TP3 Final Target Reached"
                    send_telegram_message(
                        f"🎉 *Lightning Scalper: TP3 Final Hit! (SHORT {symbol})*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 دخول: `{entry:.4f}` | إغلاق: `{tp3:.4f}` | ربح: `+${profit:.2f}`"
                    )
                    save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp3, 'Result': 'WIN', 'Reason': close_reason, 'PnL': round(profit, 2)})
                    closed = True
                elif hit_stage < 2 and curr_price <= tp2:
                    trade['HitStage'] = 2
                    trade['SL'] = entry
                    send_telegram_message(f"🚀 *Lightning Scalper TP2 Reached! (SHORT {symbol})* - SL moved to Entry.")
                    updated_trades.append(trade)
                elif hit_stage < 1 and curr_price <= tp1:
                    trade['HitStage'] = 1
                    send_telegram_message(f"📉 *Lightning Scalper TP1 Reached! (SHORT {symbol})*")
                    updated_trades.append(trade)
                else:
                    if not closed and trade not in updated_trades:
                        updated_trades.append(trade)

    if os.path.exists(CLOSED_FILE):
        try:
            df_closed = pd.read_csv(CLOSED_FILE)
            if not df_closed.empty and 'PnL' in df_closed.columns:
                current_balance = INITIAL_BALANCE + df_closed['PnL'].sum()
        except Exception as e:
            logging.error(f"Error recalculating balance after trade close: {e}")

    # --- المسح الشامل المفتوح لجميع العملات لفحص واصطياد الفرص ---
    for symbol, pionex_symbol in PIONEX_SYMBOLS.items():
        if len(updated_trades) >= 5:
            break  # الحد الأقصى 5 صفقات نشطة
        if symbol in open_symbols:
            continue
            
        df = get_pionex_candles(pionex_symbol, interval="1m", limit=80)
        if df is None or len(df) < 30:
            continue
            
        df['rsi'] = calculate_rsi(df['close'], 9)
        df['stoch_k'], df['stoch_d'] = calculate_stoch_rsi(df['close'], 9, 3, 3)
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['atr'] = calculate_atr(df, 10)
        
        for i in [-1, -2, -3, -4, -5]:
            if abs(i) >= len(df):
                continue
            curr_candle = df.iloc[i]
            prev_candle = df.iloc[i-1]

            curr_price = curr_candle['close']
            curr_stoch_k = curr_candle['stoch_k']
            curr_stoch_d = curr_candle['stoch_d']
            prev_stoch_k = prev_candle['stoch_k']
            prev_stoch_d = prev_candle['stoch_d']
            ema9 = curr_candle['ema9']
            curr_atr = curr_candle['atr']

            stoch_golden_cross = (prev_stoch_k <= prev_stoch_d) and (curr_stoch_k > curr_stoch_d) and (curr_stoch_k < 75)
            stoch_death_cross = (prev_stoch_k >= prev_stoch_d) and (curr_stoch_k < curr_stoch_d) and (curr_stoch_k > 25)

            # SHORT 1m
            if (curr_price <= ema9 * 1.003) and stoch_death_cross:
                entry = curr_price
                sl = entry + max(curr_atr * 1.0, entry * 0.0015)
                risk_dist = sl - entry
                
                tp1 = entry - (risk_dist * 0.9)
                tp2 = entry - (risk_dist * 1.6)
                tp3 = entry - (risk_dist * 2.4)

                risk_amount = current_balance * RISK_PERCENTAGE
                max_margin = current_balance * MAX_TOTAL_MARGIN_RATIO
                
                qty = risk_amount / risk_dist if risk_dist > 0 else 1.0
                if ((entry * qty) / LEVERAGE) > max_margin:
                    qty = (max_margin * LEVERAGE) / entry

                if entry > tp3 and qty > 0:
                    new_trade = {
                        'Symbol': symbol, 'Side': 'SHORT', 'Entry': entry,
                        'TP1': tp1, 'TP2': tp2, 'TP3': tp3, 'SL': sl, 'Qty': qty, 'HitStage': 0
                    }
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    
                    send_telegram_message(
                        f"⚡ *Lightning Scalper: SHORT Signal (5x)*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | الدخول: `{entry:.4f}`\n"
                        f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}` | TP3: `{tp3:.4f}`\n"
                        f"🛑 Stop Loss: `{sl:.4f}`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                    )
                    break # الانتقال للعملة التالية بعد إيجاد صفقة لهذه العملة

            # LONG 1m
            elif (curr_price >= ema9 * 0.997) and stoch_golden_cross:
                entry = curr_price
                sl = entry - max(curr_atr * 1.0, entry * 0.0015)
                risk_dist = entry - sl
                
                tp1 = entry + (risk_dist * 0.9)
                tp2 = entry + (risk_dist * 1.6)
                tp3 = entry + (risk_dist * 2.4)

                risk_amount = current_balance * RISK_PERCENTAGE
                max_margin = current_balance * MAX_TOTAL_MARGIN_RATIO
                
                qty = risk_amount / risk_dist if risk_dist > 0 else 1.0
                if ((entry * qty) / LEVERAGE) > max_margin:
                    qty = (max_margin * LEVERAGE) / entry

                if tp3 > entry and qty > 0:
                    new_trade = {
                        'Symbol': symbol, 'Side': 'LONG', 'Entry': entry,
                        'TP1': tp1, 'TP2': tp2, 'TP3': tp3, 'SL': sl, 'Qty': qty, 'HitStage': 0
                    }
                    updated_trades.append(new_trade)
                    open_symbols.append(symbol)
                    
                    send_telegram_message(
                        f"⚡ *Lightning Scalper: LONG Signal (5x)*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | الدخول: `{entry:.4f}`\n"
                        f"🎯 TP1: `{tp1:.4f}` | TP2: `{tp2:.4f}` | TP3: `{tp3:.4f}`\n"
                        f"🛑 Stop Loss: `{sl:.4f}`\n"
                        f"💵 الرصيد الحالي: `${current_balance:.2f}`"
                    )
                    break # الانتقال للعملة التالية بعد إيجاد صفقة لهذه العملة

    if updated_trades:
        df_out = pd.DataFrame(updated_trades).drop_duplicates(subset=['Symbol'])
        df_out.to_csv(TRADE_FILE, index=False)
    else:
        if os.path.exists(TRADE_FILE):
            os.remove(TRADE_FILE)

    check_daily_report(len(updated_trades), current_balance)

if __name__ == "__main__":
    manage_and_scan_scalper_market()
