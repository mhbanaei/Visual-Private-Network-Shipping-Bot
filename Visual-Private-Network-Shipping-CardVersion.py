# Full corrected bot file with card-to-card payment system + Referral System + آموزش اتصال
# Changes applied: 
# 1. Removed Zarinpal gateway completely
# 2. Added card-to-card payment with receipt upload
# 3. Added admin command /add for manual balance update
# 4. Added FREE_TRIAL service (1GB, 1 day, 1 user) with one-time purchase limit
# 5. Added check to prevent renewal of free trial service
# 6. Moved free trial to services list (not separate button in main menu)
# 7. Added Referral System with permanent referral IDs and automatic commission
# 8. Added complete connection tutorial section with Hiddify, V2rayNG, V2Box, etc.
# 9. Added: New user notification to admin
# 10. Added: /announce command for broadcasting to all users
# 11. Added: Restriction - Old users cannot set new referrals
# 12. Added: User profile links for all user IDs + detailed referral info
# 13. Added: Admin command /check for viewing user profile details
# 14. Added: Enhanced /check command with interactive buttons + copyable ID
# 15. Added: Reply handler for /check command
# 16. Added: Complete transaction history view
# 17. Added: Full service details view for admin
# 18. Added: Edit user information functionality
# 19. Added: User investigation with comprehensive data
# 20. Added: User registration by admin
# 21. Added: Complete referral list with pagination
# 22. FIXED: Edit user balance, referral, and notes functionality in /check command
# 23. ADDED: Prevent duplicate processing of receipts by multiple admins
# 24. ADDED: /allmembers command for listing all users with pagination
# 25. ADDED: /addall command for bulk balance adjustment
# 26. ADDED: Admin action logging for /add and /addall commands

import db as storage
import logging
import html
import requests
import json
import os
import re 
import asyncio
import io
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Bot, error, InputFile
import uuid 
import base64 
import time
import datetime 
from typing import Dict, List, Optional, Tuple

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
CARD_NUMBER = "0000000000000000"  # شماره کارت برای واریز

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

# --- تنظیمات رفرال ---
REFERRAL_PERCENT = 20  # درصد رفرال (مثلاً 20٪)
REFERRAL_MIN_AMOUNT = 10000  # حداقل مبلغ شارژ برای احتساب رفرال (تومان)
REFERRAL_BONUS_REFERRALS = 20   # هر ۲۰ نفر رفرال = یک هدیهٔ حجمی (نه یک گیگ به ازای هر نفر)
REFERRAL_BONUS_GB = 20          # مقدار هر هدیه: ۲۰ گیگ، یکجا روی یکی از سرویس‌های خریداری‌شده


def user_referral_percent(user_id) -> float:
    """درصد رفرال مؤثر کاربر: مقدار اختصاصی از پنل ادمین و در غیر این صورت مقدار پیش‌فرض"""
    custom = None
    try:
        custom = (load_users().get(str(user_id)) or {}).get("referral_percent")
    except Exception:
        custom = None
    if custom is not None and custom != "":
        try:
            return float(custom)
        except (TypeError, ValueError):
            pass
    return float(REFERRAL_PERCENT)

# --- وضعیت‌های Conversation ---
STATE_GET_AMOUNT = 1
STATE_GET_TICKET = 2
STATE_WAITING_FOR_CONFIG_NAME = 3
STATE_WAITING_FOR_CONFIG_NAME_CONFIRM = 4
STATE_WAITING_FOR_RENEWAL_NAME = 5
STATE_WAITING_FOR_RENEWAL_CONFIRM = 6
STATE_SELECT_SERVER = 7  
STATE_SELECT_SERVER_FOR_RENEWAL = 8 
STATE_WAITING_FOR_RECEIPT = 9  # وضعیت جدید برای دریافت عکس رسید
STATE_AWAITING_BALANCE_AMOUNT = 10  # وضعیت جدید برای دریافت مبلغ افزایش موجودی
STATE_AWAITING_CONTACT_MESSAGE = 11  # وضعیت جدید برای دریافت پیام تماس
STATE_EDIT_USER_BALANCE = 12  # وضعیت جدید برای ویرایش موجودی کاربر
STATE_EDIT_USER_REFERRAL = 13  # وضعیت جدید برای ویرایش رفرال کاربر
STATE_EDIT_USER_NOTES = 14  # وضعیت جدید برای ویرایش یادداشت کاربر

# --- فایل‌های ذخیره‌سازی دائمی ---
PENDING_PAYMENTS_FILE = 'pending_payments.json'
USERS_FILE = 'users.json'
PENDING_RECEIPTS_FILE = 'pending_receipts.json'  # فایل جدید برای رسیدهای در انتظار تأیید
FREE_TRIAL_USERS_FILE = 'free_trial_users.json'  # فایل جدید برای رصد کاربران تست رایگان
REFERRAL_DATA_FILE = 'referral_data.json'  # فایل جدید برای اطلاعات رفرال
TRANSACTION_HISTORY_FILE = 'transaction_history.json'  # فایل جدید برای تاریخچه تراکنش‌ها

# --- لیست قیمت نهایی (واحد: تومان) ---
SERVICES = {
    "FREE_TRIAL": {"label": "🆓 سرویس تست رایگان", "users": 1, "volume": "1 گیگ", "days": 1, "price_toman": 0, 
                   "description": "سرویس تست رایگان - فقط یک بار برای هر کاربر", "renewable": False},
}

# --- دکمه‌های منوی اصلی ---
MAIN_MENU_KEYBOARD = [
    ["🛍️ خرید سرویس"],
    ["📂 سرویس‌های من", "👤 حساب من"],
    ["💰 شارژ کیف پول", "📞 پشتیبانی"],
    ["🔗 لینک رفرال", "📚 آموزش اتصال"],  # اضافه کردن دکمه آموزش اتصال
]
MAIN_MENU_REPLY_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

# ============================================================
# --- قیمت‌گذاری سفارشی (خرید بی‌نهایت / حجمی) ---
# ============================================================
UNLIMITED_PRICE_PER_USER = 400000      # سرویس بی‌نهایت: هر کاربر ۴۰۰ هزار تومان
VOLUME_PRICE_PER_GB = 2000             # سرویس حجمی: هر گیگ ۲ هزار تومان
VOLUME_MAX_GB = 100                    # حداکثر حجم قابل خرید
CUSTOM_MAX_USERS = 10                  # حداکثر کاربر (بر اساس IP)
CUSTOM_USER_MULTIPLIER = 1.5           # ضریب تصاعدی قیمت برای هر کاربر اضافه
CUSTOM_DAYS = 30                       # اعتبار سرویس سفارشی
MAX_SUBSCRIPTION_DAYS = 30              # سقف اعتبار هر سرویس پس از هر تمدید (۳۰ روز)
STATE_CUSTOM_BUILD = 15                # وضعیت ساخت سرویس سفارشی
CUSTOM_PLANS = {}                      # پلن‌های سفارشی ساخته‌شده در همین اجرا

# ============================================================
# --- محتوای آموزشی برنامه‌های مختلف ---
# ============================================================

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

# دیکشنری برای نگهداری Cookie هر سرور
XUI_AUTH_COOKIES = {}

# ============================================================
# --- توابع کمکی جدید ---
# ============================================================

def get_user_link(user_id: int) -> str:
    """ساخت لینک پروفایل کاربر از شناسه"""
    return f"tg://user?id={user_id}"

def format_user_info(user_id: int, show_copyable: bool = True) -> str:
    """فرمت کردن اطلاعات کاربر با لینک پروفایل و ID قابل کپی"""
    if show_copyable:
        return f"[{user_id}]({get_user_link(user_id)}) (`{user_id}`)"
    else:
        return f"[{user_id}]({get_user_link(user_id)})"

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
        users[str_user_id] = {"balance": 0.0, "services": [], "referral_by": None, "referral_earnings": 0.0, "referrals_count": 0, "notes": "", "created_at": datetime.datetime.now().isoformat()}
        save_users(users)
        return 0.0
    
    return users[str_user_id].get("balance", 0.0)

def update_user_balance(user_id: int, amount_change: float):
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": [], "referral_by": None, "referral_earnings": 0.0, "referrals_count": 0, "notes": "", "created_at": datetime.datetime.now().isoformat()}
    
    current_balance = users[str_user_id].get("balance", 0.0)
    new_balance = current_balance + amount_change
    users[str_user_id]["balance"] = new_balance
    
    save_users(users)
    return new_balance

def add_user_service(user_id: int, config_name: str, sub_link: str, uuid: str, internal_key: str, server_key: str):
    """ذخیره جزئیات کانفیگ خریداری شده همراه با شناسه سرور"""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users or 'services' not in users[str_user_id]:
        users[str_user_id] = {"balance": users.get(str_user_id, {}).get("balance", 0.0), "services": [], "referral_by": None, "referral_earnings": 0.0, "referrals_count": 0, "notes": "", "created_at": datetime.datetime.now().isoformat()}
    
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

def update_user_notes(user_id: int, notes: str) -> bool:
    """به‌روزرسانی یادداشت‌های کاربر"""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id in users:
        users[str_user_id]["notes"] = notes
        save_users(users)
        return True
    return False

def get_user_notes(user_id: int) -> str:
    """دریافت یادداشت‌های کاربر"""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id in users:
        return users[str_user_id].get("notes", "")
    return ""

# ============================================================
# --- توابع جدید برای ارسال لاگ اقدامات ادمین ---
# ============================================================

async def send_admin_action_log(context: ContextTypes.DEFAULT_TYPE, admin_id: int, action_type: str, details: dict):
    """
    ارسال لاگ اقدامات ادمین به تمام ادمین‌ها
    
    پارامترها:
    - admin_id: شناسه ادمین انجام‌دهنده عمل
    - action_type: نوع عمل ('add', 'addall', 'edit', 'announce', etc.)
    - details: جزئیات عمل
    """
    # تغییر 1: استفاده از await برای دریافت اطلاعات ادمین
    try:
        admin_chat = await context.bot.get_chat(admin_id)
        admin_name = admin_chat.first_name or 'Admin'
    except Exception as e:
        logger.error(f"Failed to get admin info for {admin_id}: {e}")
        admin_name = 'Admin'
    
    # ساخت پیام لاگ بر اساس نوع عمل
    if action_type == 'add':
        target_user_id = details.get('target_user_id')
        amount = details.get('amount')
        new_balance = details.get('new_balance')
        
        message = f"👑 **لاگ اقدام ادمین: افزایش موجودی**\n\n"
        message += f"👤 **ادمین:** {format_user_info(admin_id)}\n"
        message += f"🎯 **کاربر هدف:** {format_user_info(target_user_id)}\n"
        message += f"💰 **مبلغ:** {amount:,.0f} تومان\n"
        message += f"💳 **موجودی جدید کاربر:** {new_balance:,.0f} تومان\n"
        message += f"📅 **زمان:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
        
    elif action_type == 'addall':
        amount = details.get('amount')
        affected_users = details.get('affected_users', 0)
        total_amount = details.get('total_amount', 0)
        
        message = f"👑 **لاگ اقدام ادمین: افزایش موجودی گروهی**\n\n"
        message += f"👤 **ادمین:** {format_user_info(admin_id)}\n"
        message += f"💰 **مبلغ به ازای هر کاربر:** {amount:,.0f} تومان\n"
        message += f"👥 **تعداد کاربران تأثیرپذیر:** {affected_users} نفر\n"
        message += f"💰 **مجموع مبلغ:** {total_amount:,.0f} تومان\n"
        message += f"📅 **زمان:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
        
    elif action_type == 'edit':
        target_user_id = details.get('target_user_id')
        field = details.get('field')
        old_value = details.get('old_value')
        new_value = details.get('new_value')
        
        message = f"👑 **لاگ اقدام ادمین: ویرایش اطلاعات کاربر**\n\n"
        message += f"👤 **ادمین:** {format_user_info(admin_id)}\n"
        message += f"🎯 **کاربر هدف:** {format_user_info(target_user_id)}\n"
        message += f"📝 **فیلد ویرایش شده:** {field}\n"
        message += f"📊 **مقدار قبلی:** {old_value}\n"
        message += f"📊 **مقدار جدید:** {new_value}\n"
        message += f"📅 **زمان:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
    
    else:
        message = f"👑 **لاگ اقدام ادمین**\n\n"
        message += f"👤 **ادمین:** {format_user_info(admin_id)}\n"
        message += f"🎯 **عمل:** {action_type}\n"
        message += f"📋 **جزئیات:** {json.dumps(details, ensure_ascii=False, indent=2)}\n"
        message += f"📅 **زمان:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
    
    # ارسال به تمام ادمین‌ها
    for admin_chat_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send admin action log to admin {admin_chat_id}: {e}")
# ============================================================
# --- تابع جدید برای ارسال لاگ خرید به ادمین‌ها ---
# ============================================================

async def send_service_purchase_log_to_admins(context: ContextTypes.DEFAULT_TYPE, log_data: dict):
    """
    ارسال لاگ کامل خرید سرویس به تمام ادمین‌ها
    
    پارامترها:
    - log_data: دیکشنری حاوی اطلاعات خرید
    """
    user_id = log_data.get('user_id')
    config_name = log_data.get('config_name')
    server_key = log_data.get('server_key')
    server_name = log_data.get('server_name')
    internal_key = log_data.get('internal_key')
    service_label = log_data.get('service_label')
    volume_gb = log_data.get('volume_gb')
    days = log_data.get('days')
    price_toman = log_data.get('price_toman')
    old_balance = log_data.get('old_balance')
    new_balance = log_data.get('new_balance')
    vmess_link = log_data.get('vmess_link')
    sub_link = log_data.get('sub_link')
    uuid = log_data.get('uuid')
    client_count = log_data.get('client_count', 1)
    log_type = log_data.get('log_type', 'purchase')  # purchase یا renewal
    
    if log_type == 'purchase':
        title = "🛒 خرید جدید سرویس"
        emoji = "🛒"
        action = "خریداری شد"
    else:
        title = "🔁 تمدید سرویس"
        emoji = "🔁"
        action = "تمدید شد"
    
    # ساخت پیام لاگ
    message = f"{emoji} **{title}**\n\n"
    message += f"👤 **کاربر:** {format_user_info(user_id, show_copyable=False)}\n"
    message += f"🆔 **شناسه کاربر:** `{user_id}`\n"
    message += f"📛 **نام کانفیگ:** `{config_name}`\n"
    message += f"🌐 **سرور:** {server_name} (`{server_key}`)\n"
    message += f"🛍️ **سرویس:** {service_label}\n"
    
    if sub_link:
        message += f"\n🔗 **لینک اشتراک:**\n`{sub_link}`\n"
    
    if internal_key == "FREE_TRIAL":
        message += f"🎯 **نوع سرویس:** 🆓 تست رایگان\n"
    else:
        message += f"🎯 **نوع سرویس:** 💰 پولی\n"
    
    message += f"💾 **حجم:** {volume_gb} گیگابایت\n"
    message += f"📅 **اعتبار:** {days} روز\n"
    message += f"👥 **تعداد کاربر مجاز:** {client_count} نفر\n"
    
    if price_toman > 0:
        message += f"💰 **هزینه:** {price_toman:,.0f} تومان\n"
        message += f"💳 **موجودی قبل:** {old_balance:,.0f} تومان\n"
        message += f"💳 **موجودی بعد:** {new_balance:,.0f} تومان\n"
        message += f"📉 **مبلغ کسر شده:** {price_toman:,.0f} تومان\n"
    else:
        message += f"💰 **هزینه:** رایگان\n"
        message += f"💳 **موجودی کاربر:** {old_balance:,.0f} تومان\n"
    
    # اطلاعات رفرال
    referral_info = get_user_referral_info(user_id)
    referral_by = referral_info.get("referral_by")
    if referral_by:
        message += f"🔗 **رفرال دهنده:** {format_user_info(referral_by, show_copyable=False)}\n"
    
    # اطلاعات سرویس‌های قبلی کاربر
    services = get_user_services(user_id)
    message += f"📊 **تعداد کل سرویس‌های کاربر:** {len(services)} عدد\n"
    
    # اطلاعات فنی
    message += f"\n🔧 **اطلاعات فنی:**\n"
    message += f"🆔 **UUID:** `{uuid}`\n"
    
    message += f"🕒 **زمان {action}:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n"
    
    # ارسال به تمام ادمین‌ها
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="Markdown"
            )
            
                    
        except Exception as e:
            logger.error(f"Failed to send service log to admin {admin_id}: {e}")
            
# ============================================================
# --- توابع مدیریت تاریخچه تراکنش‌ها ---
# ============================================================

def load_transaction_history() -> dict:
    return storage.load_transaction_history()
def save_transaction_history(history: dict):
    storage.save_transaction_history(history)
def add_transaction(user_id: int, transaction_type: str, amount: float, description: str = "", admin_id: int = None) -> str:
    """افزودن تراکنش جدید به تاریخچه"""
    history = load_transaction_history()
    str_user_id = str(user_id)
    
    if str_user_id not in history:
        history[str_user_id] = []
    
    transaction_id = str(int(time.time() * 1000))
    
    transaction = {
        'id': transaction_id,
        'type': transaction_type,  # 'deposit', 'withdrawal', 'purchase', 'renewal', 'referral_earning', 'admin_adjustment'
        'amount': amount,
        'description': description,
        'timestamp': datetime.datetime.now().isoformat(),
        'admin_id': admin_id
    }
    
    history[str_user_id].append(transaction)
    
    # فقط 100 تراکنش آخر رو نگه دار
    if len(history[str_user_id]) > 100:
        history[str_user_id] = history[str_user_id][-100:]
    
    save_transaction_history(history)
    return transaction_id

def get_user_transactions(user_id: int, limit: int = 50) -> list:
    """دریافت تاریخچه تراکنش‌های کاربر"""
    history = load_transaction_history()
    str_user_id = str(user_id)
    
    if str_user_id in history:
        return history[str_user_id][-limit:] if limit > 0 else history[str_user_id]
    return []

# ============================================================
# --- توابع مدیریت کاربران تست رایگان ---
# ============================================================

def load_free_trial_users() -> dict:
    return storage.load_free_trial_users()
def save_free_trial_users(users: dict):
    storage.save_free_trial_users(users)
def has_user_used_free_trial(user_id: int) -> bool:
    """بررسی اینکه آیا کاربر قبلاً از تست رایگان استفاده کرده است"""
    users = load_free_trial_users()
    return str(user_id) in users

def mark_free_trial_used(user_id: int):
    """علامت‌گذاری کاربر به عنوان استفاده‌کننده از تست رایگان"""
    users = load_free_trial_users()
    users[str(user_id)] = {
        'used_date': datetime.datetime.now().isoformat(),
        'user_id': user_id
    }
    save_free_trial_users(users)

# ============================================================
# --- توابع مدیریت رسیدهای در انتظار (سیستم جدید کارت به کارت) ---
# ============================================================

def load_pending_receipts() -> dict:
    return storage.load_pending_receipts()
def save_pending_receipts(receipts: dict):
    storage.save_pending_receipts(receipts)
def add_pending_receipt(user_id: int, amount_toman: int, receipt_file_id: str) -> str:
    """افزودن رسید جدید به لیست در انتظار"""
    receipts = load_pending_receipts()
    receipt_id = str(int(time.time() * 1000))  # شناسه یکتا بر اساس زمان
    
    receipts[receipt_id] = {
        'user_id': user_id,
        'amount_toman': amount_toman,
        'receipt_file_id': receipt_file_id,
        'timestamp': datetime.datetime.now().isoformat(),
        'status': 'pending',  # pending, approved, rejected
        'processed_by': None,  # شناسه ادمینی که رسید را پردازش کرده
        'processed_at': None,   # زمان پردازش
        'admin_message_ids': {}  # جدید: ذخیره message_id برای هر ادمین
    }
    
    save_pending_receipts(receipts)
    return receipt_id

def update_admin_message_ids(receipt_id: str, admin_id: int, message_id: int):
    """ذخیره message_id پیام ارسالی به یک ادمین"""
    receipts = load_pending_receipts()
    if receipt_id in receipts:
        if 'admin_message_ids' not in receipts[receipt_id]:
            receipts[receipt_id]['admin_message_ids'] = {}
        receipts[receipt_id]['admin_message_ids'][str(admin_id)] = message_id
        save_pending_receipts(receipts)
        
