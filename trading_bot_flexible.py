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

# مفاتيح التيليجرام للبوت المرن (مضمنة افتراضياً)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "5620413191")

# إعدادات رأس المال والمخاطر
INITIAL_BALANCE = 200.0     
RISK_PERCENTAGE = 0.02     
LEVERAGE = 3     
MAX_TOTAL_MARGIN_RATIO = 0.6  # أقصى نسبة مسموح بها كإجمالي هوامش (60%)

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
            f"📊 *Flexible Fast Bot: التقرير اليومي الشامل*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ الوقت: `{now.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
            f"💰 الرصيد الحالي: `${current_balance:.2f}` (ROI: `{roi_percent:+.2f}%`)\n"
            f"📈 إجمالي الأرباح/الخسائر: `${total_pnl:+.2f}`\n"
            f"🎯 صفقات رابحة: `{wins}` | 🛑 صفقات خاسرة: `{losses}`\n"
            f"📂 الصفقات النشطة حالياً: `{active_trades_count} صفقات`\n"
            f"⚡ *الرافعة المستخدمة:* `{LEVERAGE}x` | *المخاطرة لكل صفقة:* `{RISK_PERCENTAGE*100}%`\n"
            f"🚀 *الحالة:* البوت المرن السريع يقتنص الفرص على فريم الـ 15 دقيقة بكفاءة مع الفلاتر المحسنة."
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

def get_coinbase_candles(product_id, granularity=900, limit=100):
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

