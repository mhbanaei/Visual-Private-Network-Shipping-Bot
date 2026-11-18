# Full corrected bot file.
# Fix applied: removed SERVICE_DETAILS_PLAN_ from config_name_conv_handler entry points so
# selecting a plan shows its details first; only CONFIRM_* callbacks start the purchase conversation.
# Other fixes from previous iterations (avoid ReplyKeyboardMarkup in edit_message_text, avoid Markdown parse issues) preserved.

import db as storage
import logging
import html
import requests
import json
import os
import io
import re 
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters, ApplicationBuilder
)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Bot, error, InputFile
import uuid 
import base64 
import time
import datetime 

# --- تنظیمات لاگ‌گیری ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================================
# --- متغیرهای کلیدی: تنظیمات سرورها ---
# ==========================================================

# 🌟 تنظیمات چند سرور (دست نخورده)
from servers import SERVERS_CONFIG

# تنظیمات اولیه 
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_CHAT_IDS = [123456789, 987654321]
ZARINPAL_MERCHANT_ID = "ZARINPAL_MERCHANT_ID"

# ⚠️ تنظیمات پروتکل VMESS
def get_protocol_settings(server_key):
    """بازگشت تنظیمات پروتکل برای سرور مشخص"""
    server_config = SERVERS_CONFIG[server_key]
    return {
        "add": server_config["server_address"],
        "port": server_config["server_port_client"],
        "id": "",
        "aid": 0,
        "net": "ws",
        "type": "none",
        "host": server_config["server_address"],
        "path": "/ws",
        "tls": "tls",
        "sni": server_config["server_address"],
        "scy": "auto",
        "v": "2"
    }

# --- وضعیت‌های Conversation ---
STATE_GET_AMOUNT = 1
STATE_GET_TICKET = 2
STATE_WAITING_FOR_CONFIG_NAME = 3
STATE_WAITING_FOR_CONFIG_NAME_CONFIRM = 4
STATE_WAITING_FOR_RENEWAL_NAME = 5
STATE_WAITING_FOR_RENEWAL_CONFIRM = 6
STATE_SELECT_SERVER = 7  
STATE_SELECT_SERVER_FOR_RENEWAL = 8 

# --- فایل‌های ذخیره‌سازی دائمی ---
PENDING_PAYMENTS_FILE = 'pending_payments.json'
USERS_FILE = 'users.json'

# --- تنظیمات زرین‌پال ---
ZARINPAL_WEBSERVICE = 'https://api.zarinpal.com/pg/v4/payment/request.json'
ZARINPAL_VERIFY_WEBSERVICE = 'https://api.zarinpal.com/pg/v4/payment/verify.json'
ZARINPAL_STARTPAY = 'https://www.zarinpal.com/pg/StartPay/'

# --- لیست قیمت نهایی (واحد: تومان) ---
SERVICES = {
}

# -*- coding: utf-8 -*-
# محتوای بخش آموزش — محور آموزش: هسته V2Ray و برنامه‌های پشتیبان آن

CONNECTION_TUTORIALS = {
    "v2rayng_android": {
        "title": "📱 آموزش اتصال با V2rayNG (Android)",
        "category": "android",
        "steps": [
            "🔧 هسته: V2Ray (پروتکل VLESS/VMess)",
            "💵 هزینه: کاملاً رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، SOCKS و لینک اشتراک (Subscription)",
            "",
            "1. برنامه V2rayNG را از لینک زیر دانلود کنید:",
            "https://github.com/2dust/v2rayNG/releases/download/1.10.26/v2rayNG_1.10.26_universal.apk",
            "(آخرین نسخه APK را دانلود و نصب کنید)",
            "",
            "2. برنامه را باز کرده و روی علامت ➕ در بالا سمت راست کلیک کنید.",
            "3. گزینه 'Import config from clipboard' را انتخاب کنید.",
            "4. لینک کانفیگ یا لینک اشتراک خود را از ربات کپی کرده و paste کنید.",
            "5. کانفیگ در لیست ظاهر می‌شود؛ روی آن کلیک کنید.",
            "6. دکمه V در پایین صفحه را فشار دهید تا اتصال برقرار شود.",
            "7. برای قطع اتصال، دوباره روی دکمه V کلیک کنید.",
            "",
            "📌 نکات مهم:",
            "• تاریخ و ساعت دستگاه باید دقیق باشد، وگرنه اتصال برقرار نمی‌شود.",
            "• در صورت خطا، برنامه را یکبار ببندید و مجدداً باز کنید.",
        ],
    },
    "v2raytun_android": {
        "title": "📱 آموزش اتصال با V2RayTun (Android)",
        "category": "android",
        "steps": [
            "🔧 هسته: V2Ray (نسخه جدید با پشتیبانی از همه پروتکل‌ها)",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، WireGuard و لینک اشتراک",
            "",
            "1. برنامه V2RayTun را از Google Play نصب کنید.",
            "2. برنامه را باز کرده و روی ➕ کلیک کنید.",
            "3. گزینه 'Import from clipboard' را بزنید.",
            "4. لینک اشتراک یا لینک مستقیم کانفیگ را paste کنید.",
            "5. دکمه اتصال را روشن کنید و درخواست VPN را Allow کنید.",
            "",
            "📌 نکات مهم:",
            "• برای به‌روزرسانی خودکار کانفیگ‌ها، از لینک اشتراک استفاده کنید.",
            "• اگر لیست کانفیگ‌ها خالی ماند، یکبار Update را بزنید.",
        ],
    },
    "v2box_ios": {
        "title": "📱 آموزش اتصال با V2Box (iOS)",
        "category": "ios",
        "steps": [
            "🔧 هسته: V2Ray (VLESS/VMess/Trojan)",
            "💵 هزینه V2Box: رایگان — نسخه iOS در App Store رایگان است و برای استفاده کامل ممکن است خرید درون‌برنامه‌ای (In-App Purchase) داشته باشد.",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، SOCKS، Subscription",
            "",
            "1. برنامه V2Box را از App Store دانلود و نصب کنید:",
            "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690",
            "",
            "2. لینک اشتراک یا لینک کانفیگ را از ربات کپی کنید.",
            "3. برنامه را باز کرده و روی علامت ➕ در بالا سمت راست کلیک کنید.",
            "4. گزینه 'Import from Clipboard' را انتخاب کنید.",
            "5. لینک را paste کنید و کانفیگ را انتخاب کنید.",
            "6. روی دکمه 'Connect' در پایین صفحه کلیک کنید.",
            "7. اگر پیام 'VPN Configuration' ظاهر شد، روی 'Allow' کلیک کنید.",
            "",
            "📌 نکات مهم:",
            "• اگر اتصال برقرار نشد، برنامه را ببندید و دوباره باز کنید.",
            "• برای حذف تبلیغات/امکانات بیشتر، نسخه Pro قابل خرید است.",
        ],
    },
    "v2raytun_ios": {
        "title": "📱 آموزش اتصال با V2RayTun (iOS)",
        "category": "ios",
        "steps": [
            "🔧 هسته: V2Ray",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، WireGuard، Subscription",
            "",
            "1. برنامه V2RayTun را از App Store نصب کنید.",
            "2. روی ➕ بزنید و 'Import from clipboard' را انتخاب کنید.",
            "3. لینک اشتراک یا کانفیگ را paste کنید.",
            "4. اتصال را روشن کنید و اجازه VPN را بدهید.",
            "",
            "📌 نکات مهم:",
            "• V2RayTun و V2Box هر دو هسته V2Ray دارند؛ اگر یکی مشکل داشت، دیگری را امتحان کنید.",
        ],
    },
    "hiddify_android": {
        "title": "📱 آموزش اتصال با Hiddify (Android)",
        "category": "android",
        "steps": [
            "🔧 هسته: چندگانه (V2Ray/Xray + Sing-box)",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، Hysteria، TUIC و لینک اشتراک",
            "",
            "1. برنامه Hiddify را از Google Play نصب کنید:",
            "https://play.google.com/store/apps/details?id=app.hiddify.com&hl=en",
            "2. برنامه را باز کرده و روی علامت ➕ کلیک کنید.",
            "3. گزینه 'Add from Clipboard' را انتخاب کنید.",
            "4. لینک اشتراک خود را paste کنید و Add را بزنید.",
            "5. دکمه روشن/خاموش کنار کانفیگ را فعال کنید.",
            "",
            "📌 نکات مهم:",
            "• این برنامه خودکار بهترین پروتکل را انتخاب می‌کند.",
        ],
    },
    "hiddify_ios": {
        "title": "📱 آموزش اتصال با Hiddify (iOS)",
        "category": "ios",
        "steps": [
            "🔧 هسته: چندگانه (V2Ray/Xray + Sing-box)",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، Hysteria، TUIC و لینک اشتراک",
            "",
            "1. برنامه Hiddify را از App Store نصب کنید:",
            "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532",
            "2. روی ➕ بزنید و 'Add from Clipboard' را انتخاب کنید.",
            "3. لینک اشتراک را paste کرده و Add را بزنید.",
            "4. دکمه روشن/خاموش کنار کانفیگ را فعال کنید.",
        ],
    },
    "v2rayn_windows": {
        "title": "💻 آموزش اتصال با V2rayN (Windows)",
        "category": "windows",
        "steps": [
            "🔧 هسته: V2Ray/Xray",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، Subscription",
            "",
            "1. برنامه V2rayN را از لینک زیر دانلود کنید:",
            "https://github.com/2dust/v2rayN/releases/download/7.16.6/v2rayN-windows-64.zip",
            "2. فایل ZIP را Extract کنید و برنامه را اجرا کنید.",
            "3. پیش‌نیازهای برنامه (در صورت نمایش) را نصب کنید.",
            "4. لینک کانفیگ را کپی کرده و در برنامه با CTRL+V وارد کنید.",
            "5. از بخش System Proxy گزینه 'Set System Proxy' را بزنید.",
            "6. برای قطع اتصال، 'Clear System Proxy' را انتخاب کنید.",
        ],
    },
    "hiddify_windows": {
        "title": "💻 آموزش اتصال با Hiddify (Windows)",
        "category": "windows",
        "steps": [
            "🔧 هسته: چندگانه (V2Ray/Xray + Sing-box)",
            "💵 هزینه: رایگان",
            "✅ کانفیگ‌های پشتیبانی‌شده: VLESS، VMess، Trojan، Shadowsocks، Hysteria، TUIC، Subscription",
            "",
            "1. برنامه Hiddify را از لینک زیر دانلود کنید:",
            "https://github.com/hiddify/hiddify-next/releases/latest/download/Hiddify-Windows-Setup-x64.exe",
            "2. برنامه را نصب و باز کنید.",
            "3. روی ➕ بزنید و 'Add from Clipboard' را انتخاب کنید.",
            "4. لینک اشتراک را paste کنید و Add را بزنید.",
            "5. دکمه روشن/خاموش کنار کانفیگ را فعال کنید.",
            "",
            "⚠️ نکته: برای عملکرد بهتر، آنتی‌ویروس را موقتاً غیرفعال کنید.",
        ],
    },
    "general_tips": {
        "title": "📌 نکات کلی و عیب‌یابی",
        "category": "tips",
        "steps": [
            "🔹 مشکلات رایج و راه‌حل‌ها:",
            "",
            "1. کانفیگ کار نمی‌کند:",
            "   • تاریخ و ساعت دستگاه خود را بررسی کنید (باید دقیق باشد).",
            "   • کانفیگ منقضی نشده باشد.",
            "   • حجم کانفیگ تمام نشده باشد.",
            "",
            "2. سرعت کم است:",
            "   • موقعیت جغرافیایی خود را بررسی کنید.",
            "   • از شبکه اینترنت دیگری تست کنید.",
            "",
            "3. قطع و وصل می‌شود:",
            "   • در Android: Settings > Apps > [App Name] > Battery > Unrestricted",
            "   • از شبکه پایدارتری استفاده کنید.",
            "",
            "4. برنامه crash می‌کند:",
            "   • برنامه را حذف و مجدداً نصب کنید.",
            "   • از آخرین نسخه برنامه استفاده کنید.",
            "",
            "5. اگر مشکل حل نشد، از دکمه '📞 پشتیبانی' استفاده کنید.",
        ],
    },
    "supported_apps": {
        "title": "📋 برنامه‌های پشتیبانی‌شده",
        "category": "tips",
        "steps": [
            "این سرویس با هسته V2Ray کار می‌کند و کانفیگ‌های VLESS/VMess/Trojan قابل استفاده در این برنامه‌ها هستند:",
            "",
            "🔹 Android:",
            "• V2rayNG — رایگان",
            "• V2RayTun — رایگان",
            "• Hiddify — رایگان",
            "• NekoBox — رایگان",
            "• v2rayNG (نسخه‌های فورک) — رایگان",
            "",
            "🔹 iOS:",
            "• V2Box — رایگان (با خرید درون‌برنامه‌ای اختیاری)",
            "• V2RayTun — رایگان",
            "• Hiddify — رایگان",
            "• Streisand — رایگان",
            "• Shadowrocket — پولی (خرید از App Store)",
            "",
            "🔹 Windows:",
            "• V2rayN — رایگان",
            "• Hiddify — رایگان",
            "• Nekoray — رایگان",
            "",
            "🔹 macOS:",
            "• V2Box — رایگان",
            "• V2rayU — رایگان",
            "• Hiddify — رایگان",
            "",
            "✅ همه این برنامه‌ها لینک اشتراک (Subscription) را پشتیبانی می‌کنند؛ کافی است لینک اشتراک ربات را وارد کنید تا کانفیگ خودکار اضافه شود.",
        ],
    },
}