async def update_all_admin_receipt_messages(context: ContextTypes.DEFAULT_TYPE, receipt_id: str, 
                                           new_caption: str, remove_buttons: bool = True):
    """به‌روزرسانی همه پیام‌های رسید برای تمام ادمین‌ها"""
    receipts = load_pending_receipts()
    if receipt_id not in receipts:
        return
    
    receipt = receipts[receipt_id]
    admin_message_ids = receipt.get('admin_message_ids', {})
    
    for str_admin_id, message_id in admin_message_ids.items():
        try:
            admin_id = int(str_admin_id)
            if remove_buttons:
                # ویرایش پیام و حذف دکمه‌ها
                await context.bot.edit_message_caption(
                    chat_id=admin_id,
                    message_id=message_id,
                    caption=new_caption,
                    parse_mode="Markdown"
                )
            else:
                # فقط ویرایش کپشن
                await context.bot.edit_message_caption(
                    chat_id=admin_id,
                    message_id=message_id,
                    caption=new_caption,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to update receipt message for admin {str_admin_id}: {e}")


def get_pending_receipt(receipt_id: str) -> dict:
    """دریافت اطلاعات یک رسید"""
    receipts = load_pending_receipts()
    return receipts.get(receipt_id)

def update_receipt_status(receipt_id: str, status: str, admin_id: int = None):
    """به‌روزرسانی وضعیت رسید"""
    receipts = load_pending_receipts()
    if receipt_id in receipts:
        receipts[receipt_id]['status'] = status
        if admin_id:
            receipts[receipt_id]['processed_by'] = admin_id
            receipts[receipt_id]['processed_at'] = datetime.datetime.now().isoformat()
        save_pending_receipts(receipts)
        return True
    return False

def is_receipt_processed(receipt_id: str) -> tuple[bool, dict | None]:
    """بررسی اینکه آیا رسید قبلاً پردازش شده است"""
    receipts = load_pending_receipts()
    if receipt_id in receipts:
        receipt = receipts[receipt_id]
        if receipt['status'] != 'pending':
            return True, receipt
        return False, receipt  # 🔴 تغییر این خط - برگرداندن receipt حتی اگر pending باشد
    return False, None
    
def process_receipt_atomic(receipt_id: str, status: str, admin_id: int) -> tuple[bool, dict | None]:
    """پردازش اتمی رسید - فقط یک بار توسط یک ادمین قابل پردازش است"""
    receipts = load_pending_receipts()
    
    if receipt_id not in receipts:
        return False, None
    
    receipt = receipts[receipt_id]
    
    # اگر رسید قبلاً پردازش شده باشد
    if receipt['status'] != 'pending':
        return False, receipt
    
    # پردازش رسید
    receipt['status'] = status
    receipt['processed_by'] = admin_id
    receipt['processed_at'] = datetime.datetime.now().isoformat()
    
    save_pending_receipts(receipts)
    return True, receipt
    
# ============================================================
# --- توابع مدیریت سیستم رفرال ---
# ============================================================

def load_referral_data() -> dict:
    return storage.load_referral_data()
def save_referral_data(data: dict):
    storage.save_referral_data(data)
def get_user_referral_info(user_id: int) -> dict:
    """دریافت اطلاعات رفرال کاربر"""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": [], "referral_by": None, "referral_earnings": 0.0, "referrals_count": 0, "notes": "", "created_at": datetime.datetime.now().isoformat()}
        save_users(users)
    
    return {
        "referral_by": users[str_user_id].get("referral_by"),
        "referral_earnings": users[str_user_id].get("referral_earnings", 0.0),
        "referrals_count": users[str_user_id].get("referrals_count", 0)
    }

def set_user_referral(user_id: int, referred_by: int) -> bool:
    """تنظیم رفرال برای کاربر (فقط اگر قبلاً تنظیم نشده باشد و کاربر جدید باشد)"""
    users = load_users()
    str_user_id = str(user_id)
    str_referred_by = str(referred_by)
    
    # اگر کاربر از قبل در سیستم وجود داشته باشد (قدیمی باشد)، اجازه تنظیم رفرال جدید را نده
    if str_user_id in users:
        logger.info(f"User {user_id} already exists in system, cannot set new referral.")
        return False
    
    # اگر کاربر سعی کند خودش را رفرال کند
    if user_id == referred_by:
        return False
    
    # تنظیم رفرال
    users[str_user_id] = {"balance": 0.0, "services": [], "referral_by": referred_by, "referral_earnings": 0.0, "referrals_count": 0, "notes": "", "created_at": datetime.datetime.now().isoformat()}
    
    # افزایش تعداد رفرال‌های رفرال دهنده
    if str_referred_by in users:
        users[str_referred_by]["referrals_count"] = users[str_referred_by].get("referrals_count", 0) + 1
    else:
        users[str_referred_by] = {"balance": 0.0, "services": [], "referral_by": None, "referral_earnings": 0.0, "referrals_count": 1, "notes": "", "created_at": datetime.datetime.now().isoformat()}
    
    save_users(users)
    
    # ذخیره در تاریخچه رفرال‌ها
    referral_data = load_referral_data()
    if str_referred_by not in referral_data["referrals"]:
        referral_data["referrals"][str_referred_by] = []
    
    referral_data["referrals"][str_referred_by].append({
        "user_id": user_id,
        "date": datetime.datetime.now().isoformat(),
        "status": "active"
    })
    
    save_referral_data(referral_data)
    logger.info(f"User {user_id} referred by {referred_by}")
    return True

def add_referral_earning(referred_user_id: int, amount_toman: int) -> tuple[float, int]:
    """اضافه کردن درآمد رفرال به حساب رفرال دهنده و برگرداندن اطلاعات رفرال دهنده"""
    users = load_users()
    str_referred_user_id = str(referred_user_id)
    
    if str_referred_user_id not in users:
        return 0.0, None
    
    referred_by = users[str_referred_user_id].get("referral_by")
    if referred_by is None:
        return 0.0, None
    
    str_referred_by = str(referred_by)
    
    # درصد پورسانت: مقدار اختصاصی کاربر (از پنل ادمین) و در غیر این صورت مقدار پیش‌فرض
    custom_percent = users.get(str_referred_by, {}).get("referral_percent")
    try:
        percent = float(custom_percent) if custom_percent is not None and custom_percent != "" else float(REFERRAL_PERCENT)
    except (TypeError, ValueError):
        percent = float(REFERRAL_PERCENT)

    # محاسبه پورسانت
    referral_earning = (amount_toman * percent) / 100
    
    # افزایش موجودی رفرال دهنده
    if str_referred_by in users:
        current_balance = users[str_referred_by].get("balance", 0.0)
        users[str_referred_by]["balance"] = current_balance + referral_earning
        
        # افزایش مجموع درآمدهای رفرال
        current_earnings = users[str_referred_by].get("referral_earnings", 0.0)
        users[str_referred_by]["referral_earnings"] = current_earnings + referral_earning
    else:
        users[str_referred_by] = {
            "balance": referral_earning,
            "services": [],
            "referral_by": None,
            "referral_earnings": referral_earning,
            "referrals_count": 1,
            "notes": "",
            "created_at": datetime.datetime.now().isoformat()
        }
    
    save_users(users)
    
    # ذخیره در تاریخچه درآمدها
    referral_data = load_referral_data()
    if "earnings_history" not in referral_data:
        referral_data["earnings_history"] = {}
    
    if str_referred_by not in referral_data["earnings_history"]:
        referral_data["earnings_history"][str_referred_by] = []
    
    referral_data["earnings_history"][str_referred_by].append({
        "from_user": referred_user_id,
        "amount": referral_earning,
        "original_amount": amount_toman,
        "percent": percent,
        "date": datetime.datetime.now().isoformat()
    })
    
    save_referral_data(referral_data)
    
    # اضافه کردن تراکنش به تاریخچه
    add_transaction(referred_by, "referral_earning", referral_earning, f"کمیسیون رفرال از کاربر {referred_user_id}")
    
    logger.info(f"Added {referral_earning} تومان referral earning to user {referred_by} from user {referred_user_id}")
    return referral_earning, referred_by

def get_referral_history(referrer_id: int) -> list:
    """دریافت تاریخچه رفرال‌های یک کاربر"""
    referral_data = load_referral_data()
    str_referrer_id = str(referrer_id)
    
    if str_referrer_id in referral_data.get("referrals", {}):
        return referral_data["referrals"][str_referrer_id]
    return []

def get_referral_bonus_info(user_id: int) -> dict:
    """وضعیت هدیهٔ حجمی رفرال: هر ۲۰ نفر رفرال = ۲۰ گیگ یکجا روی یک سرویس"""
    referral_info = get_user_referral_info(user_id)
    count = int(referral_info.get("referrals_count", 0) or 0)
    data = load_referral_data()
    record = (data.get("bonus_claims") or {}).get(str(user_id)) or {}
    claimed = int(record.get("claimed", 0) or 0)
    earned = count // REFERRAL_BONUS_REFERRALS
    return {
        "referrals_count": count,
        "claimed": claimed,
        "earned": earned,
        "available": max(0, earned - claimed),
        "remainder": count % REFERRAL_BONUS_REFERRALS,
        "to_next": REFERRAL_BONUS_REFERRALS - (count % REFERRAL_BONUS_REFERRALS),
        "gb": REFERRAL_BONUS_GB,
    }


def record_referral_bonus_claim(user_id: int, config_name: str) -> None:
    """ثبت دریافت یک هدیهٔ حجمی رفرال روی سرویس مشخص"""
    data = load_referral_data()
    claims = data.setdefault("bonus_claims", {})
    record = claims.setdefault(str(user_id), {"claimed": 0, "history": []})
    record["claimed"] = int(record.get("claimed", 0) or 0) + 1
    record.setdefault("history", []).append({
        "config_name": config_name,
        "gb": REFERRAL_BONUS_GB,
        "date": datetime.datetime.now().isoformat(),
    })
    save_referral_data(data)


def get_referral_earnings_history(referrer_id: int) -> list:
    """دریافت تاریخچه درآمدهای رفرال یک کاربر"""
    referral_data = load_referral_data()
    str_referrer_id = str(referrer_id)
    
    if str_referrer_id in referral_data.get("earnings_history", {}):
        return referral_data["earnings_history"][str_referrer_id]
    return []

# ============================================================
# --- توابع جدید برای قابلیت‌های ادمین ---
# ============================================================

async def show_transaction_details(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page: int = 1):
    """نمایش تاریخچه تراکنش‌های کاربر با اطلاعات ادمین - اصلاح شده"""
    query = update.callback_query
    await query.answer("در حال دریافت تاریخچه تراکنش‌ها...")
    
    # دریافت تراکنش‌ها
    transactions = get_user_transactions(target_user_id, limit=0)
    
    if not transactions:
        message_text = f"📊 **تاریخچه تراکنش‌های کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n❌ هیچ تراکنشی یافت نشد."
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return
    
    # محاسبه مجموع‌ها
    total_deposit = sum(t['amount'] for t in transactions if t['type'] in ['deposit', 'admin_adjustment', 'referral_earning'])
    total_withdrawal = sum(t['amount'] for t in transactions if t['type'] in ['purchase', 'renewal'])
    net_balance = total_deposit - total_withdrawal
    
    # صفحه‌بندی
    items_per_page = 10
    total_pages = (len(transactions) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(transactions))
    
    # ساخت پیام
    message_text = f"📊 **تاریخچه تراکنش‌های کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
    message_text += f"📈 **آمار کلی:**\n"
    message_text += f"• مجموع واریزی: {total_deposit:,.0f} تومان\n"
    message_text += f"• مجموع برداشت: {total_withdrawal:,.0f} تومان\n"
    message_text += f"• موجودی خالص: {net_balance:,.0f} تومان\n\n"
    
    message_text += f"📋 **تراکنش‌ها (صفحه {page} از {total_pages}):**\n"
    
    # نمایش تراکنش‌های صفحه جاری
    for i, trans in enumerate(transactions[start_idx:end_idx], start_idx + 1):
        try:
            date = datetime.datetime.fromisoformat(trans['timestamp']).strftime("%Y/%m/%d %H:%M")
        except:
            date = trans['timestamp']
        
        # تعیین نوع تراکنش
        type_emoji = {
            'deposit': '💰',
            'withdrawal': '💸',
            'purchase': '🛍️',
            'renewal': '🔁',
            'referral_earning': '🎁',
            'admin_adjustment': '👑'
        }.get(trans['type'], '📝')
        
        type_name = {
            'deposit': 'واریز',
            'withdrawal': 'برداشت',
            'purchase': 'خرید سرویس',
            'renewal': 'تمدید سرویس',
            'referral_earning': 'درآمد رفرال',
            'admin_adjustment': 'تغییر توسط ادمین'
        }.get(trans['type'], trans['type'])
        
        description = trans.get('description', '')
        admin_id = trans.get('admin_id')
        
        description_lines = []
        if description:
            description_lines.append(f"   ↳ {description}")
        
        # اضافه کردن اطلاعات ادمین اگر وجود دارد
        if admin_id:
            admin_link = format_user_info(admin_id, show_copyable=False)
            description_lines.append(f"   ↳ توسط ادمین: {admin_link}")
        
        description_text = "\n".join(description_lines) if description_lines else ""
        
        message_text += f"{i}. {type_emoji} **{type_name}** - {trans['amount']:,.0f} تومان ({date}){description_text}\n"
    
    # دکمه‌های صفحه‌بندی
    keyboard = []
    
    # دکمه‌های صفحه‌بندی
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"transaction_details_{target_user_id}_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=f"transaction_page_info"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"transaction_details_{target_user_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit transaction message: {e}")
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def show_service_details_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page: int = 1):
    """نمایش جزئیات سرویس‌های کاربر برای ادمین"""
    query = update.callback_query
    await query.answer("در حال دریافت جزئیات سرویس‌ها...")
    
    services = get_user_services(target_user_id)
    
    if not services:
        message_text = f"📂 **سرویس‌های کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n❌ هیچ سرویسی یافت نشد."
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return
    
    # صفحه‌بندی
    items_per_page = 5
    total_pages = (len(services) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(services))
    
    # ساخت پیام
    message_text = f"📂 **سرویس‌های کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n"
    message_text += f"📊 تعداد سرویس‌ها: {len(services)} عدد\n\n"
    
    message_text += f"📋 **لیست سرویس‌ها (صفحه {page} از {total_pages}):**\n"
    
    # نمایش سرویس‌های صفحه جاری
    for i, service in enumerate(services[start_idx:end_idx], start_idx + 1):
        config_name = service.get('config_name', 'نامشخص')
        server_key = service.get('server_key', 'نامشخص')
        server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', server_key)
        internal_key = service.get('internal_key', 'نامشخص')
        service_type = SERVICES.get(internal_key, {}).get('label', internal_key)
        purchase_date = service.get('purchase_date', 'نامشخص')
        
        try:
            purchase_date_formatted = datetime.datetime.fromisoformat(purchase_date).strftime("%Y/%m/%d")
        except:
            purchase_date_formatted = purchase_date
        
        message_text += f"\n{i}. **{config_name}**\n"
        message_text += f"   ├─ نوع: {service_type}\n"
        message_text += f"   ├─ سرور: {server_name}\n"
        message_text += f"   └─ تاریخ خرید: {purchase_date_formatted}\n"
        
        # دریافت اطلاعات از سرور
        client_index, client_data = await xui_get_client_info_by_name(server_key, config_name)
        if client_data:
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
                expiry_date_str = expiry_date.strftime("%Y/%m/%d")
            
            message_text += f"   ├─ ترافیک: {remaining_display} از {total_display}\n"
            message_text += f"   └─ انقضا: {expiry_date_str}\n"
    
    # دکمه‌های صفحه‌بندی
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"service_details_{target_user_id}_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=f"service_page_info"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"service_details_{target_user_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # دکمه‌های عملیاتی
    keyboard.append([
        InlineKeyboardButton("🔍 بررسی تک‌تک سرویس‌ها", callback_data=f"check_each_service_{target_user_id}"),
        InlineKeyboardButton("🗑️ حذف سرویس‌ها", callback_data=f"delete_services_{target_user_id}")
    ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit service details message: {e}")
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def edit_user_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """شروع فرآیند ویرایش اطلاعات کاربر"""
    query = update.callback_query
    await query.answer("شروع ویرایش اطلاعات کاربر...")
    
    users = load_users()
    str_target_user_id = str(target_user_id)
    
    if str_target_user_id not in users:
        await query.answer("❌ کاربر در سیستم وجود ندارد.", show_alert=True)
        return
    
    user_data = users[str_target_user_id]
    
    message_text = f"✏️ **ویرایش اطلاعات کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
    message_text += f"💰 موجودی فعلی: {user_data.get('balance', 0):,.0f} تومان\n"
    message_text += f"🔗 رفرال دهنده: {user_data.get('referral_by', 'ندارد')}\n"
    message_text += f"📝 یادداشت: {user_data.get('notes', 'ندارد')}\n\n"
    message_text += "لطفاً گزینه مورد نظر برای ویرایش را انتخاب کنید:"
    
    keyboard = [
        [InlineKeyboardButton("💰 ویرایش موجودی", callback_data=f"edit_balance_{target_user_id}")],
        [InlineKeyboardButton("🔗 ویرایش رفرال دهنده", callback_data=f"edit_referral_{target_user_id}")],
        [InlineKeyboardButton("📝 ویرایش یادداشت", callback_data=f"edit_notes_{target_user_id}")],
        [InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def edit_user_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش موجودی کاربر"""
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split("edit_balance_")[1])
    context.user_data['edit_balance_target'] = target_user_id
    
    await query.edit_message_text(
        f"💰 **ویرایش موجودی کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
        f"لطفاً موجودی جدید را به تومان وارد کنید:\n"
        f"مثال: 50000",
        parse_mode="Markdown"
    )

async def edit_user_referral_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش رفرال دهنده کاربر"""
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split("edit_referral_")[1])
    context.user_data['edit_referral_target'] = target_user_id
    
    await query.edit_message_text(
        f"🔗 **ویرایش رفرال دهنده کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
        f"لطفاً شناسه کاربری رفرال دهنده جدید را وارد کنید:\n"
        f"مثال: 123456789\n\n"
        f"اگر می‌خواهید رفرال دهنده حذف شود، عدد 0 را وارد کنید.",
        parse_mode="Markdown"
    )

async def edit_user_notes_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش یادداشت کاربر"""
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split("edit_notes_")[1])
    context.user_data['edit_notes_target'] = target_user_id
    
    await query.edit_message_text(
        f"📝 **ویرایش یادداشت کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
        f"لطفاً یادداشت جدید را وارد کنید:",
        parse_mode="Markdown"
    )

async def handle_admin_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر یکپارچه برای دریافت ورودی‌های ویرایش ادمین"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        return
    
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # ارسال پیام مستقیم ادمین به کاربر
    if 'contact_user_target' in context.user_data:
        target_user_id = context.user_data.pop('contact_user_target')
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="📩 پیام از پشتیبانی:" + chr(10) + chr(10) + text
            )
            await update.message.reply_text(f"✅ پیام برای کاربر {target_user_id} ارسال شد.")
        except Exception as exc:
            await update.message.reply_text(f"❌ ارسال پیام ناموفق بود: {exc}")
        return
    
    # بررسی اینکه آیا در حال ویرایش موجودی هستیم
    if 'edit_balance_target' in context.user_data:
        target_user_id = context.user_data['edit_balance_target']
        
        try:
            new_balance = float(text.replace(',', ''))
            if new_balance < 0:
                await update.message.reply_text("❌ موجودی نمی‌تواند منفی باشد.")
                return
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
            return
        
        # به‌روزرسانی موجودی
        users = load_users()
        str_target_user_id = str(target_user_id)
        
        if str_target_user_id in users:
            old_balance = users[str_target_user_id].get("balance", 0)
            users[str_target_user_id]["balance"] = new_balance
            save_users(users)
            
            # افزودن به تاریخچه تراکنش‌ها
            amount_change = new_balance - old_balance
            if amount_change != 0:
                transaction_type = "admin_adjustment"
                add_transaction(target_user_id, transaction_type, amount_change, 
                               f"تغییر موجودی توسط ادمین (قدیمی: {old_balance:,.0f} تومان)", update.effective_user.id)
            
            # ارسال لاگ به ادمین‌ها
            await send_admin_action_log(context, update.effective_user.id, 'edit', {
                'target_user_id': target_user_id,
                'field': 'balance',
                'old_value': f"{old_balance:,.0f} تومان",
                'new_value': f"{new_balance:,.0f} تومان"
            })
            
            await update.message.reply_text(
                f"✅ موجودی کاربر {format_user_info(target_user_id)} به {new_balance:,.0f} تومان تغییر یافت.\n\n"
                f"تغییر: {amount_change:+,.0f} تومان",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ کاربر {target_user_id} پیدا نشد.")
        
        # پاک کردن وضعیت
        context.user_data.pop('edit_balance_target', None)
    
    # بررسی اینکه آیا در حال ویرایش رفرال هستیم
    elif 'edit_referral_target' in context.user_data:
        target_user_id = context.user_data['edit_referral_target']
        input_text = text
        
        try:
            if input_text == "0":
                referred_by = None
            else:
                referred_by = int(input_text)
                
                # بررسی اینکه کاربر نمی‌تواند خودش را رفرال دهد
                if referred_by == target_user_id:
                    await update.message.reply_text("❌ کاربر نمی‌تواند خودش را رفرال دهد.")
                    return
                    
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید یا 0 برای حذف رفرال.")
            return
        
        # به‌روزرسانی رفرال
        users = load_users()
        str_target_user_id = str(target_user_id)
        
        if str_target_user_id in users:
            old_referral = users[str_target_user_id].get("referral_by")
            users[str_target_user_id]["referral_by"] = referred_by
            
            # اگر رفرال دهنده تغییر کرد، آمار رفرال‌ها را به‌روزرسانی کن
            if old_referral != referred_by:
                # کاهش تعداد رفرال‌های رفرال دهنده قدیمی
                if old_referral:
                    str_old_referral = str(old_referral)
                    if str_old_referral in users:
                        users[str_old_referral]["referrals_count"] = max(0, users[str_old_referral].get("referrals_count", 1) - 1)
                
                # افزایش تعداد رفرال‌های رفرال دهنده جدید
                if referred_by:
                    str_referred_by = str(referred_by)
                    if str_referred_by in users:
                        users[str_referred_by]["referrals_count"] = users[str_referred_by].get("referrals_count", 0) + 1
                    else:
                        # اگر رفرال دهنده جدید در سیستم نیست، او را ثبت کن
                        users[str_referred_by] = {
                            "balance": 0.0,
                            "services": [],
                            "referral_by": None,
                            "referral_earnings": 0.0,
                            "referrals_count": 1,
                            "notes": "",
                            "created_at": datetime.datetime.now().isoformat()
                        }
            
            save_users(users)
            
            # افزودن به تاریخچه تراکنش‌ها
            admin_info = format_user_info(update.effective_user.id, show_copyable=False)
            description = f"تغییر رفرال توسط ادمین {admin_info} (قدیمی: {old_referral if old_referral else 'ندارد'})"
            add_transaction(target_user_id, "admin_adjustment", 0, description, update.effective_user.id)
            
            # ارسال لاگ به ادمین‌ها
            await send_admin_action_log(context, update.effective_user.id, 'edit', {
                'target_user_id': target_user_id,
                'field': 'referral',
                'old_value': str(old_referral) if old_referral else 'ندارد',
                'new_value': str(referred_by) if referred_by else 'ندارد'
            })
            
            await update.message.reply_text(
                f"✅ رفرال دهنده کاربر {format_user_info(target_user_id)} به {referred_by if referred_by else 'هیچ‌کس'} تغییر یافت.\n\n"
                f"توسط ادمین: {admin_info}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ کاربر {target_user_id} پیدا نشد.")
        
        # پاک کردن وضعیت
        context.user_data.pop('edit_referral_target', None)
    
    # بررسی اینکه آیا در حال ویرایش یادداشت هستیم
    elif 'edit_notes_target' in context.user_data:
        target_user_id = context.user_data['edit_notes_target']
        new_notes = text
        
        # به‌روزرسانی یادداشت
        if update_user_notes(target_user_id, new_notes):
            # افزودن به تاریخچه تراکنش‌ها
            admin_info = format_user_info(update.effective_user.id, show_copyable=False)
            description = f"ویرایش یادداشت توسط ادمین {admin_info}"
            add_transaction(target_user_id, "admin_adjustment", 0, description, update.effective_user.id)
            
            # ارسال لاگ به ادمین‌ها
            await send_admin_action_log(context, update.effective_user.id, 'edit', {
                'target_user_id': target_user_id,
                'field': 'notes',
                'old_value': get_user_notes(target_user_id),
                'new_value': new_notes
            })
            
            await update.message.reply_text(
                f"✅ یادداشت کاربر {format_user_info(target_user_id)} به‌روزرسانی شد.\n\n"
                f"📝 یادداشت جدید: {new_notes}\n"
                f"توسط ادمین: {admin_info}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ کاربر {target_user_id} پیدا نشد.")
        
        # پاک کردن وضعیت
        context.user_data.pop('edit_notes_target', None)
    
    # اگر هیچ‌کدام از حالت‌های ویرایش فعال نیست
    else:
        # بررسی سایر حالت‌های ادمین
        if 'awaiting_amount_for' in context.user_data:
            target_user_id = context.user_data['awaiting_amount_for']
            
            try:
                amount = float(text.replace(',', ''))
                if amount <= 0:
                    await update.message.reply_text("❌ مبلغ باید بزرگتر از صفر باشد.")
                    return
            except ValueError:
                await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
                return
            
            # افزایش موجودی
            new_balance = update_user_balance(target_user_id, amount)
            
            # افزودن به تاریخچه تراکنش‌ها
            add_transaction(target_user_id, "admin_adjustment", amount, f"افزایش موجودی توسط ادمین", update.effective_user.id)
            
            # ارسال لاگ به ادمین‌ها
            await send_admin_action_log(context, update.effective_user.id, 'add', {
                'target_user_id': target_user_id,
                'amount': amount,
                'new_balance': new_balance
            })
            
            # اطلاع به ادمین
            await update.message.reply_text(
                f"✅ موجودی کاربر {format_user_info(target_user_id)} به میزان {amount:,.0f} تومان افزایش یافت.\n\n"
                f"💰 موجودی جدید: {new_balance:,.0f} تومان",
                parse_mode="Markdown"
            )
            
            # اطلاع به کاربر
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"💰 موجودی کیف پول شما توسط مدیریت به میزان {amount:,.0f} تومان افزایش یافت.\n\n"
                         f"💳 موجودی جدید: {new_balance:,.0f} تومان",
                    reply_markup=MAIN_MENU_REPLY_MARKUP
                )
            except Exception as e:
                logger.error(f"Failed to notify user {target_user_id}: {e}")
            
            # پاک کردن وضعیت
            context.user_data.pop('awaiting_amount_for', None)
        
        elif 'awaiting_message_for' in context.user_data:
            target_user_id = context.user_data['awaiting_message_for']
            message_text = text
            
            if not message_text or len(message_text.strip()) == 0:
                await update.message.reply_text("❌ پیام نمی‌تواند خالی باشد.")
                return
            
            try:
                # ارسال پیام به کاربر
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📨 **پیام از مدیریت:**\n\n{message_text}\n\n"
                         f"_در صورت نیاز به پاسخ، از دکمه 📞 پشتیبانی استفاده کنید._",
                    parse_mode="Markdown"
                )
                
                await update.message.reply_text(
                    f"✅ پیام شما به کاربر {format_user_info(target_user_id)} ارسال شد.",
                    parse_mode="Markdown"
                )
                
                # ذخیره در تاریخچه
                if 'admin_messages' not in context.bot_data:
                    context.bot_data['admin_messages'] = {}
                
                timestamp = datetime.datetime.now().isoformat()
                if str(target_user_id) not in context.bot_data['admin_messages']:
                    context.bot_data['admin_messages'][str(target_user_id)] = []
                
                context.bot_data['admin_messages'][str(target_user_id)].append({
                    'from_admin': update.effective_user.id,
                    'message': message_text,
                    'timestamp': timestamp
                })
                
            except error.Forbidden:
                await update.message.reply_text(
                    f"❌ ارسال پیام به کاربر {format_user_info(target_user_id)} ناموفق بود.\n"
                    f"کاربر ربات را مسدود کرده است.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send message to user {target_user_id}: {e}")
                await update.message.reply_text(f"❌ خطا در ارسال پیام: {e}")
            
            # پاک کردن وضعیت
            context.user_data.pop('awaiting_message_for', None)

async def investigate_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """نمایش اطلاعات جامع کاربر"""
    query = update.callback_query
    await query.answer("در حال دریافت اطلاعات جامع...")
    
    users = load_users()
    str_target_user_id = str(target_user_id)
    
    if str_target_user_id not in users:
        await query.answer("❌ کاربر در سیستم وجود ندارد.", show_alert=True)
        return
    
    user_data = users[str_target_user_id]
    
    # اطلاعات پایه
    message_text = f"🔍 **بررسی جامع کاربر**\n\n👤 کاربر: {format_user_info(target_user_id)}\n\n"
    
    # اطلاعات حساب
    balance = user_data.get("balance", 0.0)
    created_at = user_data.get("created_at", "نامشخص")
    notes = user_data.get("notes", "ندارد")
    
    try:
        created_date = datetime.datetime.fromisoformat(created_at).strftime("%Y/%m/%d %H:%M")
    except:
        created_date = created_at
    
    message_text += f"📊 **اطلاعات حساب:**\n"
    message_text += f"💰 موجودی: {balance:,.0f} تومان\n"
    message_text += f"📅 تاریخ ایجاد: {created_date}\n"
    message_text += f"📝 یادداشت: {notes}\n\n"
    
    # اطلاعات رفرال
    referral_by = user_data.get("referral_by")
    referral_earnings = user_data.get("referral_earnings", 0.0)
    referrals_count = user_data.get("referrals_count", 0)
    
    message_text += f"🔗 **اطلاعات رفرال:**\n"
    if referral_by:
        message_text += f"• رفرال دهنده: {format_user_info(referral_by, show_copyable=False)}\n"
    else:
        message_text += f"• رفرال دهنده: ندارد\n"
    message_text += f"• کاربران جذب شده: {referrals_count} نفر\n"
    message_text += f"• درآمد رفرال: {referral_earnings:,.0f} تومان\n\n"
    
    # اطلاعات سرویس‌ها
    services = user_data.get("services", [])
    message_text += f"📂 **اطلاعات سرویس‌ها:**\n"
    message_text += f"• تعداد سرویس‌ها: {len(services)} عدد\n"
    
    if services:
        # گروه‌بندی سرویس‌ها بر اساس نوع
        service_types = {}
        for service in services:
            internal_key = service.get('internal_key', 'نامشخص')
            service_type = SERVICES.get(internal_key, {}).get('label', internal_key)
            if service_type not in service_types:
                service_types[service_type] = 0
            service_types[service_type] += 1
        
        message_text += f"• انواع سرویس‌ها:\n"
        for service_type, count in service_types.items():
            message_text += f"  - {service_type}: {count} عدد\n"
    
    # اطلاعات تراکنش‌ها
    transactions = get_user_transactions(target_user_id, limit=0)
    if transactions:
        total_deposit = sum(t['amount'] for t in transactions if t['type'] in ['deposit', 'admin_adjustment', 'referral_earning'])
        total_withdrawal = sum(t['amount'] for t in transactions if t['type'] in ['purchase', 'renewal'])
        
        message_text += f"\n💳 **اطلاعات مالی:**\n"
        message_text += f"• تعداد تراکنش‌ها: {len(transactions)} عدد\n"
        message_text += f"• مجموع واریزی: {total_deposit:,.0f} تومان\n"
        message_text += f"• مجموع برداشت: {total_withdrawal:,.0f} تومان\n"
        message_text += f"• موجودی خالص: {balance:,.0f} تومان\n"
    
    # اطلاعات تست رایگان
    if has_user_used_free_trial(target_user_id):
        free_trial_users = load_free_trial_users()
        trial_data = free_trial_users.get(str_target_user_id, {})
        used_date = trial_data.get('used_date', 'نامشخص')
        
        try:
            used_date_formatted = datetime.datetime.fromisoformat(used_date).strftime("%Y/%m/%d")
        except:
            used_date_formatted = used_date
        
        message_text += f"\n⚠️ **تست رایگان:**\n"
        message_text += f"• وضعیت: استفاده کرده\n"
        message_text += f"• تاریخ استفاده: {used_date_formatted}\n"
    
    # دکمه‌های عملیاتی
    keyboard = [
        [InlineKeyboardButton("📊 تاریخچه تراکنش‌ها", callback_data=f"transaction_details_{target_user_id}_1")],
        [InlineKeyboardButton("📂 جزئیات سرویس‌ها", callback_data=f"service_details_{target_user_id}_1")],
        [InlineKeyboardButton("📋 لیست کامل رفرال‌ها", callback_data=f"full_referral_list_{target_user_id}_1")],
        [InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data=f"edit_user_{target_user_id}")],
        [InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"refresh_profile_{target_user_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def register_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """ثبت کاربر جدید توسط ادمین"""
    query = update.callback_query
    await query.answer("در حال ثبت کاربر...")
    
    users = load_users()
    str_target_user_id = str(target_user_id)
    
    if str_target_user_id in users:
        await query.answer("❌ کاربر قبلاً در سیستم ثبت شده است.", show_alert=True)
        return
    
    # ثبت کاربر جدید
    users[str_target_user_id] = {
        "balance": 0.0,
        "services": [],
        "referral_by": None,
        "referral_earnings": 0.0,
        "referrals_count": 0,
        "notes": "ثبت شده توسط ادمین",
        "created_at": datetime.datetime.now().isoformat()
    }
    
    save_users(users)
    
    message_text = f"✅ کاربر جدید ثبت شد!\n\n👤 کاربر: {format_user_info(target_user_id)}\n\nاطلاعات:\n"
    message_text += f"💰 موجودی: 0 تومان\n"
    message_text += f"📅 تاریخ ثبت: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
    message_text += f"📝 وضعیت: فعال\n\n"
    message_text += f"کاربر می‌تواند از طریق ربات اقدام به خرید سرویس کند."
    
    keyboard = [
        [InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"add_balance_{target_user_id}")],
        [InlineKeyboardButton("🔍 مشاهده پروفایل", callback_data=f"refresh_profile_{target_user_id}")],
        [InlineKeyboardButton("🔙 بستن", callback_data="close_profile")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def show_full_referral_list(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page: int = 1):
    """نمایش لیست کامل کاربران جذب شده با صفحه‌بندی"""
    query = update.callback_query
    await query.answer("در حال دریافت لیست رفرال‌ها...")
    
    referral_history = get_referral_history(target_user_id)
    
    if not referral_history:
        message_text = f"📋 **لیست کاربران جذب شده**\n\n👤 رفرال دهنده: {format_user_info(target_user_id)}\n\n❌ هیچ کاربری جذب نکرده است."
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"investigate_user_{target_user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return
    
    # صفحه‌بندی
    items_per_page = 20
    total_pages = (len(referral_history) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(referral_history))
    
    # محاسبه آمار
    total_referrals = len(referral_history)
    active_referrals = sum(1 for ref in referral_history if ref.get('status') == 'active')
    
    # ساخت پیام
    message_text = f"📋 **لیست کامل کاربران جذب شده**\n\n👤 رفرال دهنده: {format_user_info(target_user_id)}\n\n"
    message_text += f"📊 **آمار کلی:**\n"
    message_text += f"• تعداد کل: {total_referrals} نفر\n"
    message_text += f"• کاربران فعال: {active_referrals} نفر\n\n"
    
    message_text += f"👥 **لیست کاربران (صفحه {page} از {total_pages}):**\n"
    
    # نمایش کاربران صفحه جاری
    for i, referral in enumerate(referral_history[start_idx:end_idx], start_idx + 1):
        ref_user_id = referral.get('user_id')
        ref_date = datetime.datetime.fromisoformat(referral.get('date')).strftime("%Y/%m/%d")
        status = referral.get('status', 'active')
        
        # دریافت اطلاعات کاربر
        users_data = load_users()
        str_ref_user_id = str(ref_user_id)
        
        user_info = ""
        if str_ref_user_id in users_data:
            user_data = users_data[str_ref_user_id]
            balance = user_data.get('balance', 0)
            services_count = len(user_data.get('services', []))
            user_info = f"💰{balance:,.0f}ت | 📂{services_count}س"
        
        status_emoji = "🟢" if status == 'active' else "⚫"
        message_text += f"{i}. {status_emoji} {format_user_info(ref_user_id, show_copyable=False)} - {ref_date} {user_info}\n"
    
    # دکمه‌های صفحه‌بندی
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"full_referral_list_{target_user_id}_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=f"referral_page_info"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"full_referral_list_{target_user_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # دکمه‌های اضافی
    keyboard.append([
        InlineKeyboardButton("📊 تاریخچه درآمد رفرال", callback_data=f"referral_earnings_history_{target_user_id}"),
        InlineKeyboardButton("📥 خروجی Excel", callback_data=f"export_referrals_{target_user_id}")
    ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به بررسی", callback_data=f"investigate_user_{target_user_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit referral list message: {e}")
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def referral_earnings_history_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page: int = 1):
    """نمایش تاریخچه درآمدهای رفرال برای ادمین"""
    query = update.callback_query
    await query.answer("در حال دریافت تاریخچه درآمدها...")
    
    earnings_history = get_referral_earnings_history(target_user_id)
    
    if not earnings_history:
        message_text = f"💰 **تاریخچه درآمد رفرال**\n\n👤 رفرال دهنده: {format_user_info(target_user_id)}\n\n❌ هیچ درآمد رفرالی نداشته است."
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"full_referral_list_{target_user_id}_1")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        return
    
    # صفحه‌بندی
    items_per_page = 15
    total_pages = (len(earnings_history) + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(earnings_history))
    
    # محاسبه مجموع
    total_earnings = sum(item['amount'] for item in earnings_history)
    
    # ساخت پیام
    message_text = f"💰 **تاریخچه درآمد رفرال**\n\n👤 رفرال دهنده: {format_user_info(target_user_id)}\n\n"
    message_text += f"📊 **آمار کلی:**\n"
    message_text += f"• تعداد تراکنش: {len(earnings_history)} عدد\n"
    message_text += f"• مجموع درآمد: {total_earnings:,.0f} تومان\n"
    message_text += f"• درصد رفرال: {user_referral_percent(target_user_id):g}%\n\n"
    
    message_text += f"📈 **تراکنش‌ها (صفحه {page} از {total_pages}):**\n"
    
    # نمایش تراکنش‌های صفحه جاری
    for i, earning in enumerate(earnings_history[start_idx:end_idx], start_idx + 1):
        date = datetime.datetime.fromisoformat(earning['date']).strftime("%Y/%m/%d")
        from_user_link = format_user_info(earning['from_user'], show_copyable=False)
        original_amount = earning.get('original_amount', 0)
        
        message_text += f"{i}. از {from_user_link}\n"
        message_text += f"   ├─ مبلغ اصلی: {original_amount:,.0f} تومان\n"
        message_text += f"   ├─ پورسانت: {earning['amount']:,.0f} تومان\n"
        message_text += f"   └─ تاریخ: {date}\n"
    
    # دکمه‌های صفحه‌بندی
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"referral_earnings_history_{target_user_id}_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data=f"earnings_page_info"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"referral_earnings_history_{target_user_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست رفرال‌ها", callback_data=f"full_referral_list_{target_user_id}_1")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# ============================================================
# --- توابع جدید برای /allmembers و /addall ---
# ============================================================

async def allmembers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای مشاهده لیست تمام کاربران با صفحه‌بندی"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    # دریافت صفحه از آرگومان‌ها (در صورت وجود)
    page = 1
    if context.args:
        try:
            page = int(context.args[0])
            if page < 1:
                page = 1
        except ValueError:
            page = 1
    
    await show_all_users_list(update, context, page)

async def show_all_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    """نمایش لیست تمام کاربران با صفحه‌بندی"""
    users = load_users()
    
    if not users:
        await update.message.reply_text("📋 **لیست کاربران**\n\n❌ هیچ کاربری در سیستم ثبت نشده است.")
        return
    
    # صفحه‌بندی
    items_per_page = 20
    user_ids = list(users.keys())
    total_users = len(user_ids)
    total_pages = (total_users + items_per_page - 1) // items_per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_users)
    
    # ساخت پیام
    message_text = f"📋 **لیست تمام کاربران**\n\n"
    message_text += f"📊 **آمار کلی:**\n"
    message_text += f"• تعداد کل کاربران: {total_users} نفر\n"
    message_text += f"• صفحه {page} از {total_pages}\n\n"
    
    message_text += f"👥 **کاربران (صفحه {page}):**\n"
    
    # نمایش کاربران صفحه جاری
    for i, str_user_id in enumerate(user_ids[start_idx:end_idx], start_idx + 1):
        user_id = int(str_user_id)
        user_data = users[str_user_id]
        
        balance = user_data.get('balance', 0)
        services_count = len(user_data.get('services', []))
        created_at = user_data.get('created_at', 'نامشخص')
        
        try:
            created_date = datetime.datetime.fromisoformat(created_at).strftime("%Y/%m/%d")
        except:
            created_date = created_at
        
        user_info = f"{format_user_info(user_id, show_copyable=False)}"
        user_info += f" | 💰{balance:,.0f}ت | 📂{services_count}س | 📅{created_date}"
        
        message_text += f"{i}. {user_info}\n"
    
    # دکمه‌های صفحه‌بندی
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ صفحه قبلی", callback_data=f"allmembers_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="allmembers_page_info"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("صفحه بعدی ▶️", callback_data=f"allmembers_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # دکمه‌های عملیاتی
    keyboard.append([
        InlineKeyboardButton("📥 خروجی Excel", callback_data="export_all_users"),
        InlineKeyboardButton("💰 افزایش موجودی گروهی", callback_data="addall_start")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"allmembers_page_{page}"),
        InlineKeyboardButton("🔙 بستن", callback_data="close_allmembers")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

async def addall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای افزایش یا کاهش موجودی گروهی کاربران"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ فرمت دستور:\n`/addall [Amount]`\n\n"
            "مثال:\n"
            "`/addall 50000` - افزایش 50,000 تومان به تمام کاربران\n"
            "`/addall -10000` - کاهش 10,000 تومان از تمام کاربران",
            parse_mode="Markdown"
        )
        return
    
    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ مبلغ وارد شده نامعتبر است. لطفاً یک عدد وارد کنید.")
        return
    
    # ذخیره اطلاعات در context برای استفاده در تایید
    context.user_data['addall_amount'] = amount
    
    # نمایش تأیید
    users = load_users()
    total_users = len(users)
    total_amount = amount * total_users
    
    message_text = f"⚠️ **تأیید افزایش موجودی گروهی**\n\n"
    message_text += f"👤 **ادمین:** {format_user_info(update.effective_user.id)}\n"
    message_text += f"💰 **مبلغ به ازای هر کاربر:** {amount:+,.0f} تومان\n"
    message_text += f"👥 **تعداد کاربران:** {total_users} نفر\n"
    message_text += f"💰 **مجموع مبلغ:** {total_amount:+,.0f} تومان\n\n"
    
    if amount < 0:
        message_text += f"⚠️ **هشدار:** شما در حال کاهش موجودی کاربران هستید!\n\n"
    
    message_text += f"آیا از انجام این عمل مطمئن هستید؟"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ بله، تأیید می‌کنم", callback_data="addall_confirm"),
            InlineKeyboardButton("❌ خیر، لغو", callback_data="addall_cancel")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)

async def addall_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تأیید و اجرای افزایش موجودی گروهی"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.answer("❌ شما دسترسی لازم ندارید.", show_alert=True)
        return
    
    amount = context.user_data.get('addall_amount')
    if amount is None:
        await query.answer("❌ اطلاعات مبلغ یافت نشد.", show_alert=True)
        return
    
    users = load_users()
    total_users = len(users)
    
    if total_users == 0:
        await query.answer("❌ هیچ کاربری برای ویرایش وجود ندارد.", show_alert=True)
        return
    
    # آپدیت پیام
    await query.edit_message_text(
        f"🔄 در حال افزایش موجودی {total_users} کاربر...\n\n"
        f"لطفاً منتظر بمانید...",
        parse_mode="Markdown"
    )
    
    # اجرای افزایش موجودی گروهی
    affected_users = 0
    failed_users = 0
    total_amount_added = 0
    
    for str_user_id, user_data in users.items():
        try:
            user_id = int(str_user_id)
            old_balance = user_data.get('balance', 0)
            new_balance = old_balance + amount
            
            # به‌روزرسانی موجودی
            users[str_user_id]["balance"] = new_balance
            
            # افزودن تراکنش به تاریخچه
            action_type = "افزایش" if amount >= 0 else "کاهش"
            add_transaction(user_id, "admin_adjustment", amount, 
                          f"{action_type} موجودی گروهی توسط ادمین", query.from_user.id)
            
            affected_users += 1
            total_amount_added += amount
            
            # اطلاع به کاربر (در صورت مثبت بودن مبلغ)
            if amount > 0:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"💰 موجودی کیف پول شما توسط مدیریت به میزان {amount:,.0f} تومان افزایش یافت.\n\n"
                             f"💳 موجودی جدید: {new_balance:,.0f} تومان",
                        reply_markup=MAIN_MENU_REPLY_MARKUP
                    )
                except error.Forbidden:
                    failed_users += 1  # کاربر ربات را بلاک کرده
                except Exception:
                    failed_users += 1
            elif amount < 0:
                # برای کاهش موجودی، فقط به کاربران خاص اطلاع نمی‌دهیم
                pass
                
        except Exception as e:
            logger.error(f"Failed to update balance for user {str_user_id}: {e}")
            failed_users += 1
    
    # ذخیره تغییرات
    save_users(users)
    
    # ارسال لاگ به ادمین‌ها
    await send_admin_action_log(context, query.from_user.id, 'addall', {
        'amount': amount,
        'affected_users': affected_users,
        'failed_users': failed_users,
        'total_amount': total_amount_added
    })
    
    # نتیجه‌گیری
    message_text = f"✅ **افزایش موجودی گروهی انجام شد**\n\n"
    message_text += f"👤 **ادمین:** {format_user_info(query.from_user.id)}\n"
    message_text += f"💰 **مبلغ به ازای هر کاربر:** {amount:+,.0f} تومان\n"
    message_text += f"✅ **کاربران موفق:** {affected_users} نفر\n"
    message_text += f"❌ **کاربران ناموفق:** {failed_users} نفر\n"
    message_text += f"💰 **مجموع مبلغ تغییر یافته:** {total_amount_added:+,.0f} تومان\n"
    message_text += f"📅 **زمان:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
    
    keyboard = [
        [InlineKeyboardButton("📋 مشاهده لیست کاربران", callback_data="allmembers_page_1")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_admin")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
    # پاک کردن داده‌های موقت
    context.user_data.pop('addall_amount', None)

async def addall_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """لغو افزایش موجودی گروهی"""
    query = update.callback_query
    await query.answer("عملیات لغو شد.")
    
    await query.edit_message_text(
        "❌ افزایش موجودی گروهی لغو شد.",
        parse_mode="Markdown"
    )
    
    # پاک کردن داده‌های موقت
    context.user_data.pop('addall_amount', None)

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
                               volume_add: int, days_add: int,
                               max_days: int = None, set_unlimited: bool = False) -> tuple[bool, float, int]:
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
    if set_unlimited:
        # سرویس بی‌نهایت: حجم کل صفر یعنی نامحدود در 3x-ui
        new_total_bytes = 0
        new_total_gb = 0.0
    elif current_total_bytes <= 0:
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
        # سقف اعتبار: بعد از هر تمدید، زمان اشتراک از حالا بیشتر از max_days روز نمی‌شود
        cap_days = max_days or MAX_SUBSCRIPTION_DAYS
        cap_seconds = now_seconds + cap_days * 24 * 3600
        if current_expiry_seconds >= cap_seconds:
            new_expiry_seconds = current_expiry_seconds
        else:
            new_expiry_seconds = min(start_time + days_add * 24 * 3600, cap_seconds)
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


async def xui_delete_client(server_key: str, config_name: str) -> bool:
    """حذف کلاینت از پنل 3x-ui (API جدید و در صورت نیاز API قدیمی)"""
    response = await xui_api_request(server_key, 'POST', f"/panel/api/clients/del/{config_name}")
    if response is not None and response.status_code >= 400:
        response = await xui_api_request(server_key, 'GET', f"/panel/api/clients/del/{config_name}")

    if response is None or response.status_code == 404:
        inbound = await xui_get_inbound(server_key)
        if inbound is None:
            return False
        try:
            inbound_id = int(inbound.get('id') or 0)
        except (TypeError, ValueError):
            inbound_id = 0
        response = await xui_api_request(
            server_key, 'POST', f"/panel/api/inbounds/{inbound_id}/delClient/{config_name}"
        )

    if response is None:
        return False

    payload = _xui_payload(response)
    if response.status_code == 200 and payload.get('success', True):
        logger.info(f"3x-ui client deleted on {server_key}: {config_name}")
        return True

    logger.error(f"3x-ui failed to delete client {config_name} on {server_key}: "
                 f"{payload.get('msg') or response.status_code}")
    return False


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
    """هندلر دستور /start با پشتیبانی از رفرال و اطلاع به ادمین"""
    user = update.effective_user
    user_id = user.id
    users = load_users()
    str_user_id = str(user_id)
    
    # بررسی آیا کاربر جدید است یا قدیمی
    is_new_user = str_user_id not in users
    
    # بررسی پارامترهای لینک برای رفرال
    args = context.args
    referral_id = None
    
    if args and len(args) > 0:
        # بررسی فرمت‌های مختلف رفرال
        referral_arg = args[0]
        
        # فرمت: /start ref_12345
        if referral_arg.startswith('ref_') and len(referral_arg) > 4:
            try:
                referral_id = int(referral_arg[4:])
            except ValueError:
                referral_id = None
        
        # فرمت: /start 12345 (مستقیم عدد)
        elif referral_arg.isdigit():
            try:
                referral_id = int(referral_arg)
            except ValueError:
                referral_id = None
    
    # تنظیم رفرال برای کاربر اگر وجود داشته باشد و کاربر جدید باشد
    if referral_id and is_new_user:
        success = set_user_referral(user_id, referral_id)
        if success:
            logger.info(f"User {user_id} registered with referral from {referral_id}")
    
    # اگر کاربر جدید است، اطلاع به ادمین‌ها
    if is_new_user:
        # ذخیره کاربر در دیتابیس (اگر قبلاً وجود نداشته)
        if str_user_id not in users:
            users[str_user_id] = {"balance": 0.0, "services": [], "referral_by": referral_id, "referral_earnings": 0.0, "referrals_count": 0, "join_date": datetime.datetime.now().isoformat(), "notes": "", "created_at": datetime.datetime.now().isoformat()}
            save_users(users)
        
        # ارسال اطلاع به ادمین‌ها
        join_date = datetime.datetime.now().strftime("%Y/%m/%d - %H:%M:%S")
        referral_info = ""
        if referral_id:
            referral_info = f"✅ توسط {format_user_info(referral_id, show_copyable=False)}"
        else:
            referral_info = "❌ ندارد"
        
        admin_message = (
            f"👤 کاربر جدید وارد ربات شد!\n\n"
            f"🆔 شناسه کاربر: {format_user_info(user_id)}\n"
            f"👤 نام: {user.first_name} {user.last_name or ''}\n"
            f"📅 تاریخ عضویت: {join_date}\n"
            f"🔗 رفرال: {referral_info}"
        )
        
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(admin_id, admin_message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send new user notification to admin {admin_id}: {e}")
    
    # پیام خوش‌آمدگویی
    welcome_message = f"سلام {user.first_name}،\nلطفاً یک گزینه را از منوی زیر انتخاب کنید:"
    
    # اگر کاربر توسط رفرال آمده، پیام اضافی
    if referral_id:
        welcome_message += f"\n\n✅ شما توسط {format_user_info(referral_id, show_copyable=False)} به ربات دعوت شده‌اید!"
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=MAIN_MENU_REPLY_MARKUP,
        parse_mode="Markdown"
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
    """نمایش موجودی کیف پول و مشخصات کاربر با اطلاعات رفرال"""
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)
    num_services = len(get_user_services(user_id))
    bonus_info = get_referral_bonus_info(user_id)
    
    # دریافت اطلاعات رفرال
    referral_info = get_user_referral_info(user_id)
    referral_by = referral_info.get("referral_by")
    referral_earnings = referral_info.get("referral_earnings", 0.0)
    referrals_count = referral_info.get("referrals_count", 0)
    
    message_text = (
        f"**👤 جزئیات حساب کاربری**\n\n"
        f"🔹 **شناسه کاربری (ID):** {format_user_info(user_id)}\n"
        f"🔹 **موجودی کیف پول:** **{balance:,.0f}** تومان\n"
        f"🔹 **تعداد سرویس فعال:** **{num_services}** عدد\n"
    )
    
    # اضافه کردن اطلاعات رفرال
    if referral_by:
        message_text += f"🔹 **رفرال دهنده:** {format_user_info(referral_by, show_copyable=False)}\n"
    
    message_text += (
        f"🔹 **تعداد کاربران رفرال:** **{referrals_count}** نفر\n"
        f"🔹 **درآمد رفرال:** **{referral_earnings:,.0f}** تومان\n"
        f"🔹 **هدیهٔ آمادهٔ دریافت:** **{bonus_info['available']}** عدد ({bonus_info['available'] * REFERRAL_BONUS_GB} گیگ)\n\n"
        f"**نکته:** برای شارژ، از دکمه «💰 شارژ کیف پول» در منوی اصلی استفاده کنید.\n"
        f"برای دریافت لینک رفرال خود، روی دکمه «🔗 لینک رفرال» کلیک کنید."
    )
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
    )

def build_referral_page(user_id: int, bot_username: str) -> tuple[str, InlineKeyboardMarkup]:
    """متن و دکمه‌های صفحهٔ لینک رفرال (مشترک بین پیام معمولی و callback)"""
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    # دریافت اطلاعات رفرال
    referral_info = get_user_referral_info(user_id)
    referral_by = referral_info.get("referral_by")
    referral_earnings = referral_info.get("referral_earnings", 0.0)
    referrals_count = referral_info.get("referrals_count", 0)

    message_text = (
        f"**🔗 لینک رفرال شما**\n\n"
        f"لینک اختصاصی شما:\n`{ref_link}`\n\n"
        f"📊 **آمار رفرال شما:**\n"
        f"🔸 تعداد کاربران جذب شده: **{referrals_count}** نفر\n"
        f"🔸 مجموع درآمد رفرال: **{referral_earnings:,.0f}** تومان\n"
        f"🔸 درصد رفرال: **{user_referral_percent(user_id):g}%**\n"
    )

    # نمایش رفرال دهنده (اگر دارد)
    if referral_by:
        message_text += f"🔸 رفرال دهنده شما: {format_user_info(referral_by, show_copyable=False)}\n"

    message_text += "\n**📝 نحوه کار:**\n"
    message_text += "1. لینک بالا را برای دوستان خود ارسال کنید\n"
    message_text += "2. دوستان شما با کلیک روی لینک وارد ربات می‌شوند\n"
    message_text += "3. رفرال شما برای همیشه در پروفایلشان ثبت می‌شود\n"
    message_text += f"4. از هر شارژی که انجام دهند، **{REFERRAL_PERCENT}%** به حساب شما اضافه می‌شود\n\n"

    # هدیهٔ حجمی: هر ۲۰ نفر رفرال = ۲۰ گیگ یکجا روی یکی از سرویس‌های خریداری‌شده
    bonus_info = get_referral_bonus_info(user_id)
    message_text += (f"**🎁 هدیهٔ حجمی:** هر {REFERRAL_BONUS_REFERRALS} نفر رفرال = "
                     f"{REFERRAL_BONUS_GB} گیگ حجم، یک‌جا روی یکی از سرویس‌های خریداری‌شده.\n")
    if bonus_info['available'] > 0:
        message_text += (f"🎁 هدیهٔ آماده: **{bonus_info['available']}** عدد "
                         f"({bonus_info['available'] * REFERRAL_BONUS_GB} گیگ) — از دکمهٔ زیر دریافت کنید.\n")
    else:
        message_text += f"تا هدیهٔ بعدی: **{bonus_info['to_next']}** نفر.\n"

    message_text += "\n**⚠️ توجه:**\n"
    message_text += f"• رفرال هر کاربر فقط یک بار و در اولین ورود ثبت می‌شود\n"
    message_text += f"• مبلغ شارژ باید حداقل **{REFERRAL_MIN_AMOUNT:,}** تومان باشد تا رفرال محاسبه شود\n"
    message_text += f"• رفرال پس از تأیید رسید شارژ توسط ادمین به حساب شما واریز می‌شود"

    message_text += "\n\n**‼️ نکته:**\n"
    message_text += f"• در صورتی که مبلغ درآمد شما از رفرال بیش از 500,000 تومان شود\n"
    message_text += f"• میتوانید با ثبت درخواست در پشتیبانی مبلغ درآمد خود را به کارت بانکی خود واریز کنید\n"

    # دکمه‌ها: دریافت هدیه (در صورت وجود)، اشتراک‌گذاری و تاریخچه
    keyboard = []
    if bonus_info['available'] > 0:
        keyboard.append([InlineKeyboardButton(
            f"🎁 دریافت هدیهٔ حجمی ({REFERRAL_BONUS_GB} گیگ)",
            callback_data="REFERRAL_BONUS_CLAIM")])
    keyboard.append([InlineKeyboardButton(
        "📲 اشتراک‌گذاری لینک", url=f"tg://msg_url?url={ref_link}&text=لینک%20رفرال%20من")])
    keyboard.append([InlineKeyboardButton(
        "📊 تاریخچه درآمد رفرال", callback_data=f"REFERRAL_HISTORY_{user_id}")])

    return message_text, InlineKeyboardMarkup(keyboard)


async def my_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لینک رفرال کاربر"""
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    message_text, reply_markup = build_referral_page(user_id, bot_username)

    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def referral_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش تاریخچه درآمدهای رفرال کاربر"""
    query = update.callback_query
    await query.answer("در حال دریافت تاریخچه...")
    
    user_id = query.from_user.id
    
    # دریافت تاریخچه درآمدها
    earnings_history = get_referral_earnings_history(user_id)
    
    if not earnings_history:
        message_text = "📊 **تاریخچه درآمد رفرال**\n\nشما هنوز درآمد رفرالی نداشته‌اید."
        try:
            await query.edit_message_text(message_text, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(user_id, message_text, parse_mode="Markdown")
        return
    
    # محاسبه مجموع
    total_earnings = sum(item['amount'] for item in earnings_history)
    
    message_text = f"📊 **تاریخچه درآمد رفرال**\n\n"
    message_text += f"**مجموع درآمد:** **{total_earnings:,.0f}** تومان\n\n"
    message_text += "**آخرین تراکنش‌ها:**\n"
    
    # نمایش 10 تراکنش آخر
    for i, earning in enumerate(earnings_history[-10:], 1):
        date = datetime.datetime.fromisoformat(earning['date']).strftime("%Y/%m/%d")
        from_user_link = format_user_info(earning['from_user'], show_copyable=False)
        message_text += f"{i}. از کاربر {from_user_link} - {earning['amount']:,.0f} تومان ({date})\n"
    
    if len(earnings_history) > 10:
        message_text += f"\nو {len(earnings_history) - 10} تراکنش دیگر..."
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_referral_link")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(user_id, message_text, parse_mode="Markdown", reply_markup=reply_markup)

# ============================================================
# --- هدیهٔ حجمی رفرال ---
# ============================================================

async def referral_bonus_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش سرویس‌های کاربر برای اعمال هدیهٔ حجمی رفرال"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bonus = get_referral_bonus_info(user_id)
    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_referral_link")]])

    if bonus["available"] <= 0:
        text = (
            "🎁 **هدیهٔ حجمی رفرال**\n\n"
            "در حال حاضر هدیهٔ آمادهٔ دریافت ندارید.\n"
            f"به ازای هر **{REFERRAL_BONUS_REFERRALS}** نفر که با لینک شما وارد شوند، **{REFERRAL_BONUS_GB} گیگ** حجم هدیه می‌گیرید.\n\n"
            f"رفرال‌های شما: **{bonus['referrals_count']}** نفر\n"
            f"تا هدیهٔ بعدی: **{bonus['to_next']}** نفر"
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=back_markup)
        return

    services = get_user_services(user_id)
    if not services:
        text = (
            "🎁 **هدیهٔ حجمی رفرال**\n\n"
            "شما هنوز سرویسی خریداری نکرده‌اید.\n"
            f"هدیهٔ شما (**{bonus['available']} × {REFERRAL_BONUS_GB} گیگ**) محفوظ می‌ماند و بعد از خرید اولین سرویس قابل دریافت است."
        )
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=back_markup)
        return

    keyboard = []
    for svc in services:
        name = svc.get("config_name") or ""
        server_name = SERVERS_CONFIG.get(svc.get("server_key", ""), {}).get("display_name", "نامشخص")
        keyboard.append([InlineKeyboardButton(
            f"🧩 {name} — {server_name}", callback_data=f"REFERRAL_BONUS_SVC_{name}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_referral_link")])

    text = (
        "🎁 **هدیهٔ حجمی رفرال**\n\n"
        f"شما **{bonus['available']}** هدیهٔ **{REFERRAL_BONUS_GB} گیگی** آمادهٔ دریافت دارید.\n"
        f"سرویسی را انتخاب کنید که **{REFERRAL_BONUS_GB} گیگ** به حجم آن اضافه شود:"
    )
    markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)


async def referral_bonus_choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش صفحهٔ تأیید هدیه روی سرویس انتخاب‌شده"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    config_name = query.data.split("REFERRAL_BONUS_SVC_", 1)[1]
    bonus = get_referral_bonus_info(user_id)
    service = next((s for s in get_user_services(user_id) if s.get("config_name") == config_name), None)
    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انتخاب سرویس دیگر", callback_data="REFERRAL_BONUS_CLAIM")]])

    if not service:
        text = "❌ این سرویس در حساب شما پیدا نشد."
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    if bonus["available"] <= 0:
        text = "❌ هدیهٔ آمادهٔ دریافت ندارید. هر ۲۰ نفر رفرال = ۲۰ گیگ حجم هدیه."
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    server_key = service.get("server_key")
    server_name = SERVERS_CONFIG.get(server_key, {}).get("display_name", "نامشخص")
    _, client_data = await xui_get_client_info_by_name(server_key, config_name)

    if not client_data:
        text = f"❌ اطلاعات سرویس {config_name} در پنل پیدا نشد. لطفاً بعداً دوباره تلاش کنید."
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    total_bytes = int(client_data.get("totalGB") or 0)
    if total_bytes <= 0:
        text = (
            f"♾️ سرویس {config_name} نامحدود است و حجم اضافه نمی‌گیرد.\n"
            "یکی از سرویس‌های حجمی خود را برای دریافت هدیه انتخاب کنید."
        )
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    text = (
        "🎁 **تأیید هدیهٔ حجمی رفرال**\n\n"
        f"📛 سرویس: **{config_name}**\n"
        f"🌐 سرور: {server_name}\n"
        f"💾 حجم فعلی: {convert_bytes_to_display(total_bytes)}\n"
        f"🎁 حجم هدیه: **+{REFERRAL_BONUS_GB} GB**\n\n"
        f"با تأیید، این حجم به سرویس اضافه می‌شود و یکی از **{bonus['available']}** هدیهٔ آمادهٔ شما مصرف می‌شود."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ تأیید و شارژ {REFERRAL_BONUS_GB} گیگ",
                              callback_data=f"REFERRAL_BONUS_APPLY_{config_name}")],
        [InlineKeyboardButton("🔙 انتخاب سرویس دیگر", callback_data="REFERRAL_BONUS_CLAIM")],
    ])
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)


async def referral_bonus_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شارژ ۲۰ گیگ هدیهٔ رفرال روی سرویس انتخاب‌شده"""
    query = update.callback_query
    await query.answer("در حال اعمال هدیه...")
    user_id = query.from_user.id
    config_name = query.data.split("REFERRAL_BONUS_APPLY_", 1)[1]
    bonus = get_referral_bonus_info(user_id)
    service = next((s for s in get_user_services(user_id) if s.get("config_name") == config_name), None)
    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لینک رفرال", callback_data="back_to_referral_link")]])

    if not service or bonus["available"] <= 0:
        text = "❌ این هدیه قابل دریافت نیست. لطفاً از صفحهٔ لینک رفرال دوباره تلاش کنید."
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    server_key = service.get("server_key")
    server_name = SERVERS_CONFIG.get(server_key, {}).get("display_name", "نامشخص")

    success, new_total_gb, _ = await xui_update_client_v2(
        server_key, user_id, config_name, REFERRAL_BONUS_GB, 0
    )

    if not success:
        text = "❌ شارژ هدیه انجام نشد و هیچ هدیه‌ای از حساب شما کم نشد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        try:
            await query.edit_message_text(text, reply_markup=back_markup)
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=back_markup)
        return

    record_referral_bonus_claim(user_id, config_name)
    bonus_after = get_referral_bonus_info(user_id)
    add_transaction(user_id, "referral_bonus", 0,
                    f"هدیهٔ {REFERRAL_BONUS_GB} گیگ رفرال روی سرویس {config_name}")

    text = (
        f"✅ **{REFERRAL_BONUS_GB} گیگ هدیهٔ رفرال روی سرویس {config_name} شارژ شد!**\n\n"
        f"🌐 سرور: {server_name}\n"
        f"💾 حجم جدید: **{new_total_gb:.2f} GB**\n"
        f"🎁 هدیه‌های باقی‌مانده: **{bonus_after['available']}** عدد\n\n"
        f"تا هدیهٔ بعدی: **{bonus_after['to_next']}** نفر رفرال"
    )
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_markup)
    except Exception:
        await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=back_markup)

    try:
        for admin_id in ADMIN_CHAT_IDS:
            await context.bot.send_message(
                admin_id,
                f"🎁 هدیهٔ حجمی رفرال\n\n"
                f"👤 کاربر: {format_user_info(user_id, show_copyable=False)}\n"
                f"📛 کانفیگ: `{config_name}`\n"
                f"🌐 سرور: {server_name}\n"
                f"➕ حجم: {REFERRAL_BONUS_GB} گیگ\n"
                f"📊 حجم کل جدید: {new_total_gb:.2f} GB\n"
                f"🕒 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
                parse_mode="Markdown"
            )
    except Exception as exc:
        logger.error(f"Failed to send referral bonus log to admins: {exc}")


# ============================================================
# --- بخش آموزش اتصال ---
# ============================================================

async def connection_tutorials_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع بخش آموزش اتصال"""
    message_text = (
        "📚 **آموزش اتصال**\n\n"
        "این بخش بر پایه هسته **V2Ray** است: برنامه‌های پشتیبانی‌شده، هزینه هر برنامه و مراحل اتصال را می‌بینید.\n"
        "لطفاً ابتدا سیستم عامل خود را انتخاب کنید:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="TUTORIAL_CAT_android")],
        [InlineKeyboardButton("📱 iOS", callback_data="TUTORIAL_CAT_ios")],
        [InlineKeyboardButton("💻 Windows", callback_data="TUTORIAL_CAT_windows")],
        [InlineKeyboardButton("📌 نکات کلی و عیب‌یابی", callback_data="TUTORIAL_CAT_tips")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_tutorial")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)

async def tutorial_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش برنامه‌های موجود در هر دسته"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.split("TUTORIAL_CAT_")[1]
    category_info = TUTORIAL_CATEGORIES.get(category)
    
    if not category_info:
        await query.edit_message_text("❌ دسته‌بندی مورد نظر پیدا نشد.")
        return
    
    message_text = f"**{category_info['title']}**\n\nلطفاً یکی از برنامه‌های زیر را انتخاب کنید:"
    
    keyboard = []
    for app in category_info['apps']:
        keyboard.append([InlineKeyboardButton(app['name'], callback_data=f"TUTORIAL_APP_{app['key']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به دسته‌بندی‌ها", callback_data="back_to_tutorial_categories")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit tutorial category message: {e}")

async def tutorial_app_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش آموزش کامل برای برنامه انتخاب شده"""
    query = update.callback_query
    await query.answer()
    
    app_key = query.data.split("TUTORIAL_APP_")[1]
    tutorial_info = CONNECTION_TUTORIALS.get(app_key)
    
    if not tutorial_info:
        await query.edit_message_text("❌ آموزش مورد نظر پیدا نشد.")
        return
    
    # ساخت پیام آموزش
    message_text = f"**{tutorial_info['title']}**\n\n"
    
    # اضافه کردن مراحل
    for step in tutorial_info['steps']:
        message_text += f"{step}\n"
    
    # اضافه کردن دکمه‌های برگشت
    keyboard = []
    
    # تشخیص دسته‌بندی بر اساس کلید
    if "android" in app_key:
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به Android", callback_data="TUTORIAL_CAT_android")])
    elif "ios" in app_key:
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به iOS", callback_data="TUTORIAL_CAT_ios")])
    elif "windows" in app_key:
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به Windows", callback_data="TUTORIAL_CAT_windows")])
    else:
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به نکات کلی", callback_data="TUTORIAL_CAT_tips")])
    
    keyboard.append([InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main_from_tutorial")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ارسال پیام (اگر پیام طولانی باشد، ممکن است نیاز به تقسیم داشته باشد)
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except error.BadRequest as e:
        if "Message is too long" in str(e):
            # اگر پیام خیلی طولانی است، آن را به چند قسمت تقسیم می‌کنیم
            parts = []
            current_part = f"**{tutorial_info['title']}**\n\n"
            
            for step in tutorial_info['steps']:
                if len(current_part) + len(step) + 1 < 4000:  # حد تلگرام
                    current_part += step + "\n"
                else:
                    parts.append(current_part)
                    current_part = step + "\n"
            
            if current_part:
                parts.append(current_part)
            
            # ارسال اولین قسمت با دکمه‌ها
            await query.edit_message_text(parts[0], parse_mode="Markdown", reply_markup=reply_markup)
            
            # ارسال قسمت‌های باقی‌مانده
            for part in parts[1:]:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=part,
                    parse_mode="Markdown"
                )
        else:
            raise

async def back_to_tutorial_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به دسته‌بندی‌های آموزش"""
    query = update.callback_query
    await query.answer()
    
    message_text = (
        "📚 **آموزش اتصال**\n\n"
        "در این بخش می‌توانید آموزش‌های کامل برای اتصال به سرویس VPN را مشاهده کنید.\n"
        "لطفاً ابتدا سیستم عامل خود را انتخاب کنید:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="TUTORIAL_CAT_android")],
        [InlineKeyboardButton("📱 iOS", callback_data="TUTORIAL_CAT_ios")],
        [InlineKeyboardButton("💻 Windows", callback_data="TUTORIAL_CAT_windows")],
        [InlineKeyboardButton("📌 نکات کلی و عیب‌یابی", callback_data="TUTORIAL_CAT_tips")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main_from_tutorial")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit back to tutorial categories: {e}")

# ============================================================
# --- دستور ادمین برای بررسی پروفایل کاربر ---
# ============================================================

async def check_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای بررسی پروفایل کاربر با جزئیات کامل"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ فرمت دستور:\n`/check [UserID]`\n\n"
            "مثال: `/check 123456789`\n"
            "همچنین می‌توانید روی هر پیامی که کاربر ارسال کرده ریپلای کرده و `/check` را تایپ کنید.",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ UserID باید عدد باشد.")
        return
    
    # فراخوانی تابع جدید برای نمایش پروفایل
    await show_user_profile(update, context, target_user_id)

async def check_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر برای وقتی که روی پیامی ریپلای شده و /check زده شود"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        return
    
    if not update.message.reply_to_message:
        return
    
    # گرفتن ID کاربر از پیام ریپلای شده
    replied_message = update.message.reply_to_message
    target_user_id = None
    
    if replied_message.from_user:
        target_user_id = replied_message.from_user.id
    elif replied_message.forward_from:
        target_user_id = replied_message.forward_from.id
    elif replied_message.forward_from_chat:
        # اگر از یک چت فوروارد شده
        await update.message.reply_text("❌ نمی‌توانم کاربر را از این پیام شناسایی کنم.")
        return
    
    if target_user_id:
        await show_user_profile(update, context, target_user_id)
    else:
        await update.message.reply_text("❌ نمی‌توانم کاربر را از این پیام شناسایی کنم.")

async def show_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int) -> None:
    """نمایش پروفایل کاربر (مستقل از نحوه فراخوانی)"""
    # دریافت اطلاعات کاربر
    users = load_users()
    str_target_user_id = str(target_user_id)
    
    if str_target_user_id not in users:
        # اگر کاربر در دیتابیس نیست، همچنان اطلاعات اولیه را نمایش بده
        message_text = f"👤 **پروفایل کاربر**\n\n"
        message_text += f"🆔 **شناسه کاربر:** {format_user_info(target_user_id)}\n"
        message_text += f"💰 **موجودی:** 0 تومان\n"
        message_text += f"📅 **وضعیت:** کاربر در دیتابیس اصلی ثبت نشده است\n"
        
        keyboard = [
            [
                InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"add_balance_{target_user_id}"),
                InlineKeyboardButton("📞 تماس با کاربر", callback_data=f"contact_user_{target_user_id}")
            ],
            [
                InlineKeyboardButton("🔍 بررسی بیشتر", callback_data=f"investigate_user_{target_user_id}"),
                InlineKeyboardButton("➕ ثبت کاربر جدید", callback_data=f"register_user_{target_user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        elif update.callback_query:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
        return
    
    user_data = users[str_target_user_id]
    
    # ساخت پیام اطلاعات کاربر
    message_text = f"👤 **پروفایل کاربر**\n\n"
    message_text += f"🆔 **شناسه کاربر:** {format_user_info(target_user_id)}\n"
    
    # اطلاعات حساب
    balance = user_data.get("balance", 0.0)
    join_date = user_data.get("join_date", "نامشخص")
    notes = user_data.get("notes", "")
    message_text += f"💰 **موجودی:** {balance:,.0f} تومان\n"
    message_text += f"📅 **تاریخ عضویت:** {join_date}\n"
    if notes:
        message_text += f"📝 **یادداشت:** {notes}\n"
    
    # اطلاعات رفرال
    referral_by = user_data.get("referral_by")
    referral_earnings = user_data.get("referral_earnings", 0.0)
    referrals_count = user_data.get("referrals_count", 0)
    
    if referral_by:
        message_text += f"🔗 **رفرال دهنده:** {format_user_info(referral_by, show_copyable=False)}\n"
    else:
        message_text += f"🔗 **رفرال دهنده:** ندارد\n"
    
    message_text += f"👥 **کاربران جذب شده:** {referrals_count} نفر\n"
    message_text += f"💵 **درآمد رفرال:** {referral_earnings:,.0f} تومان\n"
    
    # اطلاعات سرویس‌ها
    services = user_data.get("services", [])
    message_text += f"\n📂 **سرویس‌های فعال:** {len(services)} عدد\n"
    
    if services:
        message_text += "\n**لیست سرویس‌ها (آخرین 5 عدد):**\n"
        for i, service in enumerate(services[-5:], 1):
            config_name = service.get('config_name', 'نامشخص')
            server_key = service.get('server_key', 'نامشخص')
            server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', server_key)
            internal_key = service.get('internal_key', 'نامشخص')
            service_type = SERVICES.get(internal_key, {}).get('label', internal_key)
            purchase_date = service.get('purchase_date', 'نامشخص')
            
            try:
                purchase_date_formatted = datetime.datetime.fromisoformat(purchase_date).strftime("%Y/%m/%d")
            except:
                purchase_date_formatted = purchase_date
            
            message_text += f"{i}. **{config_name}**\n"
            message_text += f"   ├─ نوع: {service_type}\n"
            message_text += f"   ├─ سرور: {server_name}\n"
            message_text += f"   └─ تاریخ خرید: {purchase_date_formatted}\n"
        
        if len(services) > 5:
            message_text += f"\nو {len(services) - 5} سرویس دیگر...\n"
    
    # بررسی تاریخچه رفرال‌های جذب شده (آخرین 5 نفر)
    referral_history = get_referral_history(target_user_id)
    if referral_history:
        message_text += f"\n**👥 کاربران جذب شده (آخرین ۵ نفر):**\n"
        for i, referral in enumerate(referral_history[-5:], 1):
            ref_user_id = referral.get('user_id')
            ref_date = datetime.datetime.fromisoformat(referral.get('date')).strftime("%Y/%m/%d")
            message_text += f"{i}. {format_user_info(ref_user_id, show_copyable=False)} - {ref_date}\n"
        
        if len(referral_history) > 5:
            message_text += f"... و {len(referral_history) - 5} نفر دیگر\n"
    
    # بررسی تاریخچه درآمدهای رفرال
    earnings_history = get_referral_earnings_history(target_user_id)
    if earnings_history:
        total_earnings = sum(item['amount'] for item in earnings_history)
        message_text += f"\n**💰 تاریخچه درآمد رفرال:**\n"
        message_text += f"مجموع درآمد: **{total_earnings:,.0f}** تومان\n"
        message_text += f"تعداد تراکنش: {len(earnings_history)} عدد\n"
    
    # اطلاعات تست رایگان
    if has_user_used_free_trial(target_user_id):
        free_trial_users = load_free_trial_users()
        trial_data = free_trial_users.get(str_target_user_id, {})
        used_date = trial_data.get('used_date', 'نامشخص')
        try:
            used_date_formatted = datetime.datetime.fromisoformat(used_date).strftime("%Y/%m/%d")
        except:
            used_date_formatted = used_date
        
        message_text += f"\n⚠️ **تست رایگان:** استفاده کرده\n"
        message_text += f"📅 تاریخ استفاده: {used_date_formatted}\n"
    
    # دکمه‌های عملیاتی
    keyboard = [
        [
            InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"add_balance_{target_user_id}")
            #InlineKeyboardButton("📞 تماس با کاربر", callback_data=f"contact_user_{target_user_id}")
        ],
        [
            InlineKeyboardButton("📊 جزئیات تراکنش‌ها", callback_data=f"transaction_details_{target_user_id}_1"),
            InlineKeyboardButton("📂 بررسی سرویس‌ها", callback_data=f"service_details_{target_user_id}_1")
        ],
        [
            InlineKeyboardButton("🔍 بررسی جامع", callback_data=f"investigate_user_{target_user_id}"),
            InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data=f"edit_user_{target_user_id}")
        ],
        [
            InlineKeyboardButton("📋 لیست کامل رفرال‌ها", callback_data=f"full_referral_list_{target_user_id}_1"),
            InlineKeyboardButton("📋 کپی ID کاربر", callback_data=f"copy_user_id_{target_user_id}")
        ],
        [
            InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"refresh_profile_{target_user_id}"),
            InlineKeyboardButton("🔙 بستن", callback_data="close_profile")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(
                message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

async def add_balance_interactive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع فرآیند افزایش موجودی به صورت تعاملی"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.answer("❌ شما دسترسی لازم ندارید.", show_alert=True)
        return
    
    target_user_id = int(query.data.split("add_balance_")[1])
    context.user_data['add_balance_target'] = target_user_id
    
    await query.edit_message_text(
        f"💰 **افزایش موجودی کاربر**\n\n"
        f"👤 کاربر: {format_user_info(target_user_id)}\n\n"
        f"لطفاً مبلغ را به تومان وارد کنید:\n"
        f"مثال: 50000",
        parse_mode="Markdown"
    )
    
    # ذخیره وضعیت برای دریافت مبلغ
    context.user_data['awaiting_amount_for'] = target_user_id

async def copy_user_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """کپی کردن ID کاربر"""
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split("copy_user_id_")[1])
    
    # نمایش ID قابل کپی
    await query.answer(f"ID کاربر: {target_user_id}\n\nاین ID در کلیپ‌برد شما کپی شد.", show_alert=True)
    
    # می‌توانید اینجا کدی برای کپی کردن به کلیپ‌برد اضافه کنید
    # (البته تلگرام API مستقیم برای این کار ندارد، اما می‌توان پیام جدیدی با ID ارسال کرد)
    
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"🆔 **شناسه کاربر برای کپی:**\n\n`{target_user_id}`\n\n"
             f"می‌توانید این متن را کپی کنید.",
        parse_mode="Markdown"
    )

async def refresh_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """به‌روزرسانی پروفایل"""
    query = update.callback_query
    await query.answer("در حال به‌روزرسانی...")
    
    target_user_id = int(query.data.split("refresh_profile_")[1])
    
    # نمایش مجدد پروفایل
    await show_user_profile(update, context, target_user_id)

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
        price_text = f"{info['price_toman']:,.0f} تومان" if info['price_toman'] > 0 else "رایگان"
        button_text = f"🔹 {info['label']} ({volume_display}, {info['days']} روز) - {price_text}"
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
    
    # بررسی خاص برای سرویس تست رایگان
    if internal_key == "FREE_TRIAL":
        if has_user_used_free_trial(user_id):
            # ویرایش پیام به جای ارسال پیام جدید
            try:
                await query.edit_message_text(
                    "❌ شما قبلاً از سرویس تست رایگان استفاده کرده‌اید.\n\n"
                    "هر کاربر تنها یک بار می‌تواند از سرویس تست رایگان استفاده کند.\n"
                    "لطفاً یکی از پلن‌های پولی را انتخاب کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server','Server_1')}")]])
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ شما قبلاً از سرویس تست رایگان استفاده کرده‌اید.\n\n"
                    "هر کاربر تنها یک بار می‌تواند از سرویس تست رایگان استفاده کند.\n"
                    "لطفاً یکی از پلن‌های پولی را انتخاب کنید.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data=f"SELECT_SERVER_{context.user_data.get('selected_server','Server_1')}")]])
                )
            await send_main_menu(user_id, context)
            return ConversationHandler.END
    
    # برای سرویس‌های پولی، بررسی موجودی
    if price_toman > 0 and balance < price_toman:
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
    
    price_text = f"{price_toman:,.0f} تومان" if price_toman > 0 else "رایگان"
    
    message_text = (
        f"✅ تایید اطلاعات خرید\n\n"
        f"سرور: {server_name}\n"
        f"سرویس انتخابی: {panel_info['label']}\n"
        f"حجم: {panel_info['volume']}\n"
        f"اعتبار: {panel_info['days']} روز\n"
        f"تعداد کاربر مجاز: {panel_info['users']} نفر\n"
        f"نام کانفیگ: {user_input}\n\n"
        f"هزینه: {price_text}\n\n"
        "آیا از خرید خود مطمئن هستید؟"
    )
    
    # برای سرویس تست رایگان، پیام اضافی نمایش دهید
    if internal_key == "FREE_TRIAL":
        message_text += "\n\n⚠️ توجه: این سرویس فقط یک بار برای هر کاربر قابل استفاده است."
    
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
        days = min(int(panel_info['days']), MAX_SUBSCRIPTION_DAYS)
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
    
    # برای سرویس تست رایگان، بررسی مجدد
    if internal_key == "FREE_TRIAL":
        if has_user_used_free_trial(user_id):
            try:
                await query.edit_message_text(
                    "❌ شما قبلاً از سرویس تست رایگان استفاده کرده‌اید.\n\n"
                    "هر کاربر تنها یک بار می‌تواند از سرویس تست رایگان استفاده کند."
                )
            except Exception:
                pass
            await send_main_menu(user_id, context)
            context.user_data.pop('in_conversation', None)
            return ConversationHandler.END
    
    balance = get_user_balance(user_id)
    # بررسی موجودی فقط برای سرویس‌های پولی
    if price_toman > 0:
        balance = get_user_balance(user_id)
        if balance < price_toman:
            try:
                await query.edit_message_text(f"⚠️ موجودی ناکافی! موجودی شما: {balance:,.0f} تومان.")
            except Exception:
                pass
            await send_main_menu(user_id, context)
            context.user_data.pop('in_conversation', None)
            return ConversationHandler.END
    
    # کسر وجه فقط برای سرویس‌های پولی
    if price_toman > 0:
        new_balance = update_user_balance(user_id, -price_toman)
        # افزودن تراکنش خرید به تاریخچه
        add_transaction(user_id, "purchase", price_toman, f"خرید سرویس {panel_info['label']} - {config_name}")
    else:
        new_balance = get_user_balance(user_id)
        # افزودن تراکنش تست رایگان به تاریخچه
        add_transaction(user_id, "purchase", 0, f"سرویس تست رایگان - {config_name}")
    
    vmess_link, client_uuid, sub_link = await xui_add_client(server_key, user_id, volume_gb, config_name, days, limit_ip)
    
    if vmess_link and client_uuid and sub_link:
        add_user_service(user_id, config_name, sub_link, client_uuid, internal_key, server_key)
        
        # برای سرویس تست رایگان، کاربر را علامت‌گذاری کن
        if internal_key == "FREE_TRIAL":
            mark_free_trial_used(user_id)
        
        volume_display = panel_info['volume'].replace(' گیگ', 'GB')
        price_text = f"{price_toman:,.0f} تومان" if price_toman > 0 else "رایگان"
        
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
            f"هزینه: {price_text}\n"
        )
        
        if price_toman > 0:
            final_message += f"موجودی جدید: {new_balance:,.0f} تومان\n"
        
        final_message += (
            f"\n💡 لینک را لمس کنید تا کپی شود یا همین کیوآرکد را در برنامه اسکن کنید. در صورت مشکل، با پشتیبانی تماس بگیرید."
        )
        
        # پیام اضافی برای سرویس تست رایگان
        if internal_key == "FREE_TRIAL":
            final_message += f"\n\n⚠️ توجه: این سرویس تست رایگان فقط 1 روز اعتبار دارد و قابل تمدید نیست."
        
        # 🔴 ارسال لاگ کامل خرید به ادمین‌ها
        try:
            log_data = {
                'user_id': user_id,
                'config_name': config_name,
                'server_key': server_key,
                'server_name': server_name,
                'internal_key': internal_key,
                'service_label': panel_info['label'],
                'volume_gb': volume_gb,
                'days': days,
                'price_toman': price_toman,
                'old_balance': balance + price_toman if price_toman > 0 else balance,
                'new_balance': new_balance,
                'vmess_link': vmess_link,
                'sub_link': sub_link,
                'uuid': client_uuid,
                'client_count': limit_ip,
                'log_type': 'purchase'
            }
            
            await send_service_purchase_log_to_admins(context, log_data)
            logger.info(f"Purchase log sent to admins for user {user_id}, config {config_name}")
            
        except Exception as e:
            logger.error(f"Failed to send purchase log to admins: {e}")
            # تلاش برای ارسال پیام ساده‌تر به ادمین‌ها در صورت خطا
            try:
                for admin_id in ADMIN_CHAT_IDS:
                    await context.bot.send_message(
                        admin_id,
                        f"🛒 خرید جدید - کاربر: {format_user_info(user_id)} - کانفیگ: {config_name} - سرویس: {panel_info['label']}",
                        parse_mode="Markdown"
                    )
            except Exception as e2:
                logger.error(f"Failed to send simple notification to admins: {e2}")
        
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
            
    else:
        # بازگشت وجه فقط برای سرویس‌های پولی
        if price_toman > 0:
            update_user_balance(user_id, price_toman)
            # حذف تراکنش ناموفق از تاریخچه
            # (در این نسخه ساده، تراکنش‌ها را حذف نمی‌کنیم، اما می‌توانیم آن را علامت‌گذاری کنیم)
        
        # 🔴 ارسال لاگ خرید ناموفق به ادمین‌ها
        try:
            for admin_id in ADMIN_CHAT_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"❌ خرید ناموفق سرویس\n\n"
                    f"👤 کاربر: {format_user_info(user_id, show_copyable=False)}\n"
                    f"📛 کانفیگ: `{config_name}`\n"
                    f"🌐 سرور: {server_name}\n"
                    f"🛍️ سرویس: {panel_info['label']}\n"
                    f"💰 مبلغ: {price_toman:,.0f} تومان\n"
                    f"📝 خطا: ایجاد کانفیگ در پنل X-UI ناموفق بود\n"
                    f"🕒 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to send failed purchase log to admins: {e}")
        
        try:
            await query.edit_message_text("❌ خطا در ایجاد کانفیگ. لطفاً با پشتیبانی تماس بگیرید. در صورت کسر وجه، مبلغ به کیف پول شما بازگشت داده شد.")
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
                    "📂 سرویس‌های من\n\nشما در حال حاضر هیچ سرویس فعالی ندارید.\nبرای خرید، از دکمه «🛍️ خرید سرویس» استفاده کنید."
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
            internal_key = s.get('internal_key', 'Unknown')
            service_type = "🆓" if internal_key == "FREE_TRIAL" else "💰"
            text_lines.append(f"{service_type} {name} — {server_name}")
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
                "📂 سرویس‌های من\n\nشما در حال حاضر هیچ سرویس فعالی ندارید.\nبرای خرید، از دکمه «🛍️ خرید سرویس» استفاده کنید.",
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
            return

        text_lines = ["📂 سرویس‌های فعال شما:\n"]
        keyboard = []
        
        for s in services:
            name = s.get('config_name')
            server_key = s.get('server_key', 'Unknown')
            server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', "نامشناس")
            internal_key = s.get('internal_key', 'Unknown')
            service_type = "🆓" if internal_key == "FREE_TRIAL" else "💰"
            text_lines.append(f"{service_type} {name} — {server_name}")
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
    internal_key = current_service.get('internal_key', 'Unknown')
    
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
        
    # بررسی امکان تمدید
    renewal_allowed = False
    if internal_key == "FREE_TRIAL":
        renewal_allowed = False  # سرویس تست رایگان قابل تمدید نیست
    else:
        server_renewal = SERVERS_CONFIG.get(current_server_key, {}).get('tamdid', 1)
        service_info = SERVICES.get(internal_key, {})
        service_renewable = service_info.get('renewable', True)
        renewal_allowed = server_renewal and service_renewable
    
    keyboard = []
    if renewal_allowed:
        keyboard.append([InlineKeyboardButton("🔁 تمدید / افزایش حجم", callback_data=f"PROMPT_RENEW_{config_name}")])
        
    keyboard.append([
        InlineKeyboardButton("📝 لینک اشتراک", callback_data=f"SHOW_SUB_LINK_{config_name}"),
        InlineKeyboardButton("🔙 بازگشت به لیست سرویس‌ها", callback_data="back_to_services")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    service_type = "🆓 تست رایگان" if internal_key == "FREE_TRIAL" else "💰 سرویس پولی"
    
    message_text = (
        f"🔍 جزئیات سرویس: {config_name}\n\n"
        f"نوع: {service_type}\n"
        f"سرور: {server_name}\n\n"
        f"ترافیک کل: {total_display}\n"
        f"مصرف شده: {used_display}\n"
        f"باقی‌مانده: {remaining_display}\n"
        f"تاریخ انقضا: {expiry_date_str}\n\n"
        f"وضعیت: {'فعال' if client_data.get('enable') else 'غیرفعال'}"
    )
    
    if internal_key == "FREE_TRIAL":
        message_text += "\n\n⚠️ توجه: این سرویس تست رایگان قابل تمدید نیست. برای ادامه استفاده، لطفاً یک سرویس پولی خریداری کنید."
    
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
    
    # بررسی اینکه سرویس تست رایگان نباشد
    if current_service.get('internal_key') == "FREE_TRIAL":
        try:
            await query.edit_message_text(
                "❌ سرویس تست رایگان قابل تمدید نیست.\n\n"
                "برای ادامه استفاده، لطفاً یک سرویس پولی از منوی اصلی خریداری کنید."
            )
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
        # حذف سرویس تست رایگان از لیست تمدید
        if internal_key == "FREE_TRIAL":
            continue
            
        volume_display = panel['volume'].replace(' گیگ', 'GB')
        callback_data = f"RENEW_SELECT_{internal_key}_{panel['price_toman']}"
        button_text = f"➕ {panel['label']} (+{panel['days']} روز، +{volume_display}) - {panel['price_toman']:,.0f} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # گزینه‌های تمدید مثل بخش خرید: بی‌نهایت و حجمی (سفارشی)
    keyboard.append([InlineKeyboardButton(
        f"♾️ تمدید بی‌نهایت (تا {MAX_SUBSCRIPTION_DAYS} روز) - {UNLIMITED_PRICE_PER_USER:,} تومان",
        callback_data="RENEW_UNLIMITED")])
    keyboard.append([InlineKeyboardButton(
        "📦 تمدید حجمی (انتخاب حجم)",
        callback_data="RENEW_OPEN_VOLUME")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به سرویس‌های من", callback_data="back_to_services")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"🔁 تمدید سرویس: {config_name}\nسرور: {current_server_name}\n\nیکی از گزینه‌های زیر را انتخاب کنید. حجم به حجم فعلی اضافه می‌شود و اعتبار حداکثر تا {MAX_SUBSCRIPTION_DAYS} روز شارژ خواهد شد:",
            reply_markup=reply_markup
        )
    except error.BadRequest:
        await context.bot.send_message(user_id, "در حال بارگذاری پلن‌ها...", reply_markup=reply_markup)
        
    context.user_data['in_conversation'] = True
    return STATE_WAITING_FOR_RENEWAL_CONFIRM

async def _render_renewal_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش اسلایدر حجم برای تمدید"""
    query = update.callback_query
    volume_gb = int(context.user_data.get('renewal_vol', 10))
    volume_gb = max(1, min(VOLUME_MAX_GB, volume_gb))
    context.user_data['renewal_vol'] = volume_gb
    price = custom_plan_price('volume', volume_gb, 1)
    config_name = context.user_data.get('renewal_target_name') or ''
    text = (
        f"📦 تمدید حجمی سرویس {config_name}\n\n"
        f"حجم اضافه: {volume_gb} گیگابایت از {VOLUME_MAX_GB} گیگ\n"
        f"{custom_slider_bar(volume_gb, VOLUME_MAX_GB)}  {volume_gb}/{VOLUME_MAX_GB}\n"
        f"⏳ اعتبار: تا حداکثر {MAX_SUBSCRIPTION_DAYS} روز\n\n"
        f"💰 قیمت: {price:,} تومان\n"
        f"(هر گیگ {VOLUME_PRICE_PER_GB:,} تومان)"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏪ ۱۰-", callback_data="RENEW_VOL_ADJ_-10"),
         InlineKeyboardButton("◀️ ۱-", callback_data="RENEW_VOL_ADJ_-1"),
         InlineKeyboardButton("▶️ ۱+", callback_data="RENEW_VOL_ADJ_1"),
         InlineKeyboardButton("⏩ ۱۰+", callback_data="RENEW_VOL_ADJ_10")],
        [InlineKeyboardButton("✅ تایید و پرداخت", callback_data="RENEW_VOL_CONFIRM")],
        [InlineKeyboardButton("🔙 بازگشت به گزینه‌های تمدید",
                              callback_data=f"PROMPT_RENEW_{config_name}")],
    ])
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception:
        await context.bot.send_message(query.from_user.id, text, reply_markup=markup)


async def renew_open_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """باز کردن انتخاب حجم برای تمدید"""
    query = update.callback_query
    await query.answer("حجم مورد نظر را انتخاب کنید...")
    context.user_data['renewal_vol'] = 10
    await _render_renewal_volume(update, context)
    return STATE_WAITING_FOR_RENEWAL_CONFIRM


async def renew_adjust_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """کم/زیاد کردن حجم تمدید"""
    query = update.callback_query
    try:
        delta = int(query.data.split('RENEW_VOL_ADJ_')[1])
    except (IndexError, ValueError):
        await query.answer()
        return STATE_WAITING_FOR_RENEWAL_CONFIRM
    volume_gb = int(context.user_data.get('renewal_vol', 10)) + delta
    context.user_data['renewal_vol'] = max(1, min(VOLUME_MAX_GB, volume_gb))
    await query.answer()
    await _render_renewal_volume(update, context)
    return STATE_WAITING_FOR_RENEWAL_CONFIRM


async def _apply_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         price_toman: int, volume_add: int, plan_label: str,
                         set_unlimited: bool = False, days_add: int = None) -> int:
    """انجام تمدید (پرداخت، آپدیت پنل، پیام کاربر و لاگ ادمین)"""
    query = update.callback_query
    user_id = query.from_user.id
    config_name = context.user_data.get('renewal_target_name')
    server_key = context.user_data.get('renewal_target_server_key')
    server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', "نامشخص")
    days_add = days_add or MAX_SUBSCRIPTION_DAYS

    if not config_name or server_key not in SERVERS_CONFIG:
        try:
            await query.edit_message_text("❌ اطلاعات تمدید پیدا نشد. لطفاً از «سرویس‌های من» دوباره تلاش کنید.")
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
    add_transaction(user_id, "renewal", price_toman, f"تمدید سرویس {config_name} - {plan_label}")

    success, new_total_gb, new_expiry_days = await xui_update_client_v2(
        server_key, user_id, config_name, volume_add, days_add, set_unlimited=set_unlimited
    )

    if not success:
        update_user_balance(user_id, price_toman)
        add_transaction(user_id, "deposit", price_toman, f"بازگشت وجه تمدید ناموفق - {config_name}")
        try:
            await query.edit_message_text("❌ تمدید انجام نشد و مبلغ به کیف پول شما بازگشت داده شد.")
        except Exception:
            pass
        await send_main_menu(user_id, context)
        context.user_data.pop('in_conversation', None)
        return ConversationHandler.END

    volume_line = "نامحدود" if set_unlimited else (f"+{volume_add} GB" if volume_add else "بدون تغییر")
    final_message = (
        f"✅ تمدید سرویس {config_name} با موفقیت انجام شد!\n\n"
        f"گزینه: {plan_label}\n"
        f"افزایش حجم: {volume_line}\n"
        f"اعتبار: تا حداکثر {new_expiry_days} روز (سقف {MAX_SUBSCRIPTION_DAYS} روز)\n\n"
        f"موجودی جدید: {new_balance:,.0f} تومان\n"
        f"حجم کل (تقریبی): {new_total_gb:.2f} GB"
    )
    try:
        await query.edit_message_text(final_message)
    except Exception:
        await context.bot.send_message(user_id, final_message, )

    try:
        for admin_id in ADMIN_CHAT_IDS:
            await context.bot.send_message(
                admin_id,
                f"🔁 تمدید سرویس\n\n"
                f"👤 کاربر: {format_user_info(user_id, show_copyable=False)}\n"
                f"📛 کانفیگ: `{config_name}`\n"
                f"🌐 سرور: {server_name}\n"
                f"🎁 گزینه: {plan_label}\n"
                f"💰 مبلغ: {price_toman:,.0f} تومان\n"
                f"📅 اعتبار: {new_expiry_days} روز\n"
                f"🕒 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
                parse_mode="Markdown"
            )
    except Exception as exc:
        logger.error(f"Failed to send renewal log to admins: {exc}")

    await send_main_menu(user_id, context)
    context.user_data.pop('in_conversation', None)
    context.user_data.pop('renewal_target_name', None)
    context.user_data.pop('renewal_target_server_key', None)
    context.user_data.pop('renewal_vol', None)
    return ConversationHandler.END


