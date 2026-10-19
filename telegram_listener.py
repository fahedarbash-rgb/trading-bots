import os
import time
import logging
import requests
import pandas as pd

# --- إعداد نظام تسجيل الأخطاء ---
logging.basicConfig(
    filename='listener_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# قائمة توكنات البوتات الخمسة الخاصة بك
BOT_TOKENS = [
    "8733239782:AAFgTANZqzFSa1LF5E57_mPJIBOJIlHnou0",  # Lightning Scalper
    "8988832604:AAGbhIC3iKCnCmacPDicf9vmP_qF4ujwsY0",  # Global S&R
    "8678840548:AAFgx9th4C4lz-T3ThVwTEHr2uN-WOBmozo",  # Flexible
    "8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo",  # Strict
    "8772493944:AAGb4Y1VuBLrCq0vfvnhue7oRW4hjf_LYJE"   # Balanced
]

# تعيين إعدادات الملفات لكل بوت
BOT_CONFIGS = {
    "Lightning Scalper": {"initial": 200.0, "trade": "active_scalper_trades.csv", "closed": "closed_scalper_trades_history.csv"},
    "Global S&R": {"initial": 200.0, "trade": "active_global_trades.csv", "closed": "closed_global_trades_history.csv"},
    "Flexible": {"initial": 200.0, "trade": "active_flexible_trades.csv", "closed": "closed_flexible_trades_history.csv"},
    "Strict": {"initial": 200.0, "trade": "active_strict_trades.csv", "closed": "closed_strict_trades_history.csv"},
    "Balanced": {"initial": 200.0, "trade": "active_balanced_trades.csv", "closed": "closed_balanced_trades_history.csv"}
}

def get_fleet_balance_summary():
    """حساب وقراءة ملخص الأداء والإحصائيات لكل الأسطول"""
    msg = "📊 *ملخص أداء أسطول التداول الخارق*\n━━━━━━━━━━━━━━━━━━━\n"
    total_fleet_balance = 0.0
    total_fleet_pnl = 0.0

    for bot_name, config in BOT_CONFIGS.items():
        initial = config["initial"]
        current_bal = initial
        closed_file = config["closed"]
        wins, losses, pnl = 0, 0, 0.0

        if os.path.exists(closed_file):
            try:
                df = pd.read_csv(closed_file)
                if not df.empty and 'PnL' in df.columns:
                    pnl = df['PnL'].sum()
                    current_bal = initial + pnl
                    if 'Result' in df.columns:
                        wins = len(df[df['Result'] == 'WIN'])
                        losses = len(df[df['Result'] == 'LOSS'])
            except Exception as e:
                logging.error(f"Error reading {closed_file}: {e}")

        roi = ((current_bal - initial) / initial) * 100
        total_fleet_balance += current_bal
        total_fleet_pnl += pnl

        msg += (
            f"🤖 *{bot_name}:*\n"
            f" 💰 الرصيد: `${current_bal:.2f}` (ROI: `{roi:+.2f}%`)\n"
            f" 📈 PnL: `${pnl:+.2f}` | 🎯 رابحة: `{wins}` | 🛑 خاسرة: `{losses}`\n"
            f"-----------------------------------\n"
        )

    msg += f"💵 *إجمالي رصيد الأسطول:* `${total_fleet_balance:.2f}`\n"
    msg += f"📈 *إجمالي الأرباح الكلية:* `${total_fleet_pnl:+.2f}`"
    return msg

def get_fleet_active_trades():
    """قراءة وحصر جميع الصفقات النشطة حالياً عبر كل البوتات"""
    msg = "📂 *الصفقات النشطة حالياً عبر الأسطول*\n━━━━━━━━━━━━━━━━━━━\n"
    has_active = False

    for bot_name, config in BOT_CONFIGS.items():
        trade_file = config["trade"]
        if os.path.exists(trade_file):
            try:
                df = pd.read_csv(trade_file)
                if not df.empty:
                    has_active = True
                    msg += f"🤖 *{bot_name}:*\n"
                    for _, row in df.iterrows():
                        side_emoji = "🟢" if row.get('Side') == "LONG" else "🔴"
                        msg += (
                            f" {side_emoji} `{row.get('Symbol')}` ({row.get('Side')})\n"
                            f" 📍 الدخول: `{row.get('Entry'):.4f}` | 🛑 SL: `{row.get('SL'):.4f}`\n"
                            f" 🎯 TP1: `{row.get('TP1'):.4f}` | TP2: `{row.get('TP2'):.4f}`\n"
                        )
                    msg += "-----------------------------------\n"
            except Exception as e:
                logging.error(f"Error reading {trade_file}: {e}")

    if not has_active:
        msg += "✨ لا توجد صفقات نشطة حالياً عبر أي بوت. الأسطول يمسح السوق باحثاً عن فرص آمنة! 🛡️"
    
    return msg

def answer_callback_query(token, callback_query_id, text="تم تنفيذ الطلب"):
    """إبلاغ تيليجرام باستلام الضغطة على الزر والتجاوب معها"""
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
    except Exception as e:
        logging.error(f"Error answering callback: {e}")

def send_message(token, chat_id, text):
    """إرسال رد نصوص التيليجرام"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error sending listener response: {e}")

def poll_bot_updates(token, last_update_id):
    """الاستماع للرسائل والأزرار لكل توكن"""
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=3"
    try:
        res = requests.get(url, timeout=5).json()
        if res.get("ok") and res.get("result"):
            for update in res["result"]:
                last_update_id = update["update_id"]
                
                # التعامل مع الأزرار التفاعلية (Inline Keyboards)
                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb["id"]
                    cb_data = cb.get("data")
                    chat_id = cb["message"]["chat"]["id"]

                    answer_callback_query(token, cb_id)

                    if cb_data == "get_balance":
                        response = get_fleet_balance_summary()
                        send_message(token, chat_id, response)
                    elif cb_data == "get_active_trades":
                        response = get_fleet_active_trades()
                        send_message(token, chat_id, response)

                # التعامل مع الأوامر المكتوبة (مثل /balance أو /trades)
                elif "message" in update and "text" in update["message"]:
                    msg_text = update["message"]["text"].strip().lower()
                    chat_id = update["message"]["chat"]["id"]

                    if msg_text in ["/balance", "/status", "الرصيد", "التقرير"]:
                        response = get_fleet_balance_summary()
                        send_message(token, chat_id, response)
                    elif msg_text in ["/trades", "/active", "الصفقات"]:
                        response = get_fleet_active_trades()
                        send_message(token, chat_id, response)

    except Exception as e:
        pass
    return last_update_id

def run_listener():
    print("🚀 تم تشغيل مستمع الأسطول التفاعلي بنجاح... جاري الاستماع للأزرار والأوامر.")
    last_ids = {token: 0 for token in BOT_TOKENS}

    while True:
        for token in BOT_TOKENS:
            last_ids[token] = poll_bot_updates(token, last_ids[token])
        time.sleep(1)

if __name__ == "__main__":
    run_listener()