TUTORIAL_CATEGORIES = {
    "android": {
        "title": "📱 آموزش برای Android",
        "apps": [
            {"name": "V2rayNG (توصیه شده)", "key": "v2rayng_android"},
            {"name": "V2RayTun", "key": "v2raytun_android"},
            {"name": "Hiddify", "key": "hiddify_android"},
        ],
    },
    "ios": {
        "title": "📱 آموزش برای iOS",
        "apps": [
            {"name": "V2Box (توصیه شده)", "key": "v2box_ios"},
            {"name": "V2RayTun", "key": "v2raytun_ios"},
            {"name": "Hiddify", "key": "hiddify_ios"},
        ],
    },
    "windows": {
        "title": "💻 آموزش برای Windows",
        "apps": [
            {"name": "V2rayN (توصیه شده)", "key": "v2rayn_windows"},
            {"name": "Hiddify", "key": "hiddify_windows"},
        ],
    },
    "tips": {
        "title": "📌 نکات کلی و عیب‌یابی",
        "apps": [
            {"name": "برنامه‌های پشتیبانی‌شده", "key": "supported_apps"},
            {"name": "مشکلات رایج و راه‌حل", "key": "general_tips"},
        ],
    },
}

# --- دکمه‌های منوی اصلی ---
MAIN_MENU_KEYBOARD = [
    ["🛍️ خرید سرویس (انتخاب پلن)"],
    ["📂 سرویس‌های من", "👤 حساب من"],
    ["💰 شارژ کیف پول", "📞 پشتیبانی"],
    ["📚 آموزش اتصال"],
]
MAIN_MENU_REPLY_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

# ============================================================
# --- قیمت‌گذاری سفارشی (خرید بی‌نهایت / حجمی) ---
# ============================================================
UNLIMITED_PRICE_PER_USER = 400000      # سرویس بی‌نهایت: هر کاربر ۴۰۰ هزار تومان
VOLUME_PRICE_PER_GB = 2000             # سرویس حجمی: هر گیگ ۲ هزار تومان
VOLUME_MAX_GB = 100                    # حداکثر حجم قابل خرید
CUSTOM_MAX_USERS = 10                  # حداکثر کاربر (بر اساس IP)
CUSTOM_USER_MULTIPLIER = 1.3           # ضریب تصاعدی قیمت برای هر کاربر اضافه
CUSTOM_DAYS = 30                       # اعتبار سرویس سفارشی
STATE_CUSTOM_BUILD = 15                # وضعیت ساخت سرویس سفارشی
CUSTOM_PLANS = {}                      # پلن‌های سفارشی ساخته‌شده در همین اجرا

# دیکشنری برای نگهداری Cookie هر سرور
XUI_AUTH_COOKIES = {}

# -------------------------
# Helper to send main menu
# -------------------------
async def send_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(chat_id=chat_id, text="یک گزینه را انتخاب کنید:", reply_markup=MAIN_MENU_REPLY_MARKUP)
    except Exception as e:
        logger.error(f"Failed to send main menu to {chat_id}: {e}")

# ============================================================
# --- توابع مدیریت دیتابیس کاربران (JSON) ---
# ============================================================

def load_users() -> dict:
    return storage.load_users()
def save_users(users: dict):
    storage.save_users(users)
def get_user_balance(user_id: int) -> float:
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": []}
        save_users(users)
        return 0.0
    
    return users[str_user_id].get("balance", 0.0)

def update_user_balance(user_id: int, amount_change: float):
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": []}
    
    current_balance = users[str_user_id]["balance"]
    new_balance = current_balance + amount_change
    users[str_user_id]["balance"] = new_balance
    
    save_users(users)
    return new_balance

def add_user_service(user_id: int, config_name: str, sub_link: str, uuid: str, internal_key: str, server_key: str):
    """ذخیره جزئیات کانفیگ خریداری شده همراه با شناسه سرور"""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users or 'services' not in users[str_user_id]:
        users[str_user_id] = {"balance": users.get(str_user_id, {}).get("balance", 0.0), "services": []}
    
    if not any(s['config_name'] == config_name for s in users[str_user_id]['services']):
        users[str_user_id]['services'].append({
            'config_name': config_name,
            'sub_link': sub_link,
            'uuid': uuid,
            'internal_key': internal_key,
            'server_key': server_key,
            'purchase_date': datetime.datetime.now().isoformat()
        })
        save_users(users)
        logger.info(f"New service added for user {user_id}: {config_name} on {server_key}")

def get_user_services(user_id: int) -> list:
    users = load_users()
    return users.get(str(user_id), {}).get('services', [])

def update_user_service_key(user_id: int, config_name: str, new_key: str, new_value: any):
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id in users and 'services' in users[str_user_id]:
        for service in users[str_user_id]['services']:
            if service['config_name'] == config_name:
                service[new_key] = new_value
                save_users(users)
                return True
    return False

# ============================================================
# --- توابع مدیریت پرداخت در انتظار (JSON) ---
# ============================================================

def load_pending_payments() -> dict:
    if not os.path.exists(PENDING_PAYMENTS_FILE): return {}
    try:
        with open(PENDING_PAYMENTS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError): return {}

def save_pending_payments(payments: dict):
    with open(PENDING_PAYMENTS_FILE, 'w') as f:
        json.dump(payments, f, indent=4, ensure_ascii=False)

def add_pending_payment(authority: str, user_id: int, amount_rial: int):
    payments = load_pending_payments()
    payments[authority] = {'user_id': user_id, 'amount': amount_rial}
    save_pending_payments(payments)

def get_pending_payment(authority: str) -> tuple[int | None, int | None]:
    payments = load_pending_payments()
    payment_info = payments.get(authority)
    if payment_info:
        user_id = int(payment_info.get('user_id'))
        amount = int(payment_info.get('amount'))
        return user_id, amount
    return None, None

def remove_pending_payment(authority: str):
    payments = load_pending_payments()
    if authority in payments:
        del payments[authority]
        save_pending_payments(payments)

# ============================================================
# --- توابع اتصال به درگاه پرداخت (منتقل شده از فایل 1) ---
# ============================================================

async def zarinpal_create_request(user_id: int, amount_rial: int, description: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, str | None]:
    logger.info(f"Creating Zarinpal request for {user_id} with amount {amount_rial} Rials")
    try:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        if not bot_username:
            logger.error("Bot does not have a username, Zarinpal callback might fail.")
            await context.bot.send_message(user_id, "❌ خطای پیکربندی: ربات نام کاربری ندارد. لطفاً با ادمین تماس بگیرید.")
            return None, None
    except Exception as e:
        logger.error(f"Failed to get bot username from Telegram: {e}")
        return None, None
    
    callback_url = f"https://t.me/{bot_username}?start=verify_"
    req_data = {"merchant_id": ZARINPAL_MERCHANT_ID, "amount": amount_rial, "description": description, "callback_url": callback_url}
    
    try:
        response = requests.post(ZARINPAL_WEBSERVICE, json=req_data, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('data') and data['data'].get('authority'):
            authority = data['data']['authority']
            if data['data'].get('code') == 100:
                payment_url = f"{ZARINPAL_STARTPAY}{authority}"
                add_pending_payment(authority, user_id, amount_rial)
                return payment_url, authority
            logger.error(f"Zarinpal Request Failed (Code {data['data'].get('code')}): {data}")
            return None, None
        error_code = data.get('errors', {}).get('code', 'Unknown')
        logger.error(f"Zarinpal API Error: {error_code} - {data}")
        return None, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Zarinpal: {e}")
        return None, None

async def zarinpal_verify_request(authority: str, amount_rial: int) -> bool:
    req_data = {"merchant_id": ZARINPAL_MERCHANT_ID, "authority": str(authority), "amount": int(amount_rial)}
    try:
        response = requests.post(ZARINPAL_VERIFY_WEBSERVICE, json=req_data, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('data') and data['data'].get('code'):
            code = data['data']['code']
            if code in [100, 101]: return True
        logger.error(f"Zarinpal Verification Failed (Code {data['data'].get('code')}): {data}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Zarinpal for verification: {e}")
        return False

async def verify_zarinpal_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, authority: str, expected_amount_rial: int) -> None:
    if hasattr(update, 'effective_chat'): user_id = update.effective_chat.id
    elif hasattr(update, 'chat'): user_id = update.chat.id
    elif hasattr(update, 'from_user'): user_id = update.from_user.id
    else:
        logger.error("Could not determine user_id in verify_zarinpal_payment_callback"); return
    
    if hasattr(update, 'effective_user'): effective_user = update.effective_user
    elif hasattr(update, 'from_user'): effective_user = update.from_user
    else: effective_user = None

    success = await zarinpal_verify_request(authority, expected_amount_rial)

    if success:
        charge_amount_toman = expected_amount_rial / 10
        new_balance = update_user_balance(user_id, charge_amount_toman)
        remove_pending_payment(authority)

        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ پرداخت شما با موفقیت تایید شد.\n"
            f"مبلغ {charge_amount_toman:,.0f} تومان به کیف پول شما اضافه شد.\n\n"
            f"موجودی جدید: {new_balance:,.0f} تومان",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        if effective_user:
            for admin_id in ADMIN_CHAT_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"شارژ موفق کیف پول:\nکاربر: {effective_user.first_name} (ID: {user_id})\nمبلغ: {charge_amount_toman:,.0f} تومان"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ پرداخت شما تایید نشد.\nلطفاً در صورت کسر وجه، کد پیگیری را به پشتیبانی ارسال کنید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )

# ============================================================
# --- توابع API پنل X-UI (سیستم چند سروره) ---
# ============================================================

# ============================================================
# --- توابع API پنل 3x-ui (نسخه جدید MHSanaei + سازگاری با نسخه قدیمی) ---
# ============================================================

XUI_CSRF_TOKENS = {}

def _xui_cfg(server_key: str) -> dict:
    return SERVERS_CONFIG.get(server_key, {}) or {}

def _xui_base_url(server_key: str) -> str:
    """آدرس پایه پنل (panel_url + web base path) بدون تکرار base path"""
    from urllib.parse import urlsplit

    cfg = _xui_cfg(server_key)
    panel_url = str(cfg.get('xui_panel_url') or '').strip().rstrip('/')
    base_path = str(cfg.get('base_path') or '').strip()
    if base_path.lower() in ('', '/', 'base_path', '/base_path', 'login_path', '/login_path'):
        base_path = ''
    if base_path:
        if not base_path.startswith('/'):
            base_path = '/' + base_path
        base_path = base_path.rstrip('/')
        # اگر base path قبلاً داخل xui_panel_url آمده باشد، دوباره اضافه نشود
        if urlsplit(panel_url).path.rstrip('/').endswith(base_path):
            base_path = ''
    return panel_url + base_path

def _xui_login_urls(server_key: str) -> list:
    """آدرس‌های احتمالی login (نسخه جدید: /login زیر base path)"""
    cfg = _xui_cfg(server_key)
    panel_url = str(cfg.get('xui_panel_url') or '').strip().rstrip('/')
    urls = []
    login_path = str(cfg.get('login_path') or '').strip()
    if login_path and login_path not in ('/', 'login_path'):
        if not login_path.startswith('/'):
            login_path = '/' + login_path
        urls.append(panel_url + login_path)
    urls.append(_xui_base_url(server_key) + '/login')
    urls.append(panel_url + '/login')
    unique = []
    for url in urls:
        if url and url not in unique:
            unique.append(url)
    return unique

def _xui_extract_cookie_header(response) -> str:
    pairs = []
    try:
        for key, value in response.cookies.items():
            if str(key).lower() == 'lang':
                continue
            pairs.append(f"{key}={value}")
    except Exception:
        pairs = []
    if pairs:
        return '; '.join(pairs)
    header = response.headers.get('set-cookie', '') or ''
    for name in ('3x-ui', 'session', 'x_session', 'panel_session'):
        match = re.search(name + r'=([^;,\s]+)', header, re.IGNORECASE)
        if match:
            return f"{name}={match.group(1)}"
    return ''

def _xui_payload(response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}

def _xui_auth_headers(server_key: str):
    """هدرهای احراز هویت: API Token یا کوکی session"""
    cfg = _xui_cfg(server_key)
    token = str(cfg.get('api_token') or '').strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    cookie = XUI_AUTH_COOKIES.get(server_key)
    if cookie:
        return {"Cookie": cookie}
    return None

async def xui_load_csrf_token(server_key: str, cookie_header: str = None) -> None:
    """گرفتن توکن CSRF و کوکی pre-session (این نسخه از 3x-ui برای login هم CSRF می‌خواهد)"""
    if str(_xui_cfg(server_key).get('api_token') or '').strip():
        return
    cookie = cookie_header if cookie_header is not None else XUI_AUTH_COOKIES.get(server_key)
    headers = {"Cookie": cookie} if cookie else {}
    try:
        response = requests.get(
            _xui_base_url(server_key) + '/csrf-token',
            headers=headers, timeout=10, verify=False
        )
    except requests.exceptions.RequestException:
        return
    if response.status_code != 200:
        return
    token = _xui_payload(response).get('obj')
    if token:
        XUI_CSRF_TOKENS[server_key] = str(token)
    merged = _xui_merge_cookies(cookie, response)
    if merged:
        XUI_AUTH_COOKIES[server_key] = merged

def _xui_merge_cookies(existing_header: str, response) -> str:
    cookies = {}
    for part in str(existing_header or '').split(';'):
        if '=' in part:
            name, value = part.split('=', 1)
            name = name.strip()
            if name:
                cookies[name] = value.strip()
    try:
        for name, value in response.cookies.items():
            cookies[name] = value
    except Exception:
        pass
    return '; '.join(f"{name}={value}" for name, value in cookies.items())