async def renew_confirm_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تایید و پرداخت تمدید حجمی"""
    query = update.callback_query
    await query.answer("در حال اعمال تمدید...")
    volume_gb = int(context.user_data.get('renewal_vol', 10))
    price = custom_plan_price('volume', volume_gb, 1)
    return await _apply_renewal(update, context, price, volume_gb, f"📦 تمدید حجمی {volume_gb} گیگ")


async def renew_unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تمدید بی‌نهایت"""
    query = update.callback_query
    await query.answer("در حال اعمال تمدید...")
    price = UNLIMITED_PRICE_PER_USER
    return await _apply_renewal(update, context, price, 0, "♾️ تمدید بی‌نهایت", set_unlimited=True)


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
    
    # افزودن تراکنش تمدید به تاریخچه
    add_transaction(user_id, "renewal", price_toman, f"تمدید سرویس {config_name} - {panel_info['label']}")
    
    volume_add = int(panel_info['volume'].split(' ')[0])
    days_add = panel_info['days']
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
            
        # 🔴 ارسال لاگ تمدید به ادمین‌ها
        try:
            # دریافت اطلاعات فعلی سرویس
            _, client_data = await xui_get_client_info_by_name(server_key, config_name)
            
            log_data = {
                'user_id': user_id,
                'config_name': config_name,
                'server_key': server_key,
                'server_name': server_name,
                'internal_key': internal_key,
                'service_label': panel_info['label'],
                'volume_gb': volume_add,
                'days': days_add,
                'price_toman': price_toman,
                'old_balance': balance + price_toman,
                'new_balance': new_balance,
                'vmess_link': None,
                'sub_link': None,
                'uuid': client_data.get('id', 'نامشخص') if client_data else 'نامشخص',
                'client_count': client_data.get('limitIp', 1) if client_data else 1,
                'log_type': 'renewal',
                'total_gb': new_total_gb,
                'total_days': new_expiry_days
            }
            
            await send_service_purchase_log_to_admins(context, log_data)
            logger.info(f"Renewal log sent to admins for user {user_id}, config {config_name}")
            
        except Exception as e:
            logger.error(f"Failed to send renewal log to admins: {e}")
            # تلاش برای ارسال پیام ساده‌تر
            try:
                for admin_id in ADMIN_CHAT_IDS:
                    await context.bot.send_message(
                        admin_id,
                        f"🔁 تمدید سرویس - کاربر: {format_user_info(user_id)} - کانفیگ: {config_name} - پلن: {panel_info['label']}",
                        parse_mode="Markdown"
                    )
            except Exception as e2:
                logger.error(f"Failed to send simple renewal notification to admins: {e2}")
                
    else:
        update_user_balance(user_id, price_toman)
        
        # 🔴 ارسال لاگ تمدید ناموفق به ادمین‌ها
        try:
            for admin_id in ADMIN_CHAT_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"❌ تمدید ناموفق سرویس\n\n"
                    f"👤 کاربر: {format_user_info(user_id, show_copyable=False)}\n"
                    f"📛 کانفیگ: `{config_name}`\n"
                    f"🌐 سرور: {server_name}\n"
                    f"🛍️ پلن: {panel_info['label']}\n"
                    f"💰 مبلغ: {price_toman:,.0f} تومان\n"
                    f"📝 خطا: به‌روزرسانی کانفیگ در پنل X-UI ناموفق بود\n"
                    f"🕒 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to send failed renewal log to admins: {e}")
        
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
# =========
# -- Admin log
# ==============