def calculate_stoch_rsi(series, period=14, k_period=3, d_period=3):
    rsi = calculate_rsi(series, period)
    stoch_rsi = (rsi - rsi.rolling(window=period).min()) / (rsi.rolling(window=period).max() - rsi.rolling(window=period).min())
    stoch_k = stoch_rsi.rolling(window=k_period).mean() * 100
    stoch_d = stoch_k.rolling(window=d_period).mean() * 100
    return stoch_k, stoch_d

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

    # 1. إدارة الصفقات المفتوحة (LONG & SHORT) مع Trailing Stop وإرسال التفاصيل الشاملة
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
                msg = (
                    f"🔄 *Flexible Fast Trailing Stop Activated! (LONG {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 السعر الحالي: `{curr_price:.4f}` | سعر الدخول: `{entry:.4f}`\n"
                    f"🛡️ تم نقل وقف الخسارة إلى سعر الدخول للحماية.\n"
                    f"⚡ الرافعة: `{LEVERAGE}x` | 🎯 الهدف (TP): `{tp1:.4f}`"
                )
                send_telegram_message(msg)

            if curr_price >= tp1:
                profit = (tp1 - entry) * qty
                profit_percent = ((tp1 - entry) / entry) * 100 * LEVERAGE
                current_balance += profit
                msg = (
                    f"🎯 *Flexible Fast TP Reached! (LONG {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 سعر الدخول: `{entry:.4f}` | سعر الإغلاق: `{tp1:.4f}`\n"
                    f"🛑 وقف الخسارة السابق: `{sl:.4f}`\n"
                    f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                    f"💰 الربح المحقق: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n"
                    f"💵 الرصيد الإجمالي الجديد: `${current_balance:.2f}`"
                )
                send_telegram_message(msg)
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price <= sl:
                loss = (entry - sl) * qty
                loss_percent = ((entry - sl) / entry) * 100 * LEVERAGE
                current_balance -= loss
                msg = (
                    f"🛑 *Flexible Fast Stop Loss Hit! (LONG {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 سعر الدخول: `{entry:.4f}` | سعر الإغلاق: `{sl:.4f}`\n"
                    f"🎯 الهدف المقابل: `{tp1:.4f}`\n"
                    f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                    f"📉 الخسارة المحققة: `-${loss:.2f}` (`-{loss_percent:.2f}%`)\n"
                    f"💵 الرصيد الإجمالي الجديد: `${current_balance:.2f}`"
                )
                send_telegram_message(msg)
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True

        elif side == "SHORT":
            if curr_price <= (entry - (entry - tp1) * 0.5) and sl > entry:
                trade['SL'] = entry
                msg = (
                    f"🔄 *Flexible Fast Trailing Stop Activated! (SHORT {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 السعر الحالي: `{curr_price:.4f}` | سعر الدخول: `{entry:.4f}`\n"
                    f"🛡️ تم نقل وقف الخسارة إلى سعر الدخول للحماية.\n"
                    f"⚡ الرافعة: `{LEVERAGE}x` | 🎯 الهدف (TP): `{tp1:.4f}`"
                )
                send_telegram_message(msg)

            if curr_price <= tp1:
                profit = (entry - tp1) * qty
                profit_percent = ((entry - tp1) / entry) * 100 * LEVERAGE
                current_balance += profit
                msg = (
                    f"🎯 *Flexible Fast TP Reached! (SHORT {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 سعر الدخول: `{entry:.4f}` | سعر الإغلاق: `{tp1:.4f}`\n"
                    f"🛑 وقف الخسارة السابق: `{sl:.4f}`\n"
                    f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                    f"💰 الربح المحقق: `+${profit:.2f}` (`+{profit_percent:.2f}%`)\n"
                    f"💵 الرصيد الإجمالي الجديد: `${current_balance:.2f}`"
                )
                send_telegram_message(msg)
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': tp1, 'Result': 'WIN', 'PnL': round(profit, 2)})
                closed = True
            elif curr_price >= sl:
                loss = (sl - entry) * qty
                loss_percent = ((sl - entry) / entry) * 100 * LEVERAGE
                current_balance -= loss
                msg = (
                    f"🛑 *Flexible Fast Stop Loss Hit! (SHORT {symbol})*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 سعر الدخول: `{entry:.4f}` | سعر الإغلاق: `{sl:.4f}`\n"
                    f"🎯 الهدف المقابل: `{tp1:.4f}`\n"
                    f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                    f"📉 الخسارة المحققة: `-${loss:.2f}` (`-{loss_percent:.2f}%`)\n"
                    f"💵 الرصيد الإجمالي الجديد: `${current_balance:.2f}`"
                )
                send_telegram_message(msg)
                save_closed_trade({'Timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), 'Symbol': symbol, 'Side': side, 'Entry': entry, 'Exit': sl, 'Result': 'LOSS', 'PnL': round(-loss, 2)})
                closed = True

        if not closed:
            updated_trades.append(trade)

    # 2. فحص السوق وإرسال تفاصيل الإشارة الجديدة مع الفلاتر المحسنة
    if len(updated_trades) < 4:
        for symbol, coinbase_id in COINBASE_PRODUCTS.items():
            if symbol in open_symbols:
                continue
                
            df = get_coinbase_candles(coinbase_id, granularity=900, limit=60)
            if df is None or len(df) < 40:
                continue
                
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['stoch_k'], df['stoch_d'] = calculate_stoch_rsi(df['close'], 14, 3, 3)
            df['mid_band'], df['upper_band'], df['lower_band'] = calculate_bollinger_bands(df['close'], 20, 2)
            df['atr'] = calculate_atr(df, 14)
            
            curr_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]

            curr_price = curr_candle['close']
            curr_open = curr_candle['open']
            curr_low = curr_candle['low']
            curr_high = curr_candle['high']
            
            curr_rsi = curr_candle['rsi']
            curr_stoch_k = curr_candle['stoch_k']
            curr_stoch_d = curr_candle['stoch_d']
            prev_stoch_k = prev_candle['stoch_k']
            prev_stoch_d = prev_candle['stoch_d']

            lower_b = curr_candle['lower_band']
            upper_b = curr_candle['upper_band']
            mid_b = curr_candle['mid_band']
            curr_atr = curr_candle['atr']

            # قياس أذيال الشموع
            body_size = abs(curr_price - curr_open)
            lower_wick = min(curr_open, curr_price) - curr_low
            upper_wick = curr_high - max(curr_open, curr_price)

            # شروط التأكيد (Rejection / Reversal Candle)
            is_bullish_reversal = (curr_price > curr_open) or (lower_wick >= body_size and lower_wick > 0)
            is_bearish_reversal = (curr_price < curr_open) or (upper_wick >= body_size and upper_wick > 0)

            # تقاطعات Stochastic RSI
            stoch_golden_cross = (prev_stoch_k <= prev_stoch_d) and (curr_stoch_k > curr_stoch_d) and (curr_stoch_k < 35)
            stoch_death_cross = (prev_stoch_k >= prev_stoch_d) and (curr_stoch_k < curr_stoch_d) and (curr_stoch_k > 65)

            # --- شروط صفقات الشراء السريعة (LONG) ---
            if (curr_price <= lower_b * 1.008) and (curr_rsi < 45) and is_bullish_reversal and stoch_golden_cross:
                entry = curr_price
                sl = entry - (curr_atr * 1.5)
                calculated_tp = max(mid_b, entry + (entry - sl) * 1.5)
                tp1 = calculated_tp

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
                        f"🚀 *Flexible Fast Bot: New LONG Signal (Filtered)*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | نوع الصفقة: `LONG`\n"
                        f"📍 سعر الدخول (Entry): `{entry:.4f}`\n"
                        f"🎯 هدف الربح (TP): `{tp1:.4f}`\n"
                        f"🛑 وقف الخسارة (SL): `{sl:.4f}`\n"
                        f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                        f"🛡️ المخاطرة المحسوبة: `${risk_amount:.2f}` (`{RISK_PERCENTAGE*100}%`)\n"
                        f"📊 مؤشر RSI: `{curr_rsi:.1f}` | Stoch K/D: `{curr_stoch_k:.1f}/{curr_stoch_d:.1f}`\n"
                        f"💵 الهامش المستقطع: `${margin:.2f}` | الرصيد: `${current_balance:.2f}`"
                    )
                    send_telegram_message(msg)
                    break

            # --- شروط صفقات البيع السريعة (SHORT) ---
            elif (curr_price >= upper_b * 0.992) and (curr_rsi > 55) and is_bearish_reversal and stoch_death_cross:
                entry = curr_price
                sl = entry + (curr_atr * 1.5)
                calculated_tp = min(mid_b, entry - (sl - entry) * 1.5)
                tp1 = calculated_tp

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
                        f"📉 *Flexible Fast Bot: New SHORT Signal (Filtered)*\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 الرمز: `{symbol}` | نوع الصفقة: `SHORT`\n"
                        f"📍 سعر الدخول (Entry): `{entry:.4f}`\n"
                        f"🎯 هدف الربح (TP): `{tp1:.4f}`\n"
                        f"🛑 وقف الخسارة (SL): `{sl:.4f}`\n"
                        f"⚡ الرافعة المالية: `{LEVERAGE}x`\n"
                        f"🛡️ المخاطرة المحسوبة: `${risk_amount:.2f}` (`{RISK_PERCENTAGE*100}%`)\n"
                        f"📊 مؤشر RSI: `{curr_rsi:.1f}` | Stoch K/D: `{curr_stoch_k:.1f}/{curr_stoch_d:.1f}`\n"
                        f"💵 الهامش المستقطع: `${margin:.2f}` | الرصيد: `${current_balance:.2f}`"
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