def _xui_origin(server_key: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(_xui_base_url(server_key))
    return f"{parts.scheme}://{parts.netloc}"

async def xui_login(server_key: str) -> bool:
    """ورود به پنل 3x-ui (CSRF + کوکی، پشتیبانی از API Token و فرم قدیمی)"""
    global XUI_AUTH_COOKIES

    cfg = _xui_cfg(server_key)
    if str(cfg.get('api_token') or '').strip():
        logger.info(f"3x-ui: using API token for {server_key}")
        return True

    username = str(cfg.get('xui_username') or '').strip()
    password = str(cfg.get('xui_password') or '')
    if not username or not password or password == 'xui_password' or username == 'xui_username':
        logger.error(f"3x-ui: username/password not configured for {server_key}")
        XUI_AUTH_COOKIES[server_key] = None
        return False

    await xui_load_csrf_token(server_key)

    origin = _xui_origin(server_key)
    referer = _xui_base_url(server_key) + '/'
    last_error = ""
    for login_url in _xui_login_urls(server_key):
        for mode in ('json', 'form'):
            body_kwargs = ({"json": {"username": username, "password": password}}
                           if mode == 'json'
                           else {"data": {"username": username, "password": password}})

            for attempt in (1, 2):
                headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Origin": origin,
                    "Referer": referer,
                }
                cookie = XUI_AUTH_COOKIES.get(server_key)
                if cookie:
                    headers["Cookie"] = cookie
                csrf = XUI_CSRF_TOKENS.get(server_key)
                if csrf:
                    headers["X-CSRF-Token"] = csrf

                try:
                    response = requests.post(login_url, timeout=10, verify=False,
                                             headers=headers, **body_kwargs)
                except requests.exceptions.RequestException as exc:
                    last_error = f"{login_url}: {exc}"
                    break

                payload = _xui_payload(response)
                message = str(payload.get('msg') or '')

                if response.status_code == 403 and attempt == 1:
                    XUI_CSRF_TOKENS.pop(server_key, None)
                    await xui_load_csrf_token(server_key)
                    continue

                if response.status_code == 404:
                    last_error = f"{login_url}: 404"
                    break
                if response.status_code >= 500:
                    last_error = f"{login_url}: {response.status_code}"
                    break

                if response.status_code == 200 and payload.get('success') is True:
                    merged = _xui_merge_cookies(XUI_AUTH_COOKIES.get(server_key), response)
                    if merged:
                        XUI_AUTH_COOKIES[server_key] = merged
                    XUI_CSRF_TOKENS.pop(server_key, None)
                    await xui_load_csrf_token(server_key)
                    logger.info(f"3x-ui login successful for {server_key}")
                    return True

                last_error = f"{login_url} [{mode}]: {response.status_code} {message or response.text[:120]}"
                if 'password' in message.lower() or '2fa' in message.lower() or 'two-factor' in message.lower():
                    break

    logger.error(f"3x-ui login failed for {server_key}. {last_error}")
    XUI_AUTH_COOKIES[server_key] = None
    return False

async def xui_get_headers(server_key: str) -> dict | None:
    """دریافت Headers اتصال برای سرور مشخص"""
    if _xui_auth_headers(server_key) is None:
        if not await xui_login(server_key):
            return None
    return _xui_auth_headers(server_key)

async def xui_api_request(server_key: str, method: str, path: str,
                          json_body=None, data=None, retry: bool = True):
    """درخواست به API پنل با تمدید خودکار session"""
    headers = _xui_auth_headers(server_key)
    if headers is None:
        if not await xui_login(server_key):
            return None
        headers = _xui_auth_headers(server_key)
        if headers is None:
            return None

    headers = dict(headers)
    csrf = XUI_CSRF_TOKENS.get(server_key)
    if csrf and method.upper() not in ('GET', 'HEAD'):
        headers['X-CSRF-Token'] = csrf

    url = path if path.startswith('http') else _xui_base_url(server_key) + path
    try:
        response = requests.request(method, url, headers=headers, json=json_body,
                                    data=data, timeout=15, verify=False)
    except requests.exceptions.RequestException as exc:
        logger.error(f"3x-ui {method} {url} failed for {server_key}: {exc}")
        return None

    if response.status_code == 403 and retry:
        logger.warning(f"3x-ui CSRF token rejected for {server_key}. Refreshing...")
        XUI_CSRF_TOKENS.pop(server_key, None)
        await xui_load_csrf_token(server_key)
        return await xui_api_request(server_key, method, path, json_body=json_body,
                                     data=data, retry=False)

    if response.status_code == 401 and retry:
        logger.warning(f"3x-ui session expired for {server_key}. Retrying login...")
        XUI_AUTH_COOKIES[server_key] = None
        XUI_CSRF_TOKENS.pop(server_key, None)
        if await xui_login(server_key):
            return await xui_api_request(server_key, method, path, json_body=json_body,
                                         data=data, retry=False)
    return response

def _xui_json_field(value, default):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else default
        except json.JSONDecodeError:
            return default
    return default

async def xui_get_inbounds(server_key: str):
    """لیست اینباندهای پنل"""
    response = await xui_api_request(server_key, 'GET', '/panel/api/inbounds/list')
    if response is None:
        return None
    payload = _xui_payload(response)
    if response.status_code != 200 or not payload.get('success'):
        logger.error(f"3x-ui failed to list inbounds on {server_key}: "
                     f"{payload.get('msg') or response.status_code}")
        return None
    inbounds = payload.get('obj')
    return inbounds if isinstance(inbounds, list) else []

async def xui_get_inbound(server_key: str, inbound_id=None):
    """دریافت اینباند پنل؛ inbound_id=0 یعنی آخرین اینباند ساخته‌شده"""
    cfg = _xui_cfg(server_key)
    wanted_raw = cfg.get('inbound_id') if inbound_id is None else inbound_id
    try:
        wanted = int(wanted_raw)
    except (TypeError, ValueError):
        wanted = 0

    inbounds = await xui_get_inbounds(server_key)
    if inbounds is None:
        return None
    if not inbounds:
        logger.error(f"3x-ui: no inbound found on {server_key}")
        return None

    target = None
    if wanted > 0:
        target = next((item for item in inbounds if int(item.get('id') or 0) == wanted), None)
        if target is None:
            logger.error(f"3x-ui: inbound {wanted} not found on {server_key}")
            return None
    else:
        target = max(inbounds, key=lambda item: int(item.get('id') or 0))
        logger.info(f"3x-ui: using last inbound id={target.get('id')} on {server_key}")

    try:
        inbound_id_value = int(target.get('id') or 0)
    except (TypeError, ValueError):
        inbound_id_value = 0

    if inbound_id_value > 0:
        response = await xui_api_request(server_key, 'GET', f"/panel/api/inbounds/get/{inbound_id_value}")
        if response is not None and response.status_code == 200:
            payload = _xui_payload(response)
            if payload.get('success') and isinstance(payload.get('obj'), dict):
                target = payload['obj']

    inbound = dict(target)
    inbound['settings'] = _xui_json_field(target.get('settings'), {})
    inbound['streamSettings'] = _xui_json_field(target.get('streamSettings'), {})
    inbound['sniffing'] = _xui_json_field(target.get('sniffing'), {})
    return inbound

async def xui_get_sub_link(server_key: str, sub_id: str):
    """ساخت لینک اشتراک از تنظیمات واقعی Subscription پنل (subPath/subPort/subURI)"""
    from urllib.parse import urlsplit

    cfg = _xui_cfg(server_key)
    panel_url = str(cfg.get('xui_panel_url') or '').strip()
    scheme = 'https' if panel_url.lower().startswith('https://') else 'http'

    settings = {}
    for method in ('POST', 'GET'):
        response = await xui_api_request(server_key, method, '/panel/api/setting/all')
        if response is not None and response.status_code == 200:
            payload = _xui_payload(response)
            if payload.get('success') and isinstance(payload.get('obj'), dict):
                settings = payload['obj']
                break

    if settings.get('subEnable') is False:
        logger.warning(f"3x-ui: subscription service is disabled on {server_key}")
        return None

    sub_uri = str(settings.get('subURI') or '').strip()
    sub_domain = str(settings.get('subDomain') or '').strip()
    sub_port = settings.get('subPort')
    sub_path = str(settings.get('subPath') or '').strip()

    if not sub_uri:
        host = sub_domain or str(cfg.get('server_address') or '').strip()
        if not host:
            host = urlsplit(panel_url).hostname or ''
        if not host:
            return None
        if not sub_path:
            sub_path = str(cfg.get('subscribe_path') or '/sub/').strip() or '/sub/'
        if not sub_path.startswith('/'):
            sub_path = '/' + sub_path
        port = sub_port or cfg.get('server_port_subscription') or 2096
        sub_uri = f"{scheme}://{host}:{port}{sub_path.rstrip('/')}/"

    if not sub_uri.endswith('/'):
        sub_uri += '/'
    return f"{sub_uri}{sub_id}"

def xui_build_client_link(server_key: str, inbound: dict, client: dict):
    """ساخت لینک اتصال از روی streamSettings واقعی اینباند (fallback)"""
    from urllib.parse import urlencode, quote

    cfg = _xui_cfg(server_key)
    protocol = str(inbound.get('protocol') or '').lower()
    stream = inbound.get('streamSettings') or {}
    if isinstance(stream, str):
        stream = _xui_json_field(stream, {})
    email = str(client.get('email') or '')
    address = str(cfg.get('server_address') or '').strip()
    port = cfg.get('server_port_client') or inbound.get('port') or 443
    if not address:
        return None

    network = str(stream.get('network') or 'tcp').lower()
    security = str(stream.get('security') or 'none').lower()
    tls_settings = stream.get('tlsSettings') or {}
    reality = stream.get('realitySettings') or {}
    ws_settings = stream.get('wsSettings') or {}
    grpc_settings = stream.get('grpcSettings') or {}
    xhttp_settings = stream.get('xhttpSettings') or stream.get('splithttpSettings') or {}
    httpupgrade = stream.get('httpupgradeSettings') or {}
    tcp_settings = stream.get('tcpSettings') or {}

    server_names = reality.get('serverNames') or []
    short_ids = reality.get('shortIds') or []
    reality_inner = reality.get('settings') or {}
    sni = (tls_settings.get('serverName')
           or (server_names[0] if server_names else '')
           or address)
    fingerprint = reality_inner.get('fingerprint') or tls_settings.get('fingerprint') or 'chrome'
    alpn = tls_settings.get('alpn') or []
    alpn_value = ','.join(alpn) if isinstance(alpn, list) else str(alpn or '')
    host_header = (ws_settings.get('headers') or {}).get('Host') or address
    path = (ws_settings.get('path') or xhttp_settings.get('path')
            or httpupgrade.get('path') or '')
    service_name = grpc_settings.get('serviceName') or ''
    header_type = (tcp_settings.get('header') or {}).get('type') or 'none'

    client_id = str(client.get('id') or client.get('password') or '')
    query = {
        'type': network,
        'security': security,
        'fp': fingerprint if security in ('tls', 'reality') else '',
        'sni': sni if security in ('tls', 'reality') else '',
        'alpn': alpn_value,
        'pbk': reality_inner.get('publicKey') or '',
        'sid': short_ids[0] if short_ids else '',
        'spx': reality_inner.get('spiderX') or '/',
        'path': path,
        'host': host_header,
        'serviceName': service_name,
        'mode': xhttp_settings.get('mode') or '',
        'headerType': header_type if header_type != 'none' else '',
    }

    if protocol == 'vless':
        query['encryption'] = 'none'
        query['flow'] = str(client.get('flow') or '')
        params = urlencode({key: value for key, value in query.items() if value not in ('', None)})
        return f"vless://{client_id}@{address}:{port}?{params}#{quote(email)}"

    if protocol == 'vmess':
        if not client_id:
            return None
        vmess = {
            "v": "2", "ps": email, "add": address, "port": str(port), "id": client_id,
            "aid": "0", "scy": "auto", "net": network, "type": header_type,
            "host": host_header, "path": path, "tls": '' if security == 'none' else security,
            "sni": sni, "alpn": alpn_value,
        }
        encoded = base64.b64encode(json.dumps(vmess, ensure_ascii=False).encode('utf-8')).decode('utf-8')
        return f"vmess://{encoded}"

    if protocol == 'trojan':
        params = urlencode({key: value for key, value in query.items() if value not in ('', None)})
        return f"trojan://{client_id}@{address}:{port}?{params}#{quote(email)}"

    if protocol == 'shadowsocks':
        method = str(client.get('method') or inbound.get('method') or 'chacha20-ietf-poly1305')
        password = str(client.get('password') or '')
        if not password:
            return None
        userinfo = base64.b64encode(f"{method}:{password}".encode('utf-8')).decode('utf-8')
        return f"ss://{userinfo}@{address}:{port}#{quote(email)}"

    logger.warning(f"3x-ui: cannot build link for protocol '{protocol}' on {server_key}")
    return None

async def xui_get_client_link(server_key: str, config_name: str, inbound=None, client=None):
    """لینک اتصال؛ اول از خود پنل و در صورت نیاز از streamSettings اینباند"""
    response = await xui_api_request(server_key, 'GET', f"/panel/api/clients/links/{config_name}")
    if response is not None and response.status_code == 200:
        payload = _xui_payload(response)
        links = payload.get('obj') or []
        if payload.get('success') and isinstance(links, list) and links:
            protocol = str((inbound or {}).get('protocol') or '').lower()
            if protocol:
                for link in links:
                    if str(link).lower().startswith(protocol + '://'):
                        return str(link)
            return str(links[0])
        if payload.get('msg'):
            logger.warning(f"3x-ui links for {config_name} on {server_key}: {payload.get('msg')}")

    if inbound is None:
        inbound = await xui_get_inbound(server_key)
    if inbound is None:
        return None
    if client is None:
        clients = (inbound.get('settings') or {}).get('clients') or []
        client = next((item for item in clients if item.get('email') == config_name), None)
    if not client:
        return None
    return xui_build_client_link(server_key, inbound, client)

def _xui_relative_cfg_url(server_key: str, sub_id: str):
    """لینک اشتراک قدیمی به عنوان آخرین راه‌حل"""
    cfg = _xui_cfg(server_key)
    server_address = str(cfg.get('server_address') or '').strip()
    if not server_address:
        return None
    scheme = 'https' if str(cfg.get('xui_panel_url') or '').lower().startswith('https://') else 'http'
    port = cfg.get('server_port_subscription') or 2096
    path = str(cfg.get('subscribe_path') or '/sub/')
    if not path.startswith('/'):
        path = '/' + path
    if not path.endswith('/'):
        path += '/'
    return f"{scheme}://{server_address}:{port}{path}{sub_id}"