async def recent_purchases_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای مشاهده خریدهای اخیر"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    # اینجا می‌توانید یک سیستم لاگ کامل پیاده‌سازی کنید
    # فعلاً یک پیام ساده نمایش می‌دهیم
    await update.message.reply_text(
        "📊 **سیستم لاگ خریدها**\n\n"
        "لاگ کامل خریدها و تمدیدهای کاربران به صورت خودکار به تمام ادمین‌ها ارسال می‌شود.\n\n"
        "برای مشاهده اطلاعات هر کاربر از دستور `/check [UserID]` استفاده کنید.",
        parse_mode="Markdown"
    )
    
# ============================================================
# --- سیستم جدید شارژ کیف پول (کارت به کارت) ---
# ============================================================

async def wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع فرآیند شارژ کیف پول با سیستم کارت به کارت"""
    user_id = update.effective_user.id
    current_balance = get_user_balance(user_id)
    
    message_text = (
        f"💰 شارژ کیف پول (کارت به کارت)\n\n"
        f"موجودی فعلی شما: {current_balance:,.0f} تومان\n\n"
        f"لطفاً مبلغ مورد نظر را به شماره کارت زیر واریز کنید:\n"
        f"`{CARD_NUMBER}`\n"
        f"سپس عکس رسید بانکی را در همین چت ارسال کنید."
    )
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    context.user_data['in_conversation'] = True
    context.user_data['wallet_flow'] = True
    return STATE_WAITING_FOR_RECEIPT

async def wallet_receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت عکس رسید و ارسال برای تأیید ادمین"""
    user_id = update.effective_user.id
    
    if update.message.text and update.message.text.strip().lower() == "❌ لغو عملیات":
        return await cancel_conversation(update, context)
    
    if not update.message.photo:
        await update.message.reply_text(
            "❌ لطفاً فقط عکس رسید بانکی را ارسال کنید.",
            reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
        )
        return STATE_WAITING_FOR_RECEIPT
    
    # ذخیره اطلاعات رسید
    receipt_file_id = update.message.photo[-1].file_id
    
    # درخواست مبلغ از کاربر
    await update.message.reply_text(
        "✅ عکس رسید دریافت شد.\n\nلطفاً مبلغ واریزی (به تومان) را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    
    context.user_data['receipt_file_id'] = receipt_file_id
    return STATE_GET_AMOUNT

async def wallet_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت مبلغ واریزی و ارسال برای تأیید ادمین"""
    user_id = update.effective_user.id
    
    if update.message.text.strip().lower() == "❌ لغو عملیات":
        return await cancel_conversation(update, context)
    
    try:
        amount_toman = int(update.message.text.replace(',', ''))
        if amount_toman < 1000:
            await update.message.reply_text("❌ مبلغ وارد شده باید حداقل ۱,۰۰۰ تومان باشد.")
            return STATE_GET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ مبلغ وارد شده نامعتبر است. لطفاً فقط عدد وارد کنید.")
        return STATE_GET_AMOUNT
    
    receipt_file_id = context.user_data.get('receipt_file_id')
    if not receipt_file_id:
        await update.message.reply_text("❌ خطا در دریافت اطلاعات رسید. لطفاً دوباره تلاش کنید.")
        return await cancel_conversation(update, context)
    
    # ذخیره رسید در لیست انتظار
    receipt_id = add_pending_receipt(user_id, amount_toman, receipt_file_id)
    
    # ارسال رسید به ادمین‌ها برای تأیید
    user = update.effective_user
    admin_message = (
        f"📩 درخواست شارژ کیف پول\n\n"
        f"👤 کاربر: {user.first_name} {user.last_name or ''}\n"
        f"🆔 ID: {format_user_info(user.id)}\n"
        f"💰 مبلغ: {amount_toman:,.0f} تومان\n"
        f"🆔 کد رسید: `{receipt_id}`\n\n"
        f"وضعیت: ⏳ در انتظار تأیید\n"
        f"لطفاً رسید را بررسی و تأیید کنید:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ تأیید رسید", callback_data=f"approve_receipt_{receipt_id}"),
            InlineKeyboardButton("❌ رد رسید", callback_data=f"reject_receipt_{receipt_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ارسال به تمام ادمین‌ها و ذخیره message_idها
    for admin_id in ADMIN_CHAT_IDS:
        try:
            message = await context.bot.send_photo(
                chat_id=admin_id,
                photo=receipt_file_id,
                caption=admin_message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            # ذخیره message_id برای این ادمین
            update_admin_message_ids(receipt_id, admin_id, message.message_id)
        except Exception as e:
            logger.error(f"Failed to send receipt to admin {admin_id}: {e}")
    
    # اطلاع به کاربر
    await update.message.reply_text(
        f"✅ رسید شما دریافت و برای تأیید به پشتیبانی ارسال شد.\n\n"
        f"📋 کد پیگیری: `{receipt_id}`\n"
        f"💰 مبلغ: {amount_toman:,.0f} تومان\n\n"
        f"پس از تأیید رسید، موجودی کیف پول شما افزایش خواهد یافت.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_REPLY_MARKUP
    )
    
    context.user_data.pop('receipt_file_id', None)
    context.user_data.pop('in_conversation', None)
    context.user_data.pop('wallet_flow', None)
    
    return ConversationHandler.END
    
async def approve_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر تأیید رسید توسط ادمین - نسخه بهبودیافته"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ شما دسترسی لازم برای این عمل را ندارید.")
        return
    
    # استخراج receipt_id از callback_data
    try:
        receipt_id = query.data.split('approve_receipt_')[1]
    except IndexError:
        await query.answer("❌ خطا در دریافت اطلاعات رسید.", show_alert=True)
        return
    
    # پردازش اتمی رسید
    success, receipt_data = process_receipt_atomic(receipt_id, 'approved', query.from_user.id)
    
    if not success:
        if receipt_data:
            # رسید قبلاً پردازش شده
            status = receipt_data['status']
            processed_by = receipt_data.get('processed_by')
            processed_at = receipt_data.get('processed_at', 'نامشخص')
            
            try:
                processed_date = datetime.datetime.fromisoformat(processed_at).strftime("%Y/%m/%d %H:%M")
            except:
                processed_date = processed_at
            
            if processed_by:
                admin_link = format_user_info(processed_by, show_copyable=False)
                message = f"❌ این رسید قبلاً توسط {admin_link} {status} شده است.\n📅 زمان: {processed_date}"
            else:
                message = f"❌ این رسید قبلاً {status} شده است.\n📅 زمان: {processed_date}"
            
            await query.answer(message, show_alert=True)
            return
        else:
            await query.answer("❌ رسید یافت نشد.", show_alert=True)
            return
    
    # 🔴 رسید با موفقیت پردازش شد (اتمی)
    user_id = receipt_data['user_id']
    amount_toman = receipt_data['amount_toman']
    
    # افزایش موجودی کاربر
    new_balance = update_user_balance(user_id, amount_toman)
    
    # افزودن تراکنش واریز به تاریخچه
    add_transaction(user_id, "deposit", amount_toman, f"واریز از طریق کارت به کارت - تأیید شده توسط ادمین", query.from_user.id)
    
    # محاسبه و اضافه کردن پورسانت رفرال (اگر مبلغ به حداقل رسید)
    referral_earning = 0.0
    referral_by = None
    
    if amount_toman >= REFERRAL_MIN_AMOUNT:
        referral_earning, referral_by = add_referral_earning(user_id, amount_toman)
    
    # ساخت پیام جدید برای ادمین‌ها
    admin_message = f"✅ رسید تأیید شد\n\n"
    admin_message += f"👤 کاربر: {format_user_info(user_id)}\n"
    admin_message += f"💰 مبلغ: {amount_toman:,.0f} تومان\n"
    admin_message += f"✅ توسط: {query.from_user.first_name} ({query.from_user.id})\n"
    admin_message += f"📅 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}"
    
    if referral_earning > 0 and referral_by:
        admin_message += f"\n🎉 پورسانت رفرال: {referral_earning:,.0f} تومان به رفرال دهنده {format_user_info(referral_by, show_copyable=False)} واریز شد."
    
    # به‌روزرسانی همه پیام‌های ادمین‌ها
    await update_all_admin_receipt_messages(context, receipt_id, admin_message, remove_buttons=True)
    
    # اطلاع به کاربر
    try:
        message_text = f"✅ رسید شما تأیید شد!\n\n💰 مبلغ {amount_toman:,.0f} تومان به کیف پول شما اضافه شد.\n\n💳 موجودی جدید: {new_balance:,.0f} تومان"
        
        # اضافه کردن اطلاعات رفرال اگر رفرال‌ای داشت
        if referral_earning > 0 and referral_by:
            message_text += f"\n\n🎉 پورسانت رفرال: {referral_earning:,.0f} تومان نیز به حساب {format_user_info(referral_by, show_copyable=False)} واریز شد."
        
        await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=MAIN_MENU_REPLY_MARKUP,
            parse_mode="Markdown"
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send receipt approval notification")
        # اطلاع به ادمین که کاربر ربات را بلاک کرده
        await query.message.reply_text(f"⚠️ رسید تأیید شد اما کاربر {format_user_info(user_id)} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.", parse_mode="Markdown")

async def reject_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر رد رسید توسط ادمین - نسخه بهبودیافته"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ شما دسترسی لازم برای این عمل را ندارید.")
        return
    
    # استخراج receipt_id از callback_data
    try:
        receipt_id = query.data.split('reject_receipt_')[1]
    except IndexError:
        await query.answer("❌ خطا در دریافت اطلاعات رسید.", show_alert=True)
        return
    
    # پردازش اتمی رسید
    success, receipt_data = process_receipt_atomic(receipt_id, 'rejected', query.from_user.id)
    
    if not success:
        if receipt_data:
            # رسید قبلاً پردازش شده
            status = receipt_data['status']
            processed_by = receipt_data.get('processed_by')
            processed_at = receipt_data.get('processed_at', 'نامشخص')
            
            try:
                processed_date = datetime.datetime.fromisoformat(processed_at).strftime("%Y/%m/%d %H:%M")
            except:
                processed_date = processed_at
            
            if processed_by:
                admin_link = format_user_info(processed_by, show_copyable=False)
                message = f"❌ این رسید قبلاً توسط {admin_link} {status} شده است.\n📅 زمان: {processed_date}"
            else:
                message = f"❌ این رسید قبلاً {status} شده است.\n📅 زمان: {processed_date}"
            
            await query.answer(message, show_alert=True)
            return
        else:
            await query.answer("❌ رسید یافت نشد.", show_alert=True)
            return
    
    # 🔴 رسید با موفقیت رد شد (اتمی)
    user_id = receipt_data['user_id']
    
    # ساخت پیام جدید برای ادمین‌ها
    admin_message = f"❌ رسید رد شد\n\n"
    admin_message += f"👤 کاربر: {format_user_info(user_id)}\n"
    admin_message += f"❌ توسط: {query.from_user.first_name} ({query.from_user.id})\n"
    admin_message += f"📅 زمان: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
    admin_message += f"📝 دلیل: توسط ادمین رد شد"
    
    # به‌روزرسانی همه پیام‌های ادمین‌ها
    await update_all_admin_receipt_messages(context, receipt_id, admin_message, remove_buttons=True)
    
    # اطلاع به کاربر
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ متأسفانه رسید شما توسط پشتیبانی رد شد.\n\nلطفاً با ارسال رسید معتبر دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send receipt rejection notification")

# ============================================================
# --- دستور ادمین برای افزایش موجودی کاربر ---
# ============================================================

async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای افزایش موجودی کاربر با مدیریت خطای کاربر مسدود شده"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("❌ فرمت دستور:\n`/add [UserID] [Amount]`", parse_mode="Markdown")
        return
    
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ UserID و Amount باید عدد باشند.")
        return
    
    new_balance = update_user_balance(user_id, amount)
    
    # افزودن تراکنش به تاریخچه
    add_transaction(user_id, "admin_adjustment", amount, f"افزایش موجودی توسط دستور /add", update.effective_user.id)
    
    # ارسال لاگ به ادمین‌ها
    await send_admin_action_log(context, update.effective_user.id, 'add', {
        'target_user_id': user_id,
        'amount': amount,
        'new_balance': new_balance
    })
    
    # اطلاع به ادمین
    user_link = format_user_info(user_id)
    await update.message.reply_text(
        f"✅ موجودی کاربر {user_link} به میزان {amount:,.0f} تومان افزایش یافت.\n\n💰 موجودی جدید: {new_balance:,.0f} تومان",
        parse_mode="Markdown"
    )
    
    # اطلاع به کاربر - با مدیریت بهتر خطا
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💰 موجودی کیف پول شما توسط ادمین به میزان {amount:,.0f} تومان افزایش یافت.\n\n💳 موجودی جدید: {new_balance:,.0f} تومان",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send balance update notification")
        # اطلاع به ادمین که کاربر ربات را بلاک کرده
        await update.message.reply_text(
            f"⚠️ موجودی افزایش یافت اما کاربر {user_link} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.",
            parse_mode="Markdown"
        )
    except error.BadRequest as e:
        logger.error(f"BadRequest when notifying user {user_id}: {e}")
        if "chat not found" in str(e).lower():
            await update.message.reply_text(
                f"⚠️ موجودی افزایش یافت اما چت با کاربر {user_link} یافت نشد (ربات را ترک کرده است).",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
        await update.message.reply_text(
            f"⚠️ خطا در ارسال اطلاعیه به کاربر {user_link}: {str(e)[:100]}",
            parse_mode="Markdown"
        )
# ============================================================
# --- دستور ادمین برای ارسال پیام همگانی (Announce) ---
# ============================================================

async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور ادمین برای ارسال پیام همگانی به تمام کاربران"""
    if update.effective_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("❌ شما دسترسی لازم برای این دستور را ندارید.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ لطفاً پیام خود را بعد از دستور وارد کنید.\nمثال: `/announce سلام به همه کاربران عزیز!`", parse_mode="Markdown")
        return
    
    # جمع‌آوری متن پیام
    message_text = ' '.join(context.args)
    
    # دریافت لیست تمام کاربران
    users = load_users()
    user_ids = list(users.keys())
    
    if not user_ids:
        await update.message.reply_text("❌ هیچ کاربری در سیستم وجود ندارد.")
        return
    
    # ارسال پیام به تمام کاربران
    success_count = 0
    fail_count = 0
    blocked_users = []
    
    await update.message.reply_text(f"📢 در حال ارسال پیام به {len(user_ids)} کاربر...")
    
    for str_user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=int(str_user_id),
                text=f"📢 **پیام همگانی از مدیریت:**\n\n{message_text}",
                parse_mode="Markdown"
            )
            success_count += 1
            # تاخیر کوچک برای جلوگیری از محدودیت تلگرام
            await asyncio.sleep(0.1)
        except error.Forbidden:
            blocked_users.append(str_user_id)
            fail_count += 1
        except Exception as e:
            logger.error(f"Failed to send announcement to user {str_user_id}: {e}")
            fail_count += 1
    
    # گزارش نتایج به ادمین
    report_message = (
        f"📊 **گزارش ارسال پیام همگانی**\n\n"
        f"✅ ارسال موفق: {success_count} کاربر\n"
        f"❌ ارسال ناموفق: {fail_count} کاربر\n"
        f"📝 متن پیام: {message_text[:100]}..."
    )
    
    if blocked_users:
        report_message += f"\n\n🚫 کاربران مسدود شده ({len(blocked_users)} نفر):\n"
        for i, user_id in enumerate(blocked_users[:10], 1):
            report_message += f"{i}. {format_user_info(int(user_id))}\n"
        if len(blocked_users) > 10:
            report_message += f"و {len(blocked_users) - 10} کاربر دیگر..."
    
    await update.message.reply_text(report_message, parse_mode="Markdown")
    
    # ارسال لاگ به ادمین‌ها
    await send_admin_action_log(context, update.effective_user.id, 'announce', {
        'message': message_text,
        'success_count': success_count,
        'fail_count': fail_count,
        'blocked_users': len(blocked_users)
    })

