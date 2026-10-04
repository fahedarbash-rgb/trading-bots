import os
import ccxt
import requests
import pandas as pd
from datetime import datetime

# استدعاء المفاتيح السرية بأمان من بيئة GitHub Actions
API_KEY = os.getenv('barOUYDIqwmkG0J2nRlEaDGxTcuevQD4vgLJOMfY0OlsHyqUDQq7PVKGyJCo2lgc')
SECRET_KEY = os.getenv('7ZSWeyoZ6ZtrYmO60OHh2n1XQEgrQOuZuhWMNFEiRiXwJq3OZAoL2YXYlrr1feEy')
TELEGRAM_BOT_TOKEN = os.getenv('8935193100:AAGGIvDsapewUqGO-Z0Faas46D0VNgGkQKo')
TELEGRAM_CHAT_ID = os.getenv('5620413191')

# دالة لإرسال التنبيهات والتقارير الفورية إلى تيليجرام
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("بيانات تيليجرام غير متوفرة في البيئة!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("تم إرسال التنبيه إلى تيليجرام بنجاح.")
        else:
            print(f"فشل إرسال التنبيه: {response.text}")
    except Exception as e:
        print(f"خطأ في الاتصال بتيليجرام: {e}")

# إعداد الاتصال ببيئة اختبار باينانس (Binance Futures Testnet)
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future', # الاعتماد على العقود الآجلة وفق خطتنا
    }
})

# تفعيل وضع Sandbox (الشبكة التجريبية)
exchange.set_sandbox_mode(True)

# قائمة الأصول الـ 11 المعتمدة في خطتنا للتداول
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'MATIC/USDT'
]

def run_trading_bot():
    try:
        print(f"--- بدء تشغيل دورة البوت في: {datetime.now()} ---")
        
        # فحص رصيد الحساب الوهمي والتأكد من سلامة الاتصال
        balance = exchange.fetch_balance()
        usdt_free = balance['USDT']['free']
        
        # فحص الأسعار وتحليل الأصول الـ 11 المدرجة في الخطة
        market_summary = ""
        for symbol in SYMBOLS:
            try:
                ticker = exchange.fetch_ticker(symbol)
                last_price = ticker['last']
                market_summary += `• *{symbol}*: \`${last_price}\` USDT\n`
            except Exception as ex:
                print(f"خطأ في جلب بيانات الزوج {symbol}: {ex}")

        # صياغة تقرير الحالة المتكامل
        report_msg = f"🤖 *تقرير بوت التداول الآلي (Testnet)*\n\n" \
                     f"✅ حالة الاتصال: متصل بنجاح\n" \
                     f"💰 رصيد USDT التجريبي المتاح: `{usdt_free}`\n\n" \
                     f"📊 *أسعار الأصول الـ 11 المراقبة الحالية:*\n{market_summary}\n" \
                     f"⏱ التوقيت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        print(report_msg)
        send_telegram_message(report_msg)

    except Exception as e:
        error_msg = f"❌ *خطأ رئيسي في تشغيل البوت*:\n`{e}`"
        print(error_msg)
        send_telegram_message(error_msg)

if __name__ == "__main__":
    run_trading_bot()