async def xui_check_config_name_exists(server_key: str, config_name: str) -> bool | None:
    """بررسی تکراری نبودن نام کانفیگ (ایمیل کلاینت) در پنل"""
    response = await xui_api_request(server_key, 'GET', f"/panel/api/clients/get/{config_name}")
    if response is not None and response.status_code == 200:
        payload = _xui_payload(response)
        if 'success' in payload:
            return bool(payload.get('success'))
        logger.warning(f"3x-ui client lookup for {config_name} on {server_key} returned unexpected body")
    elif response is not None:
        logger.warning(f"3x-ui client lookup for {config_name} on {server_key} "
                       f"-> HTTP {response.status_code} ({_xui_base_url(server_key)})")
    else:
        logger.warning(f"3x-ui client lookup for {config_name} on {server_key} got no response")

    inbound = await xui_get_inbound(server_key)
    if inbound is None:
        return None
    clients = (inbound.get('settings') or {}).get('clients') or []
    return any(client.get('email') == config_name for client in clients)

async def xui_add_client(server_key: str, user_id: int, volume_gb: int, config_name: str, days: int,
                         limit_ip: int, existing_uuid: str = None, existing_sub_id: str = None) -> tuple[str | None, str | None, str | None]:
    """ایجاد کلاینت در آخرین اینباند پنل و ساخت لینک بر اساس همان اینباند"""
    inbound = await xui_get_inbound(server_key)
    if inbound is None:
        return None, None, None

    try:
        inbound_id = int(inbound.get('id') or 0)
    except (TypeError, ValueError):
        inbound_id = 0
    protocol = str(inbound.get('protocol') or '').lower()
    stream = inbound.get('streamSettings') or {}
    security = str(stream.get('security') or '').lower()
    network = str(stream.get('network') or '').lower()

    client_uuid = existing_uuid if existing_uuid else str(uuid.uuid4())
    sub_id = existing_sub_id if existing_sub_id else config_name
    volume_bytes = int(volume_gb * 1024 * 1024 * 1024)
    expiry_time_ms = int((time.time() + days * 24 * 3600) * 1000) if days > 0 else 0

    flow = ""
    if protocol == 'vless' and network == 'tcp' and security in ('tls', 'reality'):
        for existing in ((inbound.get('settings') or {}).get('clients') or []):
            if existing.get('flow'):
                flow = str(existing.get('flow'))
                break

    client_data = {
        "email": config_name,
        "totalGB": volume_bytes,
        "expiryTime": expiry_time_ms,
        "limitIp": limit_ip,
        "enable": True,
        "subId": sub_id,
        "tgId": 0,
        "comment": f"uid:{user_id}",
    }
    if protocol in ('vless', 'vmess', 'trojan', 'shadowsocks', 'wireguard', 'hysteria', 'mtproto'):
        client_data["id"] = client_uuid
    if flow:
        client_data["flow"] = flow

    response = await xui_api_request(
        server_key, 'POST', '/panel/api/clients/add',
        json_body={"client": client_data, "inboundIds": [inbound_id]}
    )

    legacy = False
    if response is not None and response.status_code == 404:
        legacy = True
        legacy_settings = {"clients": [dict(client_data, tgId="")]}
        response = await xui_api_request(
            server_key, 'POST', '/panel/api/inbounds/addClient',
            data={"id": inbound_id, "settings": json.dumps(legacy_settings)}
        )

    if response is None:
        return None, None, None
    payload = _xui_payload(response)
    if response.status_code != 200 or not payload.get('success'):
        logger.error(f"3x-ui failed to add client {config_name} on {server_key}: "
                     f"{payload.get('msg') or response.status_code}")
        return None, None, None

    logger.info(f"3x-ui client created on {server_key} (inbound {inbound_id}"
                f"{', legacy API' if legacy else ''}). UUID: {client_uuid} name: {config_name}")

    refreshed = await xui_get_inbound(server_key, inbound_id)
    link = await xui_get_client_link(server_key, config_name,
                                     inbound=refreshed or inbound, client=client_data)
    sub_link = await xui_get_sub_link(server_key, sub_id) or _xui_relative_cfg_url(server_key, sub_id)

    if not link:
        logger.error(f"3x-ui could not build connection link for {config_name} on {server_key}")
    if not sub_link:
        logger.error(f"3x-ui could not build subscription link for {config_name} on {server_key}")

    return link, client_uuid, sub_link

async def xui_update_client_v2(server_key: str, user_id: int, config_name: str,
                               volume_add: int, days_add: int) -> tuple[bool, float, int]:
    """تمدید حجم/زمان کلاینت در پنل"""
    inbound = await xui_get_inbound(server_key)
    if inbound is None:
        return False, 0.0, 0

    current_client = None
    response = await xui_api_request(server_key, 'GET', f"/panel/api/clients/get/{config_name}")
    if response is not None and response.status_code == 200:
        payload = _xui_payload(response)
        if payload.get('success') and isinstance(payload.get('obj'), dict):
            current_client = payload['obj'].get('client') or payload['obj']

    if not current_client:
        clients = (inbound.get('settings') or {}).get('clients') or []
        current_client = next((item for item in clients if item.get('email') == config_name), None)
        if not current_client:
            logger.error(f"3x-ui client {config_name} not found on {server_key}")
            return False, 0.0, 0

    current_total_bytes = int(current_client.get('totalGB') or 0)
    if current_total_bytes <= 0:
        new_total_bytes = 0
        new_total_gb = 0.0
    else:
        new_total_bytes = current_total_bytes + int(volume_add * 1024 * 1024 * 1024)
        new_total_gb = new_total_bytes / (1024 ** 3)

    current_expiry_ms = int(current_client.get('expiryTime') or 0)
    now_seconds = time.time()
    if current_expiry_ms <= 0:
        new_expiry_ms = 0
        new_expiry_days = 0
    else:
        current_expiry_seconds = current_expiry_ms / 1000
        start_time = max(now_seconds, current_expiry_seconds)
        new_expiry_seconds = start_time + days_add * 24 * 3600
        new_expiry_ms = int(new_expiry_seconds * 1000)
        new_expiry_days = int((new_expiry_seconds - now_seconds) / (24 * 3600))

    update_body = {
        "email": config_name,
        "totalGB": new_total_bytes,
        "expiryTime": new_expiry_ms,
        "limitIp": int(current_client.get('limitIp') or 0),
        "enable": True,
    }

    response = await xui_api_request(server_key, 'POST', f"/panel/api/clients/update/{config_name}",
                                     json_body=update_body)
    if response is not None and response.status_code == 404:
        success = await xui_legacy_update_client(server_key, inbound, config_name,
                                                 new_total_bytes, new_expiry_ms)
        if success:
            logger.info(f"3x-ui client {config_name} updated (legacy API). "
                        f"total={new_total_gb}GB expiry_days={new_expiry_days}")
            return True, new_total_gb, new_expiry_days
        return False, 0.0, 0

    if response is None:
        return False, 0.0, 0
    payload = _xui_payload(response)
    if response.status_code == 200 and payload.get('success'):
        logger.info(f"3x-ui client {config_name} updated on {server_key}. "
                    f"total={new_total_gb}GB expiry_days={new_expiry_days}")
        return True, new_total_gb, new_expiry_days

    logger.error(f"3x-ui failed to update {config_name} on {server_key}: "
                 f"{payload.get('msg') or response.status_code}")
    return False, 0.0, 0

async def xui_legacy_update_client(server_key: str, inbound: dict, config_name: str,
                                   new_total_bytes: int, new_expiry_ms: int) -> bool:
    """به‌روزرسانی کلاینت از طریق update کل اینباند (نسخه‌های قدیمی پنل)"""
    try:
        inbound_id = int(inbound.get('id') or 0)
    except (TypeError, ValueError):
        return False

    settings = inbound.get('settings') or {}
    clients = settings.get('clients') or []
    target = next((item for item in clients if item.get('email') == config_name), None)
    if not target:
        return False
    target['totalGB'] = new_total_bytes
    target['expiryTime'] = new_expiry_ms
    target['enable'] = True
    settings['clients'] = clients

    data = {
        "remark": inbound.get('remark'),
        "enable": inbound.get('enable'),
        "protocol": inbound.get('protocol'),
        "port": inbound.get('port'),
        "expiryTime": inbound.get('expiryTime'),
        "total": inbound.get('total'),
        "settings": json.dumps(settings),
        "streamSettings": json.dumps(inbound.get('streamSettings') or {}),
        "sniffing": json.dumps(inbound.get('sniffing') or {}),
    }
    response = await xui_api_request(server_key, 'POST',
                                     f"/panel/api/inbounds/update/{inbound_id}", data=data)
    if response is None:
        return False
    payload = _xui_payload(response)
    if response.status_code == 200 and payload.get('success'):
        return True
    logger.error(f"3x-ui legacy update failed for {config_name} on {server_key}: "
                 f"{payload.get('msg') or response.status_code}")
    return False

async def xui_get_client_info_by_name(server_key: str, config_name: str) -> tuple[int | None, dict | None]:
    """اطلاعات کلاینت (حجم/زمان/مصرف) برای نمایش به کاربر"""
    response = await xui_api_request(server_key, 'GET', f"/panel/api/clients/get/{config_name}")
    if response is not None and response.status_code == 200:
        payload = _xui_payload(response)
        if payload.get('success') and isinstance(payload.get('obj'), dict):
            obj = payload['obj']
            client = dict(obj.get('client') or {})
            if client:
                traffic = obj.get('traffic') or {}
                if not isinstance(traffic, dict):
                    traffic = {}
                client['up'] = int(traffic.get('up', client.get('up', 0)) or 0)
                client['down'] = int(traffic.get('down', client.get('down', 0)) or 0)
                if not client['up'] and not client['down'] and obj.get('usedTraffic'):
                    client['down'] = int(obj.get('usedTraffic') or 0)
                return 0, client

    inbound = await xui_get_inbound(server_key)
    if inbound is None:
        return None, None
    clients = (inbound.get('settings') or {}).get('clients') or []
    for index, client in enumerate(clients):
        if client.get('email') == config_name:
            return index, client

    logger.warning(f"3x-ui client {config_name} not found on {server_key}")
    return None, None

# ============================================================
# --- توابع کمکی جدید ---
# ============================================================

def convert_bytes_to_display(bytes_val: int) -> str:
    """تبدیل بایت به نمایش خواناتر (MB/GB/TB)"""
    if bytes_val < 0: return "0 MB"
    if bytes_val < 1024: return f"{bytes_val} B"
    if bytes_val < 1024**2: return f"{bytes_val / 1024:.2f} KB"
    if bytes_val < 1024**3: return f"{bytes_val / (1024**2):.2f} MB"
    if bytes_val < 1024**4: return f"{bytes_val / (1024**3):.2f} GB"
    return f"{bytes_val / (1024**4):.2f} TB"

# ============================================================
# --- هندلرها ---
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر دستور /start - منطق بررسی پرداخت از فایل 1 منتقل شد"""
    user = update.effective_user
    
    # --- منطق بررسی پرداخت (منتقل شده از فایل 1) ---
    if context.args and context.args[0].startswith('verify_'):
        
        full_text = (update.effective_message.text if update.effective_message else "") + ' ' + context.args[0]
        authority = None
        
        # 1. جستجو برای الگوی رایج زرین‌پال
        if 'Authority=' in full_text:
            parts = full_text.split('Authority=')
            if len(parts) > 1:
                temp_auth = parts[-1].split('&')[0].split('_')[-1].split(' ')[0]
                if len(temp_auth) == 36:
                    authority = temp_auth
        
        # 2. جستجو برای رشته 36 کاراکتری
        if not authority:
            auth_match = re.search(r'([A-Za-z0-9]{36})', full_text)
            if auth_match:
                 authority = auth_match.group(1)

        if authority and len(authority) == 36:
            logger.info(f"Zarinpal callback: Authority extracted successfully: {authority}")
        else:
            authority = None
            logger.error(f"AUTHORITY IS MISSING OR MALFORMED. Payload: {context.args[0]}")

        if authority:
            user_id, expected_amount_rial = get_pending_payment(authority)
            
            if user_id and expected_amount_rial:
                # حذف پیام لینک دار برای تمیزی
                message_to_edit = update.effective_message if update.effective_message else update.message
                if message_to_edit:
                    try:
                        await message_to_edit.delete()
                    except error.BadRequest:
                        pass
                        
                await verify_zarinpal_payment_callback(update, context, authority, expected_amount_rial)
                return
            else:
                await update.message.reply_text("❌ پرداخت شما در لیست پرداخت‌های در انتظار پیدا نشد یا قبلاً تأیید شده است.", reply_markup=MAIN_MENU_REPLY_MARKUP)
                return

        # دکمه پیگیری دستی در صورت عدم یافتن اتوریتی
        keyboard = [[InlineKeyboardButton("🔍 پیگیری پرداخت ناموفق", callback_data="check_pending_payment")]]
        await update.message.reply_text(
            "⚠️ پرداخت شما در لیست در انتظار است. اگر وجه کسر شده است، لطفاً کد پیگیری را به پشتیبانی ارسال کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    # --- پیام خوش‌آمدگویی (از فایل 2 حفظ شد) ---
    await update.message.reply_text(
        f"سلام {user.first_name}، به ربات فروش v2ray خوش آمدید!\n\nلطفاً یک گزینه را از منوی زیر انتخاب کنید:",
        reply_markup=MAIN_MENU_REPLY_MARKUP
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to admins."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    try:
        import traceback
        with open("bot_errors.log", "a", encoding="utf-8") as error_log:
            error_log.write("\n==== " + datetime.datetime.now().isoformat() + " ====\n")
            error_log.write("".join(traceback.format_exception(
                type(context.error), context.error, context.error.__traceback__)))
            error_log.flush()
    except Exception:
        pass
    
    try:
        if update and update.effective_user and update.effective_user.id:
            user_id = update.effective_user.id
            if isinstance(context.error, error.Conflict):
                return
            
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ متأسفانه خطایی در عملکرد ربات رخ داد. لطفاً دوباره امتحان کنید یا با پشتیبانی تماس بگیرید.",
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
        
        error_message = "❌ خطای جدی در ربات!\n\n" + str(context.error) + "\n\nUpdate: " + str(update)[:500]
        for admin_id in ADMIN_CHAT_IDS:
            await context.bot.send_message(admin_id, error_message)

    except Exception as e:
        logger.error(f"Failed to handle error or notify user/admin: {e}")

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش موجودی کیف پول و مشخصات کاربر"""
    balance = get_user_balance(update.effective_user.id)
    num_services = len(get_user_services(update.effective_user.id))
    
    message_text = (
        f"**👤 جزئیات حساب کاربری**\n\n"
        f"🔹 **شناسه کاربری (ID):** `{update.effective_user.id}`\n"
        f"🔹 **موجودی کیف پول:** **{balance:,.0f}** تومان\n"
        f"🔹 **تعداد سرویس فعال:** **{num_services}** عدد\n\n"
        f"**نکته:** برای شارژ، از دکمه «💰 شارژ کیف پول» در منوی اصلی استفاده کنید."
    )
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
    )