# ============================================================
# --- باقی هندلرها ---
# ============================================================

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
    context.user_data.pop('receipt_file_id', None)
    context.user_data.pop('wallet_flow', None)
    context.user_data.pop('awaiting_amount_for', None)
    context.user_data.pop('awaiting_message_for', None)
    context.user_data.pop('edit_balance_target', None)
    context.user_data.pop('edit_referral_target', None)
    context.user_data.pop('edit_notes_target', None)
    context.user_data.pop('addall_amount', None)
    
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
    """فوروارد پیام تیکت به ادمین‌ها و ذخیره اطلاعات برای پاسخ"""
    user = update.effective_user
    original_message = update.message
    
    try:
        admin_message_header = f"📞 **پیام پشتیبانی جدید**\n\n👤 کاربر: {user.first_name}\n🆔 شناسه: `{user.id}`\n📱 پیام:\n\n"
        
        # اطمینان از وجود ساختار نگاشت
        if 'support_map' not in context.bot_data: 
            context.bot_data['support_map'] = {}
        
        success_count = 0
        admin_message_ids = []  # لیست message_idهای ارسالی به ادمین‌ها
        
        for admin_id in ADMIN_CHAT_IDS:
            try:
                # ارسال هدر به ادمین
                header_message = await context.bot.send_message(
                    admin_id, 
                    admin_message_header, 
                    parse_mode="Markdown"
                )
                
                # فوروارد پیام اصلی به ادمین
                forwarded_message = await context.bot.forward_message(
                    chat_id=admin_id,
                    from_chat_id=user.id,
                    message_id=original_message.message_id
                )
                
                # ذخیره اطلاعات نگاشت - هر دو پیام (هدر و پیام اصلی)
                context.bot_data['support_map'][header_message.message_id] = {
                    'user_id': user.id,
                    'user_message_id': original_message.message_id
                }
                context.bot_data['support_map'][forwarded_message.message_id] = {
                    'user_id': user.id,
                    'user_message_id': original_message.message_id
                }
                
                # ذخیره پیام‌های ارسالی
                admin_message_ids.append(header_message.message_id)
                admin_message_ids.append(forwarded_message.message_id)
                
                success_count += 1
                
                # ارسال راهنمای پاسخ به ادمین
                #await context.bot.send_message(
                #    admin_id,
                #    "💡 برای پاسخ به کاربر، کافیست روی هر یک از پیام‌های بالا **Reply** کرده و پیام خود را بنویسید.",
                #    reply_to_message_id=forwarded_message.message_id
                #)
                
            except error.Forbidden:
                logger.warning(f"Bot is blocked by admin {admin_id}, skipping this admin")
                continue
            except Exception as e:
                logger.error(f"Failed to forward message to admin {admin_id}: {e}")
                continue
        
        # اگر حداقل به یک ادمین ارسال شد، پیام تأیید به کاربر بفرست
        if success_count > 0:
            try:
                # ذخیره اطلاعات پیام کاربر
                if 'user_support_messages' not in context.bot_data:
                    context.bot_data['user_support_messages'] = {}
                
                context.bot_data['user_support_messages'][str(user.id)] = {
                    'message_id': original_message.message_id,
                    'admin_message_ids': admin_message_ids,
                    'timestamp': datetime.datetime.now().isoformat()
                }
                
                await update.message.reply_text(
                    "✅ پیام شما به پشتیبانی ارسال شد. منتظر پاسخ باشید.", 
                    reply_markup=MAIN_MENU_REPLY_MARKUP
                )
            except error.Forbidden:
                logger.warning(f"User {user.id} blocked the bot after sending support message")
                # در این حالت کاربر ربات را بلاک کرده، کاری نمی‌توان کرد
        else:
            # اگر به هیچ ادمینی نتوانست ارسال کند
            try:
                await update.message.reply_text(
                    "❌ در حال حاضر امکان ارسال پیام به پشتیبانی وجود ندارد. لطفاً بعداً تلاش کنید.",
                    reply_markup=MAIN_MENU_REPLY_MARKUP
                )
            except error.Forbidden:
                logger.warning(f"User {user.id} blocked the bot and no admins are available")
    
    except error.Forbidden:
        logger.warning(f"User {user.id} blocked the bot during support process")
        # کاربر ربات را بلاک کرده، نمی‌توان پیام ارسال کرد
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Failed to handle support ticket: {e}")
        try:
            await update.message.reply_text(
                "❌ خطایی در ارسال پیام شما رخ داد.", 
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
        except error.Forbidden:
            logger.warning(f"User {user.id} blocked the bot after error in support")
        
    context.user_data.pop('in_conversation', None)
    return ConversationHandler.END

async def reply_to_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ ادمین به تیکت - نسخه بهبودیافته"""
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لطفاً برای پاسخ دادن، پیام اصلی کاربر را ریپلای کنید.")
        return
    
    admin_message = update.message
    replied_message = update.message.reply_to_message
    
    # جستجوی شناسه کاربر از طریق نگاشت پیام‌ها
    user_id = None
    
    # روش 1: جستجو در support_map
    if replied_message.message_id in context.bot_data.get('support_map', {}):
        mapping_data = context.bot_data['support_map'][replied_message.message_id]
        user_id = mapping_data.get('user_id')
    
    # روش 2: جستجو در user_support_messages
    if not user_id:
        for str_user_id, user_data in context.bot_data.get('user_support_messages', {}).items():
            if replied_message.message_id in user_data.get('admin_message_ids', []):
                user_id = int(str_user_id)
                break
    
    if user_id:
        try:
            # ارسال پاسخ به کاربر
            admin_name = admin_message.from_user.first_name
            if admin_message.from_user.id in ADMIN_CHAT_IDS:
                admin_name = "پشتیبانی"
            
            response_text = (
                f"💬 **پاسخ از {admin_name}:**\n\n"
                f"{admin_message.text}\n\n"
                f"_برای پاسخ مجدد، از دکمه 📞 پشتیبانی استفاده کنید._"
            )
            
            await context.bot.send_message(
                user_id,
                response_text,
                parse_mode="Markdown"
            )
            
            # تأیید ارسال به ادمین
            await admin_message.reply_text(
                f"✅ پاسخ شما برای کاربر {user_id} ارسال شد.",
                reply_to_message_id=admin_message.message_id
            )
            
            logger.info(f"Admin reply sent to user {user_id}")
            
        except error.Forbidden:
            logger.warning(f"Failed to send reply to user {user_id}: bot was blocked by the user")
            await admin_message.reply_text(
                "❌ ارسال پاسخ به کاربر ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
            )
            
        except Exception as e:
            logger.error(f"Failed to reply to user {user_id}: {e}")
            await admin_message.reply_text(f"❌ خطایی در ارسال پاسخ به کاربر رخ داد: {str(e)}")
            
    else:
        # اگر شناسه کاربر پیدا نشد، استفاده از متد قدیمی
        original_message_id = replied_message.message_id
        old_user_id = context.bot_data.get('support_map', {}).get(original_message_id)
        
        if old_user_id:
            try:
                await context.bot.send_message(
                    old_user_id,
                    f"💬 **پاسخ پشتیبانی:**\n\n{admin_message.text}",
                    parse_mode="Markdown"
                )
                await admin_message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
                
            except error.Forbidden:
                await admin_message.reply_text(
                    "❌ ارسال پاسخ به کاربر ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
                )
            except Exception as e:
                logger.error(f"Failed to reply to user {old_user_id}: {e}")
                await admin_message.reply_text(f"❌ خطایی در ارسال پاسخ به کاربر رخ داد: {e}")
        else:
            await admin_message.reply_text(
                "❌ شناسه کاربر پیدا نشد. لطفاً مطمئن شوید که روی پیام اصلی کاربر ریپلای کرده‌اید."
            )

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

async def back_to_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به لینک رفرال از تاریخچه"""
    query = update.callback_query
    await query.answer("بازگشت...")
    user_id = query.from_user.id
    
    bot_username = (await context.bot.get_me()).username
    message_text, reply_markup = build_referral_page(user_id, bot_username)
    try:
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(user_id, message_text, parse_mode="Markdown", reply_markup=reply_markup)

async def back_to_main_from_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به منوی اصلی از بخش آموزش"""
    query = update.callback_query
    await query.answer("بازگشت به منوی اصلی...")
    
    await send_main_menu(query.from_user.id, context)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر جامع برای دکمه‌های شیشه‌ای (غیر از مکالمات)"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # هندلرهای اصلی
    if data == "OPEN_MY_SERVICES" or data == "back_to_services":
        return await my_services(update, context) 
    
    if data == "back_to_main_from_services":
        return await back_to_main_menu(update, context)
        
    if data == "back_to_select_server":
        return await back_to_select_server(update, context)
        
    if data == "back_to_referral_link":
        return await back_to_referral_link(update, context)
        
    if data == "back_to_main_from_tutorial":
        return await back_to_main_menu(update, context)
        
    if data.startswith("approve_receipt_"):
        return await approve_receipt_callback(update, context)
        
    if data.startswith("reject_receipt_"):
        return await reject_receipt_callback(update, context)
        
    if data == "REFERRAL_BONUS_CLAIM":
        return await referral_bonus_claim(update, context)

    if data.startswith("REFERRAL_BONUS_SVC_"):
        return await referral_bonus_choose_service(update, context)

    if data.startswith("REFERRAL_BONUS_APPLY_"):
        return await referral_bonus_apply(update, context)

    if data.startswith("REFERRAL_HISTORY_"):
        return await referral_history(update, context)
        
    if data.startswith("TUTORIAL_CAT_"):
        return await tutorial_category_handler(update, context)
        
    if data.startswith("TUTORIAL_APP_"):
        return await tutorial_app_handler(update, context)
        
    if data == "back_to_tutorial_categories":
        return await back_to_tutorial_categories(update, context)
    
    if data.startswith("add_balance_"):
        return await add_balance_interactive(update, context)
    
    if data.startswith("copy_user_id_"):
        return await copy_user_id_callback(update, context)
    
    if data.startswith("refresh_profile_"):
        return await refresh_profile_callback(update, context)
    
    # هندلرهای جدید برای قابلیت‌های ادمین
    if data.startswith("transaction_details_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1
        return await show_transaction_details(update, context, target_user_id, page)
        
    if data.startswith("service_details_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1
        return await show_service_details_admin(update, context, target_user_id, page)
        
    if data.startswith("edit_user_"):
        target_user_id = int(data.split("edit_user_")[1])
        return await edit_user_info_start(update, context, target_user_id)
    
    if data.startswith("edit_balance_"):
        return await edit_user_balance_start(update, context)
        
    if data.startswith("edit_referral_"):
        return await edit_user_referral_start(update, context)
        
    if data.startswith("edit_notes_"):
        return await edit_user_notes_start(update, context)
        
    if data.startswith("investigate_user_"):
        target_user_id = int(data.split("investigate_user_")[1])
        return await investigate_user_info(update, context, target_user_id)
        
    if data.startswith("register_user_"):
        target_user_id = int(data.split("register_user_")[1])
        return await register_user_admin(update, context, target_user_id)
        
    if data.startswith("full_referral_list_"):
        parts = data.split("_")
        target_user_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1
        return await show_full_referral_list(update, context, target_user_id, page)
        
    if data.startswith("referral_earnings_history_"):
        parts = data.split("_")
        target_user_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1
        return await referral_earnings_history_admin(update, context, target_user_id, page)
    
    # هندلرهای جدید برای /allmembers
    if data == "allmembers_page_info":
        await query.answer("شماره صفحه جاری", show_alert=False)
        return
    
    if data.startswith("allmembers_page_"):
        try:
            page = int(data.split("allmembers_page_")[1])
        except ValueError:
            await query.answer("❌ شماره صفحه نامعتبر است.", show_alert=True)
            return
        return await show_all_users_list(update, context, page)
    
    if data == "close_allmembers":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("لیست کاربران بسته شد.")
        return
    
    if data == "export_all_users":
        await query.answer("⚠️ این قابلیت در حال حاضر در دسترس نیست.", show_alert=True)
        return
    
    if data == "addall_start":
        context.user_data['addall_amount'] = None
        await query.answer("لطفاً از دستور /addall استفاده کنید.")
        await query.edit_message_text(
            "💰 **افزایش موجودی گروهی**\n\n"
            "لطفاً از دستور زیر استفاده کنید:\n"
            "`/addall [Amount]`\n\n"
            "مثال:\n"
            "`/addall 50000` - افزایش 50,000 تومان به تمام کاربران\n"
            "`/addall -10000` - کاهش 10,000 تومان از تمام کاربران",
            parse_mode="Markdown"
        )
        return
    
    if data == "addall_confirm":
        return await addall_confirm_callback(update, context)
    
    if data == "addall_cancel":
        return await addall_cancel_callback(update, context)
    
    if data == "back_to_main_from_admin":
        await send_main_menu(query.from_user.id, context)
        return
    
    if data.startswith("transaction_page_info") or data.startswith("service_page_info") or data.startswith("referral_page_info") or data.startswith("earnings_page_info"):
        await query.answer("شماره صفحه جاری", show_alert=False)
        return
    
    if data == "close_profile":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("پروفایل بسته شد.")
        return
        
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
            price_text = f"{panel_info['price_toman']:,.0f} تومان" if panel_info['price_toman'] > 0 else "رایگان"
            
            message_text = (
                f"جزئیات پلن: {panel_info['label']}\n\n"
                f"حجم: {volume_display}\n"
                f"اعتبار: {panel_info['days']} روز\n"
                f"تعداد کاربر مجاز: {panel_info['users']} نفر\n"
                f"توضیحات: {description}\n\n"
                f"قیمت: {price_text}"
            )
            
            # برای سرویس تست رایگان، پیام اضافی
            if internal_key == "FREE_TRIAL":
                user_id = query.from_user.id
                if has_user_used_free_trial(user_id):
                    message_text += "\n\n⚠️ شما قبلاً از سرویس تست رایگان استفاده کرده‌اید. هر کاربر تنها یک بار می‌تواند از این سرویس استفاده کند."
                else:
                    message_text += "\n\n⚠️ توجه: این سرویس فقط یک بار برای هر کاربر قابل استفاده است."
            
            buy_callback_data = f"CONFIRM_PLAN_PURCHASE_{internal_key}"
            
            keyboard = [
                [InlineKeyboardButton(f"✅ تایید و خرید ({price_text})", callback_data=buy_callback_data)],
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
    
    # اگر هیچکدام از الگوها مطابقت نکرد
    if data.startswith("check_each_service_"):
        return await check_each_service_handler(update, context, int(data.split("check_each_service_")[1]))

    if data.startswith("delete_service_ask_"):
        parts = data.split("_")
        return await delete_service_ask(update, context, int(parts[3]), int(parts[4]))

    if data.startswith("delete_service_do_"):
        parts = data.split("_")
        return await delete_service_do(update, context, int(parts[3]), int(parts[4]))

    if data.startswith("delete_services_"):
        return await delete_services_menu(update, context, int(data.split("delete_services_")[1]))

    if data.startswith("export_referrals_"):
        return await export_referrals_csv(update, context, int(data.split("export_referrals_")[1]))

    if data.startswith("contact_user_"):
        return await contact_user_start(update, context, int(data.split("contact_user_")[1]))

    await query.answer("❌ این دکمه هنوز پیاده‌سازی نشده است.", show_alert=True)


# ============================================================
# --- ابزارهای ادمین: بررسی/حذف سرویس‌ها، خروجی رفرال، تماس با کاربر ---
# ============================================================

async def _safe_edit_or_send(query, context, text, reply_markup=None):
    """ویرایش پیام؛ در صورت خطا ارسال پیام جدید"""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await context.bot.send_message(query.from_user.id, text, reply_markup=reply_markup)
        except Exception:
            pass


def _admin_back_keyboard(target_user_id, callback=None, label="🔙 بازگشت"):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=callback or f"service_details_{target_user_id}_1")
    ]])


async def check_each_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """بررسی تک‌تک سرویس‌های یک کاربر روی پنل"""
    query = update.callback_query
    services = get_user_services(target_user_id)

    if not services:
        await _safe_edit_or_send(
            query, context,
            f"📂 کاربر {format_user_info(target_user_id, show_copyable=False)} سرویسی ندارد.",
            _admin_back_keyboard(target_user_id, callback=f"refresh_profile_{target_user_id}")
        )
        return

    lines = [f"🔍 وضعیت سرویس‌های {format_user_info(target_user_id, show_copyable=False)}", ""]
    for index, service in enumerate(services, 1):
        config_name = service.get('config_name', 'نامشخص')
        server_key = service.get('server_key')
        server_name = SERVERS_CONFIG.get(server_key, {}).get('display_name', server_key or 'نامشخص')

        _, client = await xui_get_client_info_by_name(server_key, config_name)
        if not client:
            lines.append(f"{index}. {config_name} ({server_name})\n   ❌ روی پنل پیدا نشد\n")
            continue

        used = int(client.get('up') or 0) + int(client.get('down') or 0)
        total = int(client.get('totalGB') or 0)
        used_text = convert_bytes_to_display(used)
        total_text = convert_bytes_to_display(total) if total > 0 else "نامحدود"

        expiry_time = int(client.get('expiryTime') or 0)
        if expiry_time > 0:
            expiry_dt = datetime.datetime.fromtimestamp(expiry_time / 1000)
            days_left = max((expiry_dt - datetime.datetime.now()).days, 0)
            expiry_text = f"{expiry_dt.strftime('%Y/%m/%d')} ({days_left} روز مانده)"
        else:
            expiry_text = "نامحدود"

        status = "🟢 فعال" if client.get('enable') else "🔴 غیرفعال"
        lines.append(f"{index}. {config_name} ({server_name})\n"
                     f"   {status} | مصرف: {used_text} از {total_text}\n"
                     f"   انقضا: {expiry_text}\n")

    message = "\n".join(lines)
    if len(message) > 4000:
        message = message[:3990] + "\n…"
    await _safe_edit_or_send(query, context, message,
                             _admin_back_keyboard(target_user_id, callback=f"service_details_{target_user_id}_1"))


async def delete_services_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """لیست سرویس‌های کاربر برای حذف"""
    query = update.callback_query
    services = get_user_services(target_user_id)

    if not services:
        await _safe_edit_or_send(
            query, context,
            f"📂 کاربر {format_user_info(target_user_id, show_copyable=False)} سرویسی برای حذف ندارد.",
            _admin_back_keyboard(target_user_id, callback=f"refresh_profile_{target_user_id}")
        )
        return

    keyboard = []
    for index, service in enumerate(services):
        keyboard.append([InlineKeyboardButton(
            f"🗑️ {service.get('config_name', 'نامشخص')}",
            callback_data=f"delete_service_ask_{target_user_id}_{index}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"refresh_profile_{target_user_id}")])

    await _safe_edit_or_send(
        query, context,
        f"🗑️ حذف سرویس‌های {format_user_info(target_user_id, show_copyable=False)}\n\n"
        "کدام سرویس حذف شود؟ (هم از پنل و هم از حساب کاربر)",
        InlineKeyboardMarkup(keyboard)
    )


async def delete_service_ask(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, index: int):
    """درخواست تایید حذف یک سرویس"""
    query = update.callback_query
    services = get_user_services(target_user_id)
    if index < 0 or index >= len(services):
        await _safe_edit_or_send(
            query, context, "❌ سرویس پیدا نشد (لیست تغییر کرده است).",
            _admin_back_keyboard(target_user_id, callback=f"delete_services_{target_user_id}")
        )
        return

    config_name = services[index].get('config_name', 'نامشخص')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"delete_service_do_{target_user_id}_{index}")],
        [InlineKeyboardButton("🔙 انصراف", callback_data=f"delete_services_{target_user_id}")]
    ])
    await _safe_edit_or_send(
        query, context,
        f"⚠️ حذف سرویس {config_name}\n\n"
        "این کلاینت از پنل حذف می‌شود و لینک اتصال کاربر از کار می‌افتد. مطمئن هستید؟",
        keyboard
    )


async def delete_service_do(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, index: int):
    """حذف سرویس از پنل و از حساب کاربر"""
    query = update.callback_query
    services = get_user_services(target_user_id)
    if index < 0 or index >= len(services):
        await _safe_edit_or_send(
            query, context, "❌ سرویس پیدا نشد (لیست تغییر کرده است).",
            _admin_back_keyboard(target_user_id, callback=f"delete_services_{target_user_id}")
        )
        return

    service = services[index]
    config_name = service.get('config_name', 'نامشخص')
    server_key = service.get('server_key')

    removed_from_panel = await xui_delete_client(server_key, config_name)
    if not removed_from_panel:
        await _safe_edit_or_send(
            query, context,
            f"❌ حذف سرویس {config_name} از پنل ناموفق بود.\n"
            "سرویس در حساب کاربر باقی ماند تا لینک کاربر بی‌دلیل از کار نیفتد.",
            _admin_back_keyboard(target_user_id, callback=f"delete_services_{target_user_id}")
        )
        return

    users = load_users()
    str_target = str(target_user_id)
    if str_target in users and 'services' in users[str_target]:
        users[str_target]['services'] = [
            s for s in users[str_target]['services'] if s.get('config_name') != config_name
        ]
        save_users(users)

    await send_admin_action_log(context, query.from_user.id, 'delete', {
        'target_user_id': target_user_id,
        'config_name': config_name,
        'server_key': server_key
    })

    await _safe_edit_or_send(
        query, context,
        f"✅ سرویس {config_name} از پنل و از حساب کاربر حذف شد.",
        _admin_back_keyboard(target_user_id, callback=f"service_details_{target_user_id}_1")
    )


async def export_referrals_csv(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """ارسال خروجی CSV از کاربران جذب‌شده"""
    query = update.callback_query
    history = get_referral_history(target_user_id)

    if not history:
        await query.answer("هیچ رفرالی برای این کاربر ثبت نشده است.", show_alert=True)
        return

    users = load_users()
    rows = ["user_id,date,status,balance,services_count"]
    for item in history:
        ref_id = item.get('user_id')
        user_data = users.get(str(ref_id), {}) or {}
        rows.append(",".join([
            str(ref_id),
            str(item.get('date', '')),
            str(item.get('status', 'active')),
            f"{float(user_data.get('balance', 0) or 0):.0f}",
            str(len(user_data.get('services', []) or [])),
        ]))

    csv_bytes = ("\n".join(rows) + "\n").encode('utf-8-sig')
    try:
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=InputFile(io.BytesIO(csv_bytes), filename=f"referrals_{target_user_id}.csv"),
            caption=(f"📥 خروجی کاربران جذب‌شده "
                     f"{format_user_info(target_user_id, show_copyable=False)}\n"
                     f"تعداد: {len(history)}")
        )
        await query.answer("فایل ارسال شد.")
    except Exception as exc:
        logger.error(f"Failed to export referrals csv for {target_user_id}: {exc}")
        await query.answer("ارسال فایل ناموفق بود.", show_alert=True)


async def contact_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """شروع ارسال پیام مستقیم ادمین به کاربر"""
    query = update.callback_query
    context.user_data['contact_user_target'] = target_user_id
    await _safe_edit_or_send(
        query, context,
        f"✉️ پیام خود را برای کاربر {format_user_info(target_user_id, show_copyable=False)} بنویسید.\n"
        "پیام بعدی شما مستقیماً برای کاربر ارسال می‌شود.",
        InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="back_to_main_from_admin")]])
    )



# ============================================================
# --- خرید سفارشی: سرویس بی‌نهایت و سرویس حجمی با اسلایدر ---
# ============================================================

def custom_plan_price(mode: str, volume_gb: int, users: int) -> int:
    """قیمت سرویس سفارشی
    بی‌نهایت: ۴۰۰٬۰۰۰ تومان به ازای هر کاربر
    حجمی: حجم × ۲٬۰۰۰ تومان و برای هر کاربر اضافه ضریب ۱.۵ تصاعدی"""
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
    
    # ایجاد Application با روش جدید
    application = Application.builder().token(BOT_TOKEN).build()

    # ========== تغییر 1: اضافه کردن هندلرهای اصلی در ابتدا ==========
    # ثبت پروفایل تلگرام کاربران برای پنل ادمین
    application.add_handler(MessageHandler(filters.ALL, track_user_profile), group=-1)
    application.add_handler(CallbackQueryHandler(track_user_profile), group=-1)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_balance_command))  # دستور ادمین
    application.add_handler(CommandHandler("addall", addall_command))  # دستور جدید ادمین
    application.add_handler(CommandHandler("allmembers", allmembers_command))  # دستور جدید ادمین
    application.add_handler(CommandHandler("announce", announce_command))  # دستور ارسال پیام همگانی
    application.add_handler(CommandHandler("check", check_user_profile))  # دستور بررسی پروفایل کاربر
    application.add_handler(CommandHandler("myref", my_referral))  # دستور نمایش لینک رفرال
    application.add_handler(CommandHandler("tutorial", connection_tutorials_start))  # دستور آموزش
    
    # هندلر جدید برای `/check` با ریپلای
    application.add_handler(MessageHandler(
        filters.Chat(ADMIN_CHAT_IDS) & filters.TEXT & filters.REPLY,
        reply_to_ticket
    ))
    
    # مکالمه خرید سرویس جدید
    purchase_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text("🛍️ خرید سرویس"), select_server_for_purchase),
            CallbackQueryHandler(select_service_plan, pattern=r'^SELECT_SERVER_'),
        ],
        states={
            STATE_SELECT_SERVER: [
                CallbackQueryHandler(select_service_plan, pattern=r'^SELECT_SERVER_'),
                CallbackQueryHandler(prompt_for_config_name, pattern=r'^SERVICE_DETAILS_PLAN_'),
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
            MessageHandler(filters.Text("❌ لغو عملیات"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True
    )
    application.add_handler(purchase_conv_handler)

    # مکالمه شارژ کیف پول (کارت به کارت)
    wallet_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("💰 شارژ کیف پول"), wallet_start)],
        states={
            STATE_WAITING_FOR_RECEIPT: [
                MessageHandler(filters.PHOTO, wallet_receive_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_receive_receipt),
            ],
            STATE_GET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_receive_amount),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Text("❌ لغو عملیات"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True
    )
    application.add_handler(wallet_conv_handler)

    # مکالمه پشتیبانی
    support_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("📞 پشتیبانی"), support_start)],
        states={
            STATE_GET_TICKET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_receive_message),
                MessageHandler(filters.PHOTO, support_receive_message),
                MessageHandler(filters.VIDEO, support_receive_message),
                MessageHandler(filters.Document.ALL, support_receive_message),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Text("❌ لغو عملیات"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True
    )
    application.add_handler(support_conv_handler)

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
            MessageHandler(filters.Text("❌ لغو عملیات"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True,
    )
    application.add_handler(custom_buy_conv_handler)

    # سایر هندلرهای پیام
    application.add_handler(MessageHandler(filters.Text("👤 حساب من"), my_account))
    application.add_handler(MessageHandler(filters.Text("📂 سرویس‌های من"), my_services))
    application.add_handler(MessageHandler(filters.Text("🔗 لینک رفرال"), my_referral))
    application.add_handler(MessageHandler(filters.Text("📚 آموزش اتصال"), connection_tutorials_start))
    
    # هندلر برای دریافت ورودی‌های ویرایش ادمین
    application.add_handler(MessageHandler(
        filters.Chat(ADMIN_CHAT_IDS) & filters.TEXT & ~filters.COMMAND,
        handle_admin_edit_input
    ))


    # مکالمه تمدید / افزایش حجم سرویس
    renewal_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_renew_service, pattern=r'^PROMPT_RENEW_'),
        ],
        states={
            STATE_WAITING_FOR_RENEWAL_CONFIRM: [
                CallbackQueryHandler(finalize_renewal, pattern=r'^RENEW_SELECT_'),
                CallbackQueryHandler(renew_unlimited, pattern=r'^RENEW_UNLIMITED$'),
                CallbackQueryHandler(renew_open_volume, pattern=r'^RENEW_OPEN_VOLUME$'),
                CallbackQueryHandler(renew_adjust_volume, pattern=r'^RENEW_VOL_ADJ_'),
                CallbackQueryHandler(renew_confirm_volume, pattern=r'^RENEW_VOL_CONFIRM$'),
                CallbackQueryHandler(prompt_renew_service, pattern=r'^PROMPT_RENEW_'),
                CallbackQueryHandler(back_to_services, pattern=r'^back_to_services$'),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Text("❌ لغو عملیات"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
        ],
        allow_reentry=True
    )
    application.add_handler(renewal_conv_handler)

    # هندلر جامع برای دکمه‌های شیشه‌ای
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # هندلر خطا
    application.add_error_handler(error_handler)

    # شروع ربات
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()