# 🌟 انتخاب سرور قبل از انتخاب سرویس
async def select_server_for_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش لیست سرورها برای خرید"""
    if update.callback_query: chat_id = update.callback_query.message.chat_id
    else: chat_id = update.effective_chat.id
    keyboard = []
    for server_key, server_config in SERVERS_CONFIG.items():
        if server_config.get('active', 1):
            button_text = server_config['display_name']
            callback_data = f"SELECT_SERVER_{server_key}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        else:
            logger.info(f"Server {server_key} is inactive and hidden from purchase list.")
            
    if not keyboard:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ متأسفانه در حال حاضر هیچ سرور فعالی برای خرید وجود ندارد. لطفاً بعداً تلاش کنید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="**🌍 لطفاً یک سرور را انتخاب کنید:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    context.user_data['in_conversation'] = True
    context.user_data['purchase_type'] = 'new'
    return STATE_SELECT_SERVER

# 🌟 نمایش لیست پلن‌ها بعد از انتخاب سرور
async def select_service_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش لیست پلن‌های قابل خرید برای سرور انتخاب شده"""
    query = update.callback_query
    await query.answer("در حال بارگذاری لیست پلن‌ها...")
    
    if query.data.startswith('SELECT_SERVER_'):
        server_key = query.data.split('SELECT_SERVER_')[1]
    else:
        server_key = context.user_data.get('selected_server')
    
    server_config = SERVERS_CONFIG.get(server_key)
    
    if not server_config:
        # edit inline message (no ReplyKeyboardMarkup)
        try:
            await query.edit_message_text("❌ خطای سرور. لطفاً دوباره تلاش کنید.")
        except error.BadRequest:
            pass
        await send_main_menu(query.from_user.id, context)
        return ConversationHandler.END
        
    context.user_data['selected_server'] = server_key
    context.user_data['server_display_name'] = server_config['display_name']
    
    keyboard = []
    for internal_key, info in SERVICES.items():
        volume_display = info['volume'].replace(' گیگ', 'GB')
        button_text = f"🔹 {info['label']} ({volume_display}, {info['days']} روز) - {info['price_toman']:,.0f} تومان"
        callback_data = f"SERVICE_DETAILS_PLAN_{internal_key}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
    keyboard.append([InlineKeyboardButton("♾️ سرویس بی‌نهایت (سفارشی)", callback_data="CUSTOM_BUY_UNLIMITED")])
    keyboard.append([InlineKeyboardButton("📦 سرویس حجمی (سفارشی)", callback_data="CUSTOM_BUY_VOLUME")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست سرورها", callback_data="back_to_select_server")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"**🛒 خرید سرویس ({server_config['display_name']})**\n\n"
        "لطفاً پلن مورد نظر خود را انتخاب کنید تا جزئیات و توضیحات آن را مشاهده نمایید:"
    )
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except error.BadRequest:
        await context.bot.send_message(query.from_user.id, message_text, parse_mode="Markdown", reply_markup=reply_markup)
        
    return STATE_SELECT_SERVER

# ---------------------------
# FIXED prompt_for_config_name
# ---------------------------
async def prompt_for_config_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """درخواست نام کانفیگ قبل از خرید (نسخه اصلاح‌شده: ویرایش پیام inline با InlineKeyboard و ارسال ReplyKeyboard به‌صورت پیام جدا)"""
    query = update.callback_query
    await query.answer("در حال بارگذاری...")
    
    try:
        # Support both SERVICE_DETAILS_PLAN_ and CONFIRM_PLAN_PURCHASE_ entry points
        if query.data.startswith('CONFIRM_PURCHASE_') or query.data.startswith('CONFIRM_PLAN_PURCHASE_'):
            # some flows use CONFIRM_PLAN_PURCHASE_ (from previous versions)
            if 'CONFIRM_PLAN_PURCHASE_' in query.data:
                internal_key = query.data.split('CONFIRM_PLAN_PURCHASE_')[1]
            else:
                internal_key = query.data.split('CONFIRM_PURCHASE_')[1]
        elif query.data.startswith('SERVICE_DETAILS_PLAN_'):
            internal_key = query.data.split('SERVICE_DETAILS_PLAN_')[1]
        else:
            # fallback: try generic split
            internal_key = query.data.split('_')[-1]
        panel_info = SERVICES.get(internal_key)
        if not panel_info:
            raise ValueError("Invalid plan key")
        price_toman = panel_info['price_toman']
    except Exception as e:
        logger.error(f"Failed to unpack plan data in prompt_for_config_name: {query.data} Error: {e}")
        # Edit inline message (use InlineKeyboardMarkup or none)
        try:
            await query.edit_message_text(
                "❌ خطای داده خرید. لطفاً دوباره تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_to_select_server")]])
            )
        except Exception:
            # Fallback to sending a new message
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="❌ خطای داده خرید. لطفاً دوباره تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_to_select_server")]])
            )
        await send_main_menu(query.from_user.id, context)
        return ConversationHandler.END

    user_id = query.from_user.id
    balance = get_user_balance(user_id)
    
    if balance < price_toman:
        # Edit inline message to show insufficient balance, include inline back button
        try:
            await query.edit_message_text(
                f"⚠️ موجودی ناکافی!\n\nبرای خرید سرویس {panel_info['label']} نیاز به {price_toman:,.0f} تومان دارید، اما موجودی شما {balance:,.0f} تومان است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server','Server_1')}")]])
            )
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ موجودی ناکافی!\n\nبرای خرید سرویس {panel_info['label']} نیاز به {price_toman:,.0f} تومان دارید، اما موجودی شما {balance:,.0f} تومان است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server','Server_1')}")]])
            )
        await send_main_menu(user_id, context)
        return ConversationHandler.END

    # store purchase data
    context.user_data['purchase_data'] = {
        'internal_key': internal_key,
        'price_toman': price_toman
    }

    # remove previous inline message
    try:
        await query.message.delete()
    except Exception:
        pass

    # send prompt message with ReplyKeyboardMarkup (Reply keyboard must be sent as a normal message, not edit of inline)
    # NOTE: do not set parse_mode to Markdown here to avoid entity parsing issues with backticks/examples
    await context.bot.send_message(
        user_id,
        "لطفاً یک نام انگلیسی دلخواه برای کانفیگ خود وارد کنید.\n(مثال: myconfig123, Ali-Vpn)\nاین نام باید بین ۳ تا ۲۰ کاراکتر باشد و فقط شامل حروف انگلیسی، اعداد، خط تیره (-) یا آندرلاین (_) باشد.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    context.user_data['in_conversation'] = True
    return STATE_WAITING_FOR_CONFIG_NAME

# ----------------------------------------------------

async def receive_config_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت نام کانفیگ و درخواست تایید نهایی"""
    user_input = update.message.text.strip()
    user_id = update.effective_user.id
    
    if user_input.lower() == "❌ لغو عملیات".lower():
        return await cancel_conversation(update, context)
    
    if not re.match(r'^[a-zA-Z0-9_-]{3,20}$', user_input):
        await update.message.reply_text(
            "⚠️ نام کانفیگ باید حداقل 3 و حداکثر 20 کاراکتر، شامل حروف انگلیسی، اعداد، خط تیره (-) یا آندرلاین (_) باشد. دوباره تلاش کنید:",
            reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
        )
        return STATE_WAITING_FOR_CONFIG_NAME

    server_key = context.user_data.get('selected_server', 'Server_1')
    exists = await xui_check_config_name_exists(server_key, user_input)
    
    if exists is None:
        await update.message.reply_text("❌ خطای ارتباط با پنل. لطفاً بعداً تلاش کنید یا با پشتیبانی تماس بگیرید.", reply_markup=MAIN_MENU_REPLY_MARKUP)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END
        
    if exists:
        await update.message.reply_text(
            "❌ این نام کانفیگ قبلاً در سیستم وجود دارد. لطفاً یک نام انگلیسی منحصربه‌فرد انتخاب کنید:",
            reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
        )
        return STATE_WAITING_FOR_CONFIG_NAME

    context.user_data['config_name'] = user_input
    purchase_data = context.user_data['purchase_data']
    internal_key = purchase_data['internal_key']
    price_toman = purchase_data['price_toman']
    server_name = context.user_data.get('server_display_name', 'Server')
    panel_info = get_plan_info(internal_key, context)
    
    message_text = (
        f"✅ تایید اطلاعات خرید\n\n"
        f"سرور: {server_name}\n"
        f"سرویس انتخابی: {panel_info['label']}\n"
        f"حجم: {panel_info['volume']}\n"
        f"اعتبار: {panel_info['days']} روز\n"
        f"تعداد کاربر مجاز: {panel_info['users']} نفر\n"
        f"نام کانفیگ: {user_input}\n\n"
        f"هزینه: {price_toman:,.0f} تومان (از کیف پول کسر می‌شود)\n\n"
        "آیا از خرید خود مطمئن هستید؟"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ تایید و خرید نهایی", callback_data=f"CONFIRM_PURCHASE_{internal_key}")],
        [InlineKeyboardButton("🔙 بازگشت و تغییر نام", callback_data="back_to_config_name_prompt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # send confirmation inline (new message)
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup
    )
    
    # remove the temporary reply keyboard by deleting user's input message (if possible)
    try:
        await context.bot.delete_message(chat_id=user_id, message_id=update.message.message_id)
    except Exception:
        pass
    
    return STATE_WAITING_FOR_CONFIG_NAME_CONFIRM

async def finalize_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نهایی کردن خرید، کسر وجه و ساخت کانفیگ در پنل"""
    query = update.callback_query
    await query.answer("در حال نهایی‌سازی خرید...")
    user_id = query.from_user.id
    
    try:
        config_name = context.user_data['config_name']
        server_key = context.user_data.get('selected_server', 'Server_1')
        server_name = context.user_data.get('server_display_name', 'Server')
        purchase_data = context.user_data['purchase_data']
        
        internal_key = purchase_data['internal_key']
        price_toman = purchase_data['price_toman']
        
        panel_info = get_plan_info(internal_key, context)
        volume_gb = (int(panel_info['volume_gb']) if 'volume_gb' in panel_info
                     else int(panel_info['volume'].split(' ')[0]))
        days = panel_info['days']
        limit_ip = panel_info['users']
    except Exception as e:
        logger.error(f"Failed to retrieve purchase data in finalize_purchase: {e}")
        try:
            await query.edit_message_text("❌ خطای داده. لطفاً از منوی اصلی دوباره تلاش کنید.")
        except Exception:
            pass
        await send_main_menu(query.from_user.id, context)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END
        
    balance = get_user_balance(user_id)
    if balance < price_toman:
        try:
            await query.edit_message_text(f"⚠️ موجودی ناکافی! موجودی شما: {balance:,.0f} تومان.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END
        
    new_balance = update_user_balance(user_id, -price_toman)
    
    vmess_link, client_uuid, sub_link = await xui_add_client(server_key, user_id, volume_gb, config_name, days, limit_ip)
    
    if vmess_link and client_uuid and sub_link:
        add_user_service(user_id, config_name, sub_link, client_uuid, internal_key, server_key)
        
        volume_display = panel_info['volume'].replace(' گیگ', 'GB')
        
        links_block = (
            f"🔗 <b>لینک اشتراک</b> (روی آن بزنید تا کپی شود):\n"
            f"<code>{html.escape(sub_link)}</code>\n\n"
        )
        
        final_message = (
            f"✅ خرید شما با موفقیت انجام شد!\n\n"
            f"{links_block}"
            f"━━━━━━━━━━━━━━━\n"
            f"سرویس: {panel_info['label']}\n"
            f"نام کانفیگ: {config_name}\n"
            f"سرور: {server_name}\n"
            f"حجم و اعتبار: {volume_display} - {days} روز\n"
            f"هزینه: {price_toman:,.0f} تومان\n"
        )
        
        if price_toman > 0:
            final_message += f"موجودی جدید: {new_balance:,.0f} تومان\n"
        
        final_message += (
            f"\n💡 لینک را لمس کنید تا کپی شود یا همین کیوآرکد را در برنامه اسکن کنید. در صورت مشکل، با پشتیبانی تماس بگیرید."
        )
        
        try:
            await query.message.delete()
        except Exception:
            pass
        
        sent_qr = await send_subscription_qr(
            user_id, sub_link, context,
            caption=final_message,
            parse_mode="HTML",
            reply_markup=MAIN_MENU_REPLY_MARKUP,
        )
        if not sent_qr:
            try:
                await context.bot.send_message(
                    user_id, final_message,
                    parse_mode="HTML",
                    reply_markup=MAIN_MENU_REPLY_MARKUP,
                )
            except Exception as exc:
                logger.error(f"Failed to send purchase summary to {user_id}: {exc}")
            
        try:
            for admin_id in ADMIN_CHAT_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"خرید جدید:\nکاربر: {user_id}\nکانفیگ: {config_name}\nسرور: {server_name}\nپلن: {internal_key}"
                )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
            
    else:
        update_user_balance(user_id, price_toman)
        try:
            await query.edit_message_text("❌ خطا در ایجاد کانفیگ. لطفاً با پشتیبانی تماس بگیرید. مبلغ کسر شده به کیف پول شما بازگشت داده شد.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        
    context.user_data.pop('config_name', None)
    context.user_data.pop('selected_server', None)
    context.user_data.pop('server_display_name', None)
    context.user_data.pop('purchase_data', None)
    context.user_data.pop('in_conversation', None)

    return ConversationHandler.END

async def my_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لیست کانفیگ‌های فعال کاربر"""
    user_id = update.effective_user.id
    services = get_user_services(user_id)
    
    if update.callback_query:
        query = update.callback_query
        try: await query.answer("در حال بارگذاری سرویس‌ها...")
        except: pass
        
        if not services:
            # edit inline message without ReplyKeyboardMarkup, then send main menu
            try:
                await query.edit_message_text(
                    "📂 سرویس‌های من\n\nشما در حال حاضر هیچ سرویس فعالی ندارید.\nبرای خرید، از دکمه «🛍️ خرید سرویس (انتخاب پلن)» استفاده کنید."
                )
            except Exception:
                pass
            await send_main_menu(query.from_user.id, context)
            return

        text_lines = ["📂 سرویس‌های فعال شما:\n"]
        keyboard = []
        
        for s in services:
            name = s.get('config_name')
            server_key = s.get('server_key', 'Unknown')
            server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', "نامشناس")
            text_lines.append(f"▫️ {name} — {server_name}")
            keyboard.append([InlineKeyboardButton(f"🔍 جزئیات {name}", callback_data=f"SERVICE_DETAILS_{name}")])
            
        text = "\n".join(text_lines)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_services")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup
            )
        except error.BadRequest:
            await context.bot.send_message(user_id, text, reply_markup=reply_markup)
            
    else:
        if not services:
            await update.message.reply_text(
                "📂 سرویس‌های من\n\nشما در حال حاضر هیچ سرویس فعالی ندارید.\nبرای خرید، از دکمه «🛍️ خرید سرویس (انتخاب پلن)» استفاده کنید.",
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
            return

        text_lines = ["📂 سرویس‌های فعال شما:\n"]
        keyboard = []
        
        for s in services:
            name = s.get('config_name')
            server_key = s.get('server_key', 'Unknown')
            server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', "نامشناس")
            text_lines.append(f"▫️ {name} — {server_name}")
            keyboard.append([InlineKeyboardButton(f"🔍 جزئیات {name}", callback_data=f"SERVICE_DETAILS_{name}")])
            
        text = "\n".join(text_lines)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_services")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup
        )

async def show_single_service(update: Update, context: ContextTypes.DEFAULT_TYPE, config_name: str) -> None:
    """نمایش جزئیات یک سرویس خاص (ترافیک باقی‌مانده و تاریخ انقضا)"""
    query = update.callback_query
    await query.answer("در حال دریافت اطلاعات سرویس...")
    user_id = query.from_user.id
    
    services = get_user_services(user_id)
    current_service = next((s for s in services if s['config_name'] == config_name), None)
    
    if not current_service:
        try:
            await query.edit_message_text("❌ سرویس مورد نظر پیدا نشد.")
        except Exception:
            pass
        await send_main_menu(query.from_user.id, context)
        return
        
    current_server_key = current_service.get('server_key')
    server_name = SERVERS_CONFIG.get(current_server_key, {}).get('display_name', "نامشناس")
    
    _, client_data = await xui_get_client_info_by_name(current_server_key, config_name)
    
    if not client_data:
        try:
            await query.edit_message_text(f"❌ سرویس {config_name} پیدا نشد یا حذف شده است. لطفاً با پشتیبانی تماس بگیرید.")
        except Exception:
            pass
        await send_main_menu(query.from_user.id, context)
        return
        
    total_bytes = client_data.get('totalGB', 0)
    used_bytes = client_data.get('up', 0) + client_data.get('down', 0)
    remaining_bytes = total_bytes - used_bytes
    expiry_ms = client_data.get('expiryTime', 0)
    
    total_display = convert_bytes_to_display(total_bytes)
    used_display = convert_bytes_to_display(used_bytes)
    remaining_display = convert_bytes_to_display(remaining_bytes)
    
    expiry_date_str = "نامحدود"
    if expiry_ms > 0:
        expiry_date = datetime.datetime.fromtimestamp(expiry_ms / 1000)
        expiry_date_str = expiry_date.strftime("%Y/%m/%d - %H:%M")
        
    renewal_allowed = SERVERS_CONFIG.get(current_server_key, {}).get('tamdid', 1)
    
    keyboard = []
    if renewal_allowed:
        keyboard.append([InlineKeyboardButton("🔁 تمدید / افزایش حجم", callback_data=f"PROMPT_RENEW_{config_name}")])
        
    keyboard.append([
        InlineKeyboardButton("📝 لینک اشتراک", callback_data=f"SHOW_SUB_LINK_{config_name}"),
        InlineKeyboardButton("🔙 بازگشت به لیست سرویس‌ها", callback_data="back_to_services")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"🔍 جزئیات سرویس: {config_name}\n\n"
        f"سرور: {server_name}\n\n"
        f"ترافیک کل: {total_display}\n"
        f"مصرف شده: {used_display}\n"
        f"باقی‌مانده: {remaining_display}\n"
        f"تاریخ انقضا: {expiry_date_str}\n\n"
        f"وضعیت: {'فعال' if client_data.get('enable') else 'غیرفعال'}"
    )
    
    try:
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    except error.BadRequest:
        await query.message.reply_text(message_text, reply_markup=reply_markup)

async def send_sub_link(update: Update, context: ContextTypes.DEFAULT_TYPE, config_name: str) -> None:
    """ارسال لینک اشتراک به صورت مجزا"""
    query = update.callback_query
    await query.answer("لینک اشتراک ارسال شد.")
    user_id = query.from_user.id
    
    services = get_user_services(user_id)
    current_service = next((s for s in services if s['config_name'] == config_name), None)
    
    if not current_service:
        await context.bot.send_message(user_id, "❌ سرویس مورد نظر پیدا نشد.")
        return
        
    sub_link = current_service.get('sub_link', 'نامشخص')
    
    message_text = f"📝 <b>لینک اشتراک سرویس {config_name}</b> (روی آن بزنید تا کپی شود):\n\n<code>{html.escape(sub_link)}</code>"
    
    await context.bot.send_message(user_id, message_text, parse_mode="HTML")
    await show_single_service(update, context, config_name)

async def prompt_renew_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش لیست پلن‌ها برای تمدید/افزایش حجم"""
    query = update.callback_query
    await query.answer("در حال بارگذاری پلن‌های تمدید...")
    user_id = query.from_user.id
    
    config_name = query.data.split('PROMPT_RENEW_')[1]
    
    services = get_user_services(user_id)
    current_service = next((s for s in services if s['config_name'] == config_name), None)
    
    if not current_service:
        try:
            await query.edit_message_text("❌ سرویس مورد نظر برای تمدید پیدا نشد.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        return ConversationHandler.END
        
    current_server_key = current_service.get('server_key')
    current_server_name = SERVERS_CONFIG.get(current_server_key, {}).get('display_name', "نامشناس")
    
    context.user_data['renewal_target_name'] = config_name
    context.user_data['renewal_target_server_key'] = current_server_key
    
    keyboard = []
    for internal_key, panel in SERVICES.items():
        volume_display = panel['volume'].replace(' گیگ', 'GB')
        callback_data = f"RENEW_SELECT_{internal_key}_{panel['price_toman']}"
        button_text = f"➕ {panel['label']} (+{panel['days']} روز، +{volume_display}) - {panel['price_toman']:,.0f} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به سرویس‌های من", callback_data="back_to_services")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"🔁 تمدید سرویس: {config_name}\nسرور: {current_server_name}\n\nیکی از پلن‌های زیر را انتخاب کنید. حجم و اعتبار جدید به مقادیر فعلی شما اضافه خواهد شد:",
            reply_markup=reply_markup
        )
    except error.BadRequest:
        await context.bot.send_message(user_id, "در حال بارگذاری پلن‌ها...", reply_markup=reply_markup)
        
    context.user_data['in_conversation'] = True
    return STATE_WAITING_FOR_RENEWAL_CONFIRM

async def finalize_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نهایی کردن تمدید سرویس"""
    query = update.callback_query
    await query.answer("در حال تایید و اعمال تمدید...")
    user_id = query.from_user.id
    
    try:
        data_string = query.data.split('RENEW_SELECT_')[1]
        internal_key, price_toman_str = data_string.rsplit('_', 1)
        price_toman = int(price_toman_str)
        panel_info = SERVICES.get(internal_key)
        
        config_name = context.user_data.get('renewal_target_name')
        server_key = context.user_data.get('renewal_target_server_key')
        server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', "نامشناس")
        
        volume_add = int(panel_info['volume'].split(' ')[0])
        days_add = panel_info['days']
    except Exception as e:
        logger.error(f"Failed to retrieve renewal data in finalize_renewal: {e}")
        try:
            await query.edit_message_text("❌ خطای داده تمدید. لطفاً دوباره تلاش کنید.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END

    balance = get_user_balance(user_id)
    if balance < price_toman:
        try:
            await query.edit_message_text(f"⚠️ موجودی ناکافی! موجودی شما: {balance:,.0f} تومان.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END
        
    new_balance = update_user_balance(user_id, -price_toman)
    
    success, new_total_gb, new_expiry_days = await xui_update_client_v2(server_key, user_id, config_name, volume_add, days_add)
    
    if success:
        final_message = (
            f"✅ تمدید سرویس {config_name} با موفقیت انجام شد!\n\n"
            f"پلن انتخابی: {panel_info['label']}\n"
            f"افزایش حجم: +{volume_add} GB\n"
            f"افزایش اعتبار: +{days_add} روز\n\n"
            f"موجودی جدید: {new_balance:,.0f} تومان\n"
            f"حجم کل (تقریبی): {new_total_gb:.2f} GB\n"
            f"اعتبار باقی‌مانده (تقریبی): {new_expiry_days} روز"
        )
        
        try:
            await query.edit_message_text(final_message)
            await send_main_menu(user_id, context)
        except Exception:
            await context.bot.send_message(user_id, final_message)
            await send_main_menu(user_id, context)
            
        try:
            for admin_id in ADMIN_CHAT_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"تمدید سرویس:\nکاربر: {user_id}\nکانفیگ: {config_name}\nسرور: {server_name}\nپلن: {internal_key}\nاضافه شده: {volume_add} GB و {days_add} روز"
                )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
            
    else:
        update_user_balance(user_id, price_toman)
        try:
            await query.edit_message_text("❌ خطا در به‌روزرسانی سرویس. مبلغ تمدید به کیف پول شما بازگشت داده شد.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        
    context.user_data.pop('renewal_target_name', None)
    context.user_data.pop('renewal_target_server_key', None)
    context.user_data.pop('renewal_target_client_data', None)
    context.user_data.pop('in_conversation', None)
    return ConversationHandler.END

# ============================================================
# --- هندلرهای کیف پول و پشتیبانی ---
# ============================================================

async def wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع فرآیند شارژ کیف پول"""
    user_id = update.effective_user.id
    current_balance = get_user_balance(user_id)
    
    message_text = (
        f"💰 شارژ کیف پول\n\n"
        f"موجودی فعلی شما: {current_balance:,.0f} تومان\n\n"
        "لطفاً مبلغ مورد نظر (به تومان) را جهت شارژ کیف پول وارد کنید:\n"
        "(حداقل ۱,۰۰۰ تومان)"
    )
    
    await update.message.reply_text(
        message_text,
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    context.user_data['in_conversation'] = True
    return STATE_GET_AMOUNT

async def wallet_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت مبلغ و هدایت به درگاه پرداخت - منطق از فایل 1 کپی شد"""
    user_input = update.message.text.strip()
    
    if user_input.lower() == "❌ لغو عملیات".lower():
        return await cancel_conversation(update, context)

    try:
        amount_toman = int(user_input.replace(',', ''))
        if amount_toman < 1000:
             await update.message.reply_text("مبلغ وارد شده باید حداقل ۱,۰۰۰ تومان باشد."); return STATE_GET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ مبلغ وارد شده نامعتبر است. لطفاً مبلغ را به تومان و به صورت عدد وارد کنید (حداقل ۱,۰۰۰ تومان).")
        return STATE_GET_AMOUNT

    user_id = update.effective_user.id
    amount_rial = amount_toman * 10
    description = f"شارژ کیف پول کاربر {user_id} به مبلغ {amount_toman:,.0f} تومان"
    
    payment_url, authority = await zarinpal_create_request(user_id, amount_rial, description, context)

    if payment_url and authority:
        # دکمه لغو پرداخت (اضافه شده از منطق فایل 1)
        keyboard = [
            [InlineKeyboardButton("💳 پرداخت آنلاین (اتصال به زرین‌پال)", url=payment_url)],
            [InlineKeyboardButton("❌ لغو پرداخت", callback_data=f"cancel_payment_{authority}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ لینک پرداخت برای مبلغ {amount_toman:,.0f} تومان ساخته شد.\n\n روی دکمه کلیک کرده و پرداخت را کامل کنید.",
            reply_markup=reply_markup
        )
        
        # حذف دکمه‌های Reply (ارسال یک پیام کوچک برای پاکسازی UI)
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=update.message.message_id)
        except Exception:
            pass
        
        context.user_data.pop('in_conversation', None)
        await send_main_menu(user_id, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ خطای اتصال به درگاه پرداخت. لطفاً بعداً تلاش کنید یا با پشتیبانی تماس بگیرید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END

# 🌟 تابع جدید (منتقل شده از فایل 1): هندلر لغو پرداخت
async def cancel_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("عملیات پرداخت لغو شد.") 
    
    user_id = query.from_user.id
    
    try:
        authority = query.data.split("cancel_payment_")[1]
        remove_pending_payment(authority)
    except IndexError:
        logger.error("Could not extract authority from cancel_payment callback data.")

    try:
        await query.edit_message_text(
            "❌ لغو پرداخت\n\nعملیات شارژ کیف پول لغو شد و به منوی اصلی بازگشتید.",
            reply_markup=None
        )
    except error.BadRequest:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ لغو پرداخت\n\nعملیات شارژ کیف پول لغو شد و به منوی اصلی بازگشتید."
        )
        
    await send_main_menu(user_id, context)
    
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو مکالمه و بازگشت به منوی اصلی"""
    user_id = update.effective_user.id
    
    context.user_data.pop('in_conversation', None)
    context.user_data.pop('config_name', None)
    context.user_data.pop('selected_server', None)
    context.user_data.pop('server_display_name', None)
    context.user_data.pop('purchase_data', None)
    context.user_data.pop('renewal_target_name', None)
    context.user_data.pop('renewal_target_server_key', None)
    
    if update.message and update.message.text.lower() == "❌ لغو عملیات".lower():
        try: await context.bot.delete_message(chat_id=user_id, message_id=update.message.message_id)
        except Exception: pass
        
    await send_main_menu(user_id, context)
    
    return ConversationHandler.END

async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع مکالمه پشتیبانی"""
    await update.message.reply_text(
        "📞 پشتیبانی\n\nلطفاً پیام یا سوال خود را ارسال کنید. پیام شما برای ادمین‌ها فوروارد خواهد شد.\nدر صورت تمایل به لغو، از دکمه زیر استفاده کنید.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    context.user_data['in_conversation'] = True
    return STATE_GET_TICKET

async def support_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """فوروارد پیام تیکت به ادمین‌ها"""
    user = update.effective_user
    original_message = update.message
    
    try:
        admin_message_header = f"📞 پیام پشتیبانی جدید\nنام کاربر: {user.first_name} (ID: {user.id})\n"
        
        if 'support_map' not in context.bot_data: context.bot_data['support_map'] = {}
        
        for admin_id in ADMIN_CHAT_IDS:
            await context.bot.send_message(admin_id, admin_message_header)
            forwarded_message = await context.bot.forward_message(
                chat_id=admin_id,
                from_chat_id=user.id,
                message_id=original_message.message_id
            )
            context.bot_data['support_map'][forwarded_message.message_id] = user.id
            
        await update.message.reply_text("✅ پیام شما به پشتیبانی ارسال شد. منتظر پاسخ باشید.", reply_markup=MAIN_MENU_REPLY_MARKUP)
    
    except Exception as e:
        logger.error(f"Failed to handle support ticket: {e}")
        await update.message.reply_text("❌ خطایی در ارسال پیام شما رخ داد.", reply_markup=MAIN_MENU_REPLY_MARKUP)
        
    context.user_data.pop('in_conversation', None)
    return ConversationHandler.END

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ ادمین به تیکت"""
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لطفاً برای پاسخ دادن، پیام اصلی کاربر را ریپلای کنید.")
        return
        
    original_message_id = update.message.reply_to_message.message_id
    user_id = context.bot_data.get('support_map', {}).get(original_message_id)
    
    if user_id:
        try:
            await context.bot.send_message(
                user_id,
                f"پاسخ پشتیبانی:\n\n{update.message.text}"
            )
            await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
            
        except Exception as e:
            logger.error(f"Failed to reply to user {user_id}: {e}")
            await update.message.reply_text(f"❌ خطایی در ارسال پاسخ به کاربر رخ داد: {e}")
            
    else:
        await update.message.reply_text("❌ شناسه کاربر پیدا نشد یا پیام اصلی تیکت نیست.")

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به منوی اصلی از طریق دکمه‌های شیشه‌ای"""
    query = update.callback_query
    await query.answer("بازگشت به منوی اصلی...")
    
    # edit inline message with no ReplyKeyboardMarkup, then send MAIN menu as separate message
    try:
        await query.edit_message_text("یک گزینه را انتخاب کنید:")
    except Exception:
        pass
    await send_main_menu(query.from_user.id, context)

async def back_to_config_name_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بازگشت به مرحله وارد کردن نام کانفیگ (در مکالمه خرید)"""
    query = update.callback_query
    await query.answer("بازگشت...")
    user_id = query.from_user.id
    
    await context.bot.send_message(
        user_id,
        "لطفاً یک نام انگلیسی دلخواه برای کانفیگ خود وارد کنید.\n(مثال: myconfig123, Ali-Vpn)\nاین نام باید بین ۳ تا ۲۰ کاراکتر باشد و فقط شامل حروف انگلیسی، اعداد، خط تیره (-) یا آندرلاین (_) باشد.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    
    try: await query.message.delete()
    except Exception: pass
    
    return STATE_WAITING_FOR_CONFIG_NAME

async def back_to_select_server(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به لیست سرورها از طریق دکمه شیشه‌ای"""
    query = update.callback_query
    await query.answer("بازگشت به لیست سرورها...")
    user_id = query.from_user.id
    keyboard = []
    for server_key, server_config in SERVERS_CONFIG.items():
        if server_config.get('active', 1):
            button_text = server_config['display_name']
            callback_data = f"SELECT_SERVER_{server_key}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    if not keyboard:
        try:
            await query.edit_message_text("❌ متأسفانه در حال حاضر هیچ سرور فعالی برای خرید وجود ندارد.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        return
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text("🌍 لطفاً یک سرور را انتخاب کنید:", reply_markup=reply_markup)
    except error.BadRequest:
        await context.bot.send_message(user_id, text="🌍 لطفاً یک سرور را انتخاب کنید:", reply_markup=reply_markup)

async def back_to_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به لیست سرویس‌های من از طریق دکمه شیشه‌ای"""
    await my_services(update, context)

# ============================================================
# --- PAYMENT: check pending payment (REPLACED) -------------
# ============================================================

async def check_pending_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks for a pending payment for the user and triggers verification (moved from file 1)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Inform the user we're checking
    try:
        await query.edit_message_text("در حال بررسی پرداخت‌های در انتظار...")
    except Exception:
        pass

    pending_payments = load_pending_payments()
    found_payment = None
    for authority, info in pending_payments.items():
        if str(info['user_id']) == str(user_id):
            found_payment = (authority, info['amount'])
            break

    if found_payment:
        authority, expected_amount_rial = found_payment
        # Use the message object (query.message) as the 'update' parameter like in file 1:
        await verify_zarinpal_payment_callback(query.message, context, authority, expected_amount_rial)
    else:
        await context.bot.send_message(user_id, "❌ هیچ پرداخت در انتظاری برای حساب شما پیدا نشد. لطفاً دوباره امتحان کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP)

# ============================================================
# --- باقی هندلر‌ها و button handler -----------------------
# ============================================================

async def check_pending_payment_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """راهنمای پیگیری پرداخت (احتیاط: نگه‌داشته شده در صورت نیاز)"""
    query = update.callback_query
    await query.answer("راهنمای پیگیری پرداخت...")
    
    message_text = (
        "پیگیری پرداخت ناموفق\n\n"
        "اگر وجه از حساب شما کسر شده اما موجودی کیف پول شما افزایش نیافته است، لطفاً اطلاعات زیر را به پشتیبانی ارسال کنید:\n\n"
        "1. تاریخ و ساعت دقیق تراکنش\n"
        "2. کد پیگیری یا شماره ارجاع تراکنش\n"
        "3. تصویر رسید پرداخت (اختیاری)\n\n"
        "برای ارسال پیام به پشتیبانی، روی دکمه «📞 پشتیبانی» در منوی اصلی کلیک کنید."
    )
    
    try:
        await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_services")]]))
    except error.BadRequest:
        await query.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_services")]]))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر جامع برای دکمه‌های شیشه‌ای (غیر از مکالمات)"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "OPEN_MY_SERVICES" or data == "back_to_services":
        return await my_services(update, context) 
    
    if data == "back_to_main_from_services":
        return await back_to_main_menu(update, context)
        
    if data == "back_to_select_server":
        return await back_to_select_server(update, context)
        
    if data == "check_pending_payment":
        # Now invokes the verification flow (not the old guide)
        return await check_pending_payment(update, context)
        
    if data.startswith("SERVICE_DETAILS_"):
        config_name_or_plan_key = data.split("SERVICE_DETAILS_")[1]
        
        if config_name_or_plan_key.startswith("PLAN_"):
            internal_key = config_name_or_plan_key.split("PLAN_")[1]
            panel_info = SERVICES.get(internal_key)
            
            if not panel_info:
                try:
                    await query.edit_message_text("❌ پلن نامعتبر", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_to_select_server")]]))
                except Exception:
                    pass
                return

            volume_display = panel_info['volume'].replace(' گیگ', 'GB')
            description = panel_info['description']
            
            message_text = (
                f"جزئیات پلن: {panel_info['label']}\n\n"
                f"حجم: {volume_display}\n"
                f"اعتبار: {panel_info['days']} روز\n"
                f"تعداد کاربر مجاز: {panel_info['users']} نفر\n"
                f"توضیحات: {description}\n\n"
                f"قیمت: {panel_info['price_toman']:,.0f} تومان"
            )
            
            buy_callback_data = f"CONFIRM_PLAN_PURCHASE_{internal_key}"
            
            keyboard = [
                [InlineKeyboardButton(f"✅ تایید و خرید ({panel_info['price_toman']:,.0f} تومان)", callback_data=buy_callback_data)],
                [InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server', 'Server_1')}")] 
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await query.edit_message_text(message_text, reply_markup=reply_markup)
            except error.BadRequest:
                await context.bot.send_message(query.from_user.id, message_text, reply_markup=reply_markup)
            return
            
        else:
            return await show_single_service(update, context, config_name_or_plan_key)

    if data.startswith("SHOW_SUB_LINK_"):
        config_name = data.split("SHOW_SUB_LINK_")[1]
        return await send_sub_link(update, context, config_name)


# ============================================================
# --- خرید سفارشی: سرویس بی‌نهایت و سرویس حجمی با اسلایدر ---
# ============================================================

def custom_plan_price(mode: str, volume_gb: int, users: int) -> int:
    """قیمت سرویس سفارشی
    بی‌نهایت: ۴۰۰٬۰۰۰ تومان به ازای هر کاربر
    حجمی: حجم × ۲٬۰۰۰ تومان و برای هر کاربر اضافه ضریب ۱.۳ تصاعدی"""
    if mode == 'unlimited':
        return UNLIMITED_PRICE_PER_USER * users
    return int(round(volume_gb * VOLUME_PRICE_PER_GB * (CUSTOM_USER_MULTIPLIER ** (users - 1))))


def custom_slider_bar(value: int, maximum: int, width: int = 10) -> str:
    """نوار کشویی که از چپ به راست پر می‌شود"""
    filled = int(round(width * value / maximum)) if maximum else 0
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


def get_plan_info(internal_key: str, context=None):
    """اطلاعات پلن؛ پلن‌های سفارشی از purchase_data خوانده می‌شوند"""
    if context is not None:
        plan = (context.user_data.get('purchase_data') or {}).get('plan_info')
        if plan:
            return plan
    return SERVICES.get(internal_key) or CUSTOM_PLANS.get(internal_key)


def _custom_selection(context):
    sel = context.user_data.get('custom_buy')
    if not sel:
        sel = {'mode': 'volume', 'volume_gb': 10, 'users': 1}
        context.user_data['custom_buy'] = sel
    return sel


async def _render_custom_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    sel = _custom_selection(context)
    mode = sel['mode']
    users = sel['users']
    volume_gb = sel['volume_gb']
    price = custom_plan_price(mode, volume_gb, users)

    if mode == 'unlimited':
        title = "♾️ سرویس بی‌نهایت"
        body = "حجم: نامحدود\n"
        volume_rows = []
        price_hint = f"(هر کاربر {UNLIMITED_PRICE_PER_USER:,} تومان)"
    else:
        title = "📦 سرویس حجمی"
        body = (f"حجم: {volume_gb} گیگابایت از {VOLUME_MAX_GB} گیگ\n"
                f"{custom_slider_bar(volume_gb, VOLUME_MAX_GB)}  {volume_gb}/{VOLUME_MAX_GB}\n")
        volume_rows = [
            [InlineKeyboardButton("⏪ ۱۰-", callback_data="CUSTOM_ADJ_VOL_-10"),
             InlineKeyboardButton("◀️ ۱-", callback_data="CUSTOM_ADJ_VOL_-1"),
             InlineKeyboardButton("▶️ ۱+", callback_data="CUSTOM_ADJ_VOL_1"),
             InlineKeyboardButton("⏩ ۱۰+", callback_data="CUSTOM_ADJ_VOL_10")],
        ]
        price_hint = (f"(هر گیگ {VOLUME_PRICE_PER_GB:,} تومان؛ "
                      f"هر کاربر اضافه قیمت را {CUSTOM_USER_MULTIPLIER} برابر می‌کند)")

    text = (
        f"{title} (سفارشی)\n\n"
        f"{body}"
        f"کاربران (بر اساس IP): {users} از {CUSTOM_MAX_USERS}\n"
        f"{custom_slider_bar(users, CUSTOM_MAX_USERS)}\n"
        f"⏳ اعتبار: {CUSTOM_DAYS} روز\n\n"
        f"💰 قیمت نهایی: {price:,} تومان\n"
        f"{price_hint}"
    )

    keyboard = volume_rows + [
        [InlineKeyboardButton("👥 ۱-", callback_data="CUSTOM_ADJ_USR_-1"),
         InlineKeyboardButton("👥 ۱+", callback_data="CUSTOM_ADJ_USR_1")],
        [InlineKeyboardButton("✅ تایید و خرید", callback_data="CUSTOM_CONFIRM")],
        [InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها",
                              callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server', 'Server_1')}")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception:
        await context.bot.send_message(query.from_user.id, text, reply_markup=markup)


async def custom_buy_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """باز کردن خرید سفارشی (بی‌نهایت یا حجمی)"""
    query = update.callback_query
    await query.answer("در حال باز کردن خرید سفارشی...")
    mode = 'unlimited' if query.data.endswith('UNLIMITED') else 'volume'
    context.user_data['custom_buy'] = {'mode': mode, 'volume_gb': 10, 'users': 1}
    context.user_data['in_conversation'] = True
    await _render_custom_buy(update, context)
    return STATE_CUSTOM_BUILD


async def custom_buy_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """کم/زیاد کردن حجم یا تعداد کاربر با اسلایدر"""
    query = update.callback_query
    try:
        _, _, field, delta = query.data.split('_')
        delta = int(delta)
    except Exception:
        await query.answer()
        return STATE_CUSTOM_BUILD

    sel = _custom_selection(context)
    if field == 'VOL':
        sel['volume_gb'] = max(1, min(VOLUME_MAX_GB, sel['volume_gb'] + delta))
    elif field == 'USR':
        sel['users'] = max(1, min(CUSTOM_MAX_USERS, sel['users'] + delta))

    await query.answer()
    await _render_custom_buy(update, context)
    return STATE_CUSTOM_BUILD


async def custom_buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ثبت پلن سفارشی و رفتن به مرحله نام کانفیگ"""
    query = update.callback_query
    await query.answer("در حال آماده‌سازی خرید...")
    user_id = query.from_user.id

    sel = _custom_selection(context)
    mode = sel['mode']
    users = sel['users']
    volume_gb = sel['volume_gb'] if mode == 'volume' else 0
    price = custom_plan_price(mode, volume_gb, users)

    balance = get_user_balance(user_id)
    if balance < price:
        try:
            await query.edit_message_text(
                f"⚠️ موجودی ناکافی!\n\nقیمت این سرویس {price:,} تومان است اما موجودی شما {balance:,} تومان است.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها",
                                         callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server', 'Server_1')}")
                ]])
            )
        except Exception:
            pass
        await send_main_menu(user_id, context)
        return ConversationHandler.END

    if mode == 'unlimited':
        label = f"♾️ بی‌نهایت ({users} کاربر)"
        volume_text = "نامحدود"
        volume_number = 0
    else:
        label = f"📦 حجمی {volume_gb} گیگ ({users} کاربر)"
        volume_text = f"{volume_gb} گیگ"
        volume_number = volume_gb

    plan_info = {
        'label': label,
        'users': users,
        'volume': volume_text,
        'volume_gb': volume_number,
        'days': CUSTOM_DAYS,
        'price_toman': price,
        'description': 'سرویس سفارشی',
    }

    internal_key = f"CUSTOM_{mode.upper()}_{int(time.time() * 1000)}"
    CUSTOM_PLANS[internal_key] = plan_info
    context.user_data['purchase_data'] = {
        'internal_key': internal_key,
        'price_toman': price,
        'plan_info': plan_info,
    }
    context.user_data.pop('custom_buy', None)

    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        user_id,
        "لطفاً یک نام انگلیسی دلخواه برای کانفیگ خود وارد کنید.\n"
        "(مثال: myconfig123, Ali-Vpn)\n"
        "این نام باید بین ۳ تا ۲۰ کاراکتر باشد و فقط شامل حروف انگلیسی، اعداد، خط تیره (-) یا آندرلاین (_) باشد.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    context.user_data['in_conversation'] = True
    return STATE_WAITING_FOR_CONFIG_NAME


# ============================================================
# --- ارسال فایل کانفیگ به‌صورت قابل دانلود ---

# ============================================================
# --- کیوآرکد لینک اشتراک ---
# ============================================================

def build_qr_png(data: str):
    """ساخت تصویر PNG از کیوآرکد (در صورت نصب بودن کتابخانه qrcode)"""
    try:
        import qrcode
    except ImportError:
        logger.warning("qrcode library is not installed; skipping QR code")
        return None
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        logger.error(f"Failed to build QR code: {exc}")
        return None


async def send_subscription_qr(chat_id: int, sub_link: str, context, caption: str = None,
                                parse_mode: str = None, reply_markup=None) -> bool:
    """ارسال کیوآرکد لینک اشتراک تا با اسکن در برنامه اضافه شود"""
    if not sub_link:
        return False
    png = build_qr_png(sub_link)
    if not png:
        return False
    if caption is None:
        caption = (
            "📷 کیوآرکد لینک اشتراک شما\n"
            "در برنامه، گزینه Scan QR Code را بزنید و این تصویر را اسکن کنید.\n"
            f"{sub_link}"
        )
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(io.BytesIO(png), filename="subscription_qr.png"),
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        return True
    except Exception as exc:
        logger.error(f"Failed to send QR code to {chat_id}: {exc}")
        return False


# ============================================================
# --- بخش آموزش اتصال ---
# ============================================================

TUTORIAL_MAIN_TEXT = (
    "📚 **آموزش اتصال**\n\n"
    "این بخش بر پایه هسته **V2Ray** است و برای هر سیستم عامل، برنامه‌های پشتیبانی‌شده و هزینه هر برنامه را مشخص کرده‌ایم.\n\n"
    "لطفاً ابتدا سیستم عامل خود را انتخاب کنید:"
)


def tutorial_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Android", callback_data="TUTORIAL_CAT_android")],
        [InlineKeyboardButton("📱 iOS", callback_data="TUTORIAL_CAT_ios")],
        [InlineKeyboardButton("💻 Windows", callback_data="TUTORIAL_CAT_windows")],
        [InlineKeyboardButton("📌 نکات کلی و برنامه‌های پشتیبانی‌شده", callback_data="TUTORIAL_CAT_tips")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_tutorial")],
    ])


async def connection_tutorials_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع بخش آموزش اتصال"""
    await update.message.reply_text(TUTORIAL_MAIN_TEXT, parse_mode="Markdown",
                                    reply_markup=tutorial_categories_keyboard())


async def tutorial_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش برنامه‌های هر دسته"""
    query = update.callback_query
    await query.answer()
    category = query.data.split("TUTORIAL_CAT_")[1]
    category_info = TUTORIAL_CATEGORIES.get(category)
    if not category_info:
        await query.edit_message_text("❌ دسته‌بندی پیدا نشد.")
        return
    keyboard = [[InlineKeyboardButton(app['name'], callback_data=f"TUTORIAL_APP_{app['key']}")]
                for app in category_info['apps']]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به دسته‌بندی‌ها", callback_data="back_to_tutorial_categories")])
    text = f"**{category_info['title']}**\n\nلطفاً یکی از برنامه‌های زیر را انتخاب کنید:"
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as exc:
        logger.error(f"Failed to edit tutorial category message: {exc}")


async def tutorial_app_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش آموزش کامل یک برنامه"""
    query = update.callback_query
    await query.answer()
    app_key = query.data.split("TUTORIAL_APP_")[1]
    info = CONNECTION_TUTORIALS.get(app_key)
    if not info:
        await query.edit_message_text("❌ آموزش مورد نظر پیدا نشد.")
        return

    text = chr(10).join([f"**{info['title']}**", ""] + list(info['steps']))
    category = info.get('category', 'tips')
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"TUTORIAL_CAT_{category}")],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main_from_tutorial")],
    ])

    try:
        if len(text) <= 4000:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            try:
                await query.edit_message_text("📚 آموزش در چند پیام ارسال می‌شود...")
            except Exception:
                pass
            for start in range(0, len(text), 3900):
                await context.bot.send_message(query.from_user.id, text[start:start + 3900], parse_mode="Markdown")
            await context.bot.send_message(query.from_user.id, "برای انتخاب برنامه دیگر از دکمه‌های زیر استفاده کنید:", reply_markup=markup)
    except error.BadRequest:
        await context.bot.send_message(query.from_user.id, text, parse_mode="Markdown", reply_markup=markup)


async def back_to_tutorial_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به دسته‌بندی آموزش"""
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(TUTORIAL_MAIN_TEXT, parse_mode="Markdown",
                                      reply_markup=tutorial_categories_keyboard())
    except Exception as exc:
        logger.error(f"Failed to edit back to tutorial categories: {exc}")


async def back_to_main_from_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به منوی اصلی از بخش آموزش"""
    query = update.callback_query
    await query.answer("بازگشت به منوی اصلی...")
    await send_main_menu(query.from_user.id, context)


async def track_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ثبت @username و نام تلگرام کاربر در دیتابیس (برای نمایش در پنل ادمین)"""
    try:
        user = update.effective_user
        if user is not None:
            storage.touch_profile(user.id, user.username, user.first_name)
    except Exception as exc:
        logger.debug(f"profile tracking failed: {exc}")


_SINGLE_INSTANCE_HANDLE = None


def ensure_single_instance() -> None:
    """جلوگیری از اجرای همزمان دو نسخهٔ ربات با یک توکن (خطای Conflict در getUpdates)"""
    global _SINGLE_INSTANCE_HANDLE
    if os.name != "nt":
        return
    try:
        import ctypes
        import hashlib
        tag = hashlib.md5(str(BOT_TOKEN or "").encode("utf-8", "ignore")).hexdigest()[:16]
        _SINGLE_INSTANCE_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\vpn-bot-{tag}")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            logger.error("Another instance of this bot is already running (same token).")
            print("\n[!] این ربات همین حالا در حال اجراست. ابتدا نسخهٔ قبلی را ببندید.\n")
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as lock_error:
        logger.warning(f"Single-instance lock skipped: {lock_error}")


def main() -> None:
    """شروع به کار ربات"""
    ensure_single_instance()
    # اجرای پنل وب ادمین همراه ربات (پورت 9997)
    try:
        import admin_panel
        admin_panel.start_panel_thread(bot_token=BOT_TOKEN)
    except Exception as panel_error:
        logger.error(f"Failed to start admin panel: {panel_error}")
    
    application = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

    wallet_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 شارژ کیف پول$"), wallet_start)],
        states={
            STATE_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_receive_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)],
    )

    support_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📞 پشتیبانی$"), support_start)],
        states={
            STATE_GET_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, support_receive_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)],
    )

    purchase_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🛍️ خرید سرویس \(انتخاب پلن\)$"), select_server_for_purchase)],
        states={
            STATE_SELECT_SERVER: [
                CallbackQueryHandler(select_service_plan, pattern="^SELECT_SERVER_"),
                MessageHandler(filters.Regex(r"^🛍️ خرید سرویس \(انتخاب پلن\)$"), select_server_for_purchase),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), 
            MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation),
        ],
    )

    # IMPORTANT FIX: do NOT include SERVICE_DETAILS_PLAN_ in entry_points here.
    config_name_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_for_config_name, pattern="^CONFIRM_PURCHASE_|^CONFIRM_PLAN_PURCHASE_")], 
        states={
            STATE_WAITING_FOR_CONFIG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_config_name), CallbackQueryHandler(cancel_conversation, pattern="^cancel_conv_select_server")],
            STATE_WAITING_FOR_CONFIG_NAME_CONFIRM: [CallbackQueryHandler(finalize_purchase, pattern="^CONFIRM_PURCHASE_|^CONFIRM_PLAN_PURCHASE_"), CallbackQueryHandler(back_to_config_name_prompt, pattern="^back_to_config_name_prompt")]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)],
    )
    
    renewal_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_renew_service, pattern="^PROMPT_RENEW_")],
        states={
            STATE_WAITING_FOR_RENEWAL_CONFIRM: [CallbackQueryHandler(finalize_renewal, pattern="^RENEW_SELECT_")]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)],
    )

    application.add_error_handler(error_handler)
    # ثبت پروفایل تلگرام کاربران برای پنل ادمین
    application.add_handler(MessageHandler(filters.ALL, track_user_profile), group=-1)
    application.add_handler(CallbackQueryHandler(track_user_profile), group=-1)

    application.add_handler(CommandHandler("start", start))
    
    application.add_handler(wallet_conv_handler)
    application.add_handler(support_conv_handler)
    
    application.add_handler(purchase_conv_handler) 
    
    application.add_handler(config_name_conv_handler) 
    application.add_handler(renewal_conv_handler)
    # مکالمه خرید سفارشی (بی‌نهایت / حجمی با اسلایدر)
    custom_buy_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(custom_buy_open, pattern=r'^CUSTOM_BUY_'),
        ],
        states={
            STATE_CUSTOM_BUILD: [
                CallbackQueryHandler(custom_buy_adjust, pattern=r'^CUSTOM_ADJ_'),
                CallbackQueryHandler(custom_buy_confirm, pattern=r'^CUSTOM_CONFIRM$'),
            ],
            STATE_WAITING_FOR_CONFIG_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_config_name),
            ],
            STATE_WAITING_FOR_CONFIG_NAME_CONFIRM: [
                CallbackQueryHandler(finalize_purchase, pattern=r'^CONFIRM_PURCHASE_'),
                CallbackQueryHandler(back_to_config_name_prompt, pattern=r'^back_to_config_name_prompt'),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True,
    )
    application.add_handler(custom_buy_conv_handler)

    
    # 🌟 هندلر دکمه لغو پرداخت (از فایل 1 اضافه شد)
    application.add_handler(CallbackQueryHandler(cancel_payment_callback, pattern="^cancel_payment_"))
    
    application.add_handler(CallbackQueryHandler(back_to_select_server, pattern="^back_to_select_server$"))
    application.add_handler(CommandHandler("tutorial", connection_tutorials_start))
    application.add_handler(MessageHandler(filters.Regex(r"^📚 آموزش اتصال$"), connection_tutorials_start))
    application.add_handler(CallbackQueryHandler(tutorial_category_handler, pattern="^TUTORIAL_CAT_"))
    application.add_handler(CallbackQueryHandler(tutorial_app_handler, pattern="^TUTORIAL_APP_"))
    application.add_handler(CallbackQueryHandler(back_to_tutorial_categories, pattern="^back_to_tutorial_categories$"))
    application.add_handler(CallbackQueryHandler(back_to_main_from_tutorial, pattern="^back_to_main_from_tutorial$"))
    
    application.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^SERVICE_DETAILS_|SHOW_SUB_LINK_|back_to_main_from_services|check_pending_payment|back_to_services|OPEN_MY_SERVICES"))
    
    application.add_handler(MessageHandler(filters.Regex(r"^👤 حساب من$"), my_account))
    application.add_handler(MessageHandler(filters.Regex(r"^📂 سرویس‌های من$"), my_services))
    
    application.add_handler(
        MessageHandler(
            filters.Chat(chat_id=ADMIN_CHAT_IDS) & filters.REPLY & filters.TEXT,
            reply_to_ticket
        )
    )

    logger.info("Bot started and polling...")
    application.run_polling(poll_interval=1.0)

if __name__ == '__main__':
    main()