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

import logging
import requests
import json
import os
import re 
import asyncio
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Bot, error
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
SERVERS_CONFIG = {
    "Server_1": {
        "display_name": "Server 🟣",
        "xui_panel_url": "xui_panel_url",
        "xui_username": "xui_username",
        "xui_password": "xui_password",
        "login_path": "/login_path/login",
        "inbound_id": 1,
        "server_address": "server_address",
        "server_port_subscription": 2096,
        "server_port_client": 8080,
        "base_path": "/base_path",
        "subscribe_path": "/subscribe/",
        "active": 1,   # 🌟 1 = قابل خرید | 0 = ظرفیت پر
        "tamdid": 1    # 🌟 1 = قابل تمدید | 0 = تمدید غیرفعال
    }
}

# تنظیمات اولیه 
BOT_TOKEN = "BOT_TOKEN"
ADMIN_CHAT_IDS = [6659266132, 8210063313]
CARD_NUMBER = "6219861830494810"  # شماره کارت برای واریز

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
    "Nano_Lite": {"label": "نانو لایت", "users": 2, "volume": "10 گیگ", "days": 10, "price_toman": 35000, "description": "برای استفاده سبک مثل پیام‌رسان و مرور روزانه.", "renewable": True},
    "Pint_Lite": {"label": "پینت لایت", "users": 2, "volume": "30 گیگ", "days": 20, "price_toman": 69000, "description": "مناسب کاربران نیمه‌فعال و شبکه‌های اجتماعی.", "renewable": True},
    "Standard": {"label": "استاندارد", "users": 2, "volume": "50 گیگ", "days": 30, "price_toman": 89000, "description": "تعادل عالی بین سرعت.", "renewable": True},
    "Smart_Online": {"label": "اسمارت آنلاین", "users": 2, "volume": "100 گیگ", "days": 30, "price_toman": 129000, "description": "محبوب میان کاربران حرفه‌ای ایرانی.", "renewable": True},
    "Pro_Plus": {"label": "پرو پلاس +", "users": 3, "volume": "200 گیگ", "days": 30, "price_toman": 179000, "description": "انتخاب همیشگی برای فریلنسرها و گیمرها.", "renewable": True},
    "Family": {"label": "خانواده", "users": 3, "volume": "500 گیگ", "days": 30, "price_toman": 379000, "description": "طراحی شده برای خانواده یا گروه کاری کوچک.", "renewable": True},
    "Titanium": {"label": "تیتانیوم", "users": 4, "volume": "700 گیگ", "days": 30, "price_toman": 419000, "description": "تعادل هوشمند بین ترافیک زیاد و کنترل کیفیت.", "renewable": True},
    "VIP": {"label": "VIP", "users": 5, "volume": "900 گیگ", "days": 30, "price_toman": 459000, "description": "مخصوص یوزرهای دائم آنلاین و پرمصرف.", "renewable": True},
    "VIP_Plus": {"label": "VIP_Plus", "users": 5, "volume": "1000 گیگ", "days": 30, "price_toman": 599000, "description": "سطح بالای امنیت، اختصاصی مدیران و حرفه‌ای‌ها.", "renewable": True},
    "Organizational": {"label": "سازمانی", "users": 5, "volume": "2500 گیگ", "days": 30, "price_toman": 749000, "description": "انتخاب اقتصادی برای تیم‌ها و سازمان‌ها.", "renewable": True},
    "Unlimited": {"label": "نامحدود + هدیه", "users": 2, "volume": "9999 گیگ", "days": 30, "price_toman": 899000, "description": "IP ثابت آلمان، سرعت اختصاصی.", "renewable": True},
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
# --- محتوای آموزشی برنامه‌های مختلف ---
# ============================================================

CONNECTION_TUTORIALS = {
    # Hiddify - Android
    "hiddify_android": {
        "title": "📱 آموزش اتصال با Hiddify (Android)",
        "steps": [
            "1. ابتدا برنامه Hiddify را از فروشگاه Google Play دانلود و نصب کنید.",
            "1.1 https://play.google.com/store/apps/details?id=app.hiddify.com&hl=en",
            "2. برنامه را باز کرده و روی علامت ➕ در  صفحه کلیک کنید.",
            "3. گزینه 'Add from Clipboard' یا 'وارد کردن از کلیپ‌برد' را انتخاب کنید.",
            "4. لینک اشتراک خود را از ربات کپی کرده و در این قسمت paste کنید.",
            "5. روی 'Add' کلیک کنید تا کانفیگ اضافه شود.",
            "6. حالا روی دکمه روشن/خاموش (🔘) در کنار کانفیگ خود کلیک کنید تا اتصال برقرار شود.",
            "",
            "📌 نکات مهم:",
            "• این برنامه به صورت خودکار بهترین پروتکل را انتخاب می‌کند.",
            "• برای قطع اتصال، دوباره روی دکمه روشن/خاموش کلیک کنید."
        ]
    },
    
    # Hiddify - iOS
    "hiddify_ios": {
        "title": "📱 آموزش اتصال با Hiddify (iOS)",
        "steps": [
            "1. ابتدا برنامه Hiddify را از فروشگاه App Store دانلود و نصب کنید.",
            "1.1 https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532",
            "2. برنامه را باز کرده و روی علامت ➕ در  صفحه کلیک کنید.",
            "3. گزینه 'Add from Clipboard' یا 'وارد کردن از کلیپ‌برد' را انتخاب کنید.",
            "4. لینک اشتراک خود را از ربات کپی کرده و در این قسمت paste کنید.",
            "5. روی 'Add' کلیک کنید تا کانفیگ اضافه شود.",
            "6. حالا روی دکمه روشن/خاموش (🔘) در کنار کانفیگ خود کلیک کنید تا اتصال برقرار شود.",
            "",
            "📌 نکات مهم:",
            "• این برنامه کاملاً رایگان است.",
            "",
            "• این برنامه به صورت خودکار بهترین پروتکل را انتخاب می‌کند.",
            "• برای قطع اتصال، دوباره روی دکمه روشن/خاموش کلیک کنید."
        ]
    },
    
    # V2rayNG - Android
    "v2rayng_android": {
        "title": "📱 آموزش اتصال با V2rayNG (Android)",
        "steps": [
            "1. برنامه V2rayNG را از لینک زیر دانلود کنید:",
            "https://github.com/2dust/v2rayNG/releases/download/1.10.26/v2rayNG_1.10.26_universal.apk",
            "(آخرین نسخه APK را دانلود و نصب کنید)",
            "",
            "2. برنامه را باز کرده و روی علامت ➕ در بالا سمت راست کلیک کنید.",
            "3. لینک اشتراک خود را از ربات کپی کرده ",
            "4. گزینه 'Import config from clipboard' را انتخاب کنید.",
            "5. حالا کانفیگ شما در لیست ظاهر می‌شود. روی آن کلیک کنید.",
            "6. در صفحه باز شده، دکمه V را در پایین صفحه فشار دهید تا اتصال برقرار شود.",
            "7. برای قطع اتصال، دوباره روی دکمه V کلیک کنید.",
            "",
            "📌 نکات مهم:",
            "• این برنامه کاملاً رایگان است.",
            "",
            "⚠️ توجه: اگر کانفیگ کار نکرد، مطمئن شوید تاریخ دستگاه شما درست باشد."
        ]
    },
    
    # V2Box - iOS
    "v2box_ios": {
        "title": "📱 آموزش اتصال با V2Box (iOS)",
        "steps": [
            "1. برنامه V2Box را از App Store دانلود و نصب کنید.",
            "1.1 https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690",
            "",
            "2. لینک اشتراک خود را از ربات کپی کرده",
            "3. برنامه را باز کرده و روی علامت ➕ در بالا سمت راست کلیک کنید.",
            "4. گزینه 'Import from Clipboard' را انتخاب کنید.",
            "5. لینک اشتراک خود را از ربات کپی کرده و در این قسمت paste کنید.",
            "6. حالا کانفیگ شما در لیست ظاهر می‌شود. روی آن کلیک کنید تا انتخاب شود.",
            "7. روی دکمه 'Connect' در پایین صفحه کلیک کنید.",
            "8. اگر پیام 'VPN Configuration' ظاهر شد، روی 'Allow' کلیک کنید.",
            "9. حالا باید به اینترنت متصل شوید.",
            "",
            "📌 نکات مهم:",
            "• این برنامه کاملاً رایگان است.",
            "",
            "⚠️ مشکل احتمالی: اگر اتصال برقرار نشد، برنامه را یکبار بسته و مجدداً باز کنید."
        ]
    },
    
    # V2rayN - Windows
    "v2rayn_windows": {
        "title": "💻 آموزش اتصال با V2rayN (Windows)",
        "steps": [
            "1. برنامه V2rayN را از لینک زیر دانلود کنید:",
            "https://github.com/2dust/v2rayN/releases/download/7.16.6/v2rayN-windows-64.zip",
            "(فایل v2rayN.zip را دانلود و extract کنید)",
            "",
            "2. وارد پوشه ای که فایل رو دانلود کردید بشید و فایل رو Extract کنید",
            "3. برنامه رو بازکنید و پیش نیاز های آن را نصب نمایید",
            "4. لینک اشتراک خود را از ربات کپی کرده",
            "5. بر روی برنامه کلیک کنید و با استفاده کلید واژه CTRL+V کانفیگ خود را انتقال بدید",
            "6. برای متصل شدن از بخش System Proxy  که در پایین برنامه قرار دارد set System Proxy را انتخاب کنید",
            "7. برای قطع کردن سرویس از بخش System Proxy  که در پایین برنامه قرار دارد Clear System Proxy را انتخاب کنید",
            "",
        ]
    },
    
    # Hiddify - Windows
    "hiddify_windows": {
        "title": "💻 آموزش اتصال با Hiddify (Windows)",
        "steps": [
            "1. برنامه Hiddify برای Windows را از لینک زیر دانلود کنید:",
            "https://github.com/hiddify/hiddify-next/releases/latest/download/Hiddify-Windows-Setup-x64.exe",
            "(فایل Hiddify.Windows.Setup.exe را دانلود کنید)",
            "",
            "2. برنامه را باز کرده و روی علامت ➕ در  صفحه کلیک کنید.",
            "3. گزینه 'Add from Clipboard' یا 'وارد کردن از کلیپ‌برد' را انتخاب کنید.",
            "4. لینک اشتراک خود را از ربات کپی کرده و در این قسمت paste کنید.",
            "5. روی 'Add' کلیک کنید تا کانفیگ اضافه شود.",
            "6. حالا روی دکمه روشن/خاموش (🔘) در کنار کانفیگ خود کلیک کنید تا اتصال برقرار شود.",
            "",
            "⚠️ نکته: برای عملکرد بهتر، آنتی‌ویروس را موقتاً غیرفعال کنید."
        ]
    },
    
    # آموزش کلی برای همه
    "general_tips": {
        "title": "📌 نکات کلی و عیب‌یابی",
        "steps": [
            "🔹 **مشکلات رایج و راه‌حل‌ها:**",
            "",
            "1. **کانفیگ کار نمی‌کند:**",
            "   • تاریخ و ساعت دستگاه خود را بررسی کنید (باید دقیق باشد).",
            "   • کانفیگ منقضی نشده باشد.",
            "   • حجم کانفیگ تمام نشده باشد.",
            "",
            "2. **سرعت کم است:**",
            #"   • سرور دیگری را امتحان کنید.",
            "   • موقعیت جغرافیایی خود را بررسی کنید.",
            "   • از شبکه اینترنت دیگری تست کنید.",
            "",
            "3. **قطع و وصل می‌شود:**",
            "   • تنظیمات Battery Optimization را برای برنامه غیرفعال کنید.",
            "   • در Android: Settings > Apps > [App Name] > Battery > Unrestricted",
            "   • از شبکه پایدارتری استفاده کنید.",
            "",
            "4. **برنامه crash می‌کند:**",
            "   • برنامه را حذف و مجدداً نصب کنید.",
            "   • از آخرین نسخه برنامه استفاده کنید.",
            "   • حافظه دستگاه را خالی کنید.",
            "",
            "5. **ایرانسل/همراه اول فیلتر کرده:**",
            "   • با پشتیبانی تماس بگیرید.",
            "",
            "🔹 **پشتیبانی:**",
            "اگر مشکلتان حل نشد، از دکمه '📞 پشتیبانی' استفاده کنید."
        ]
    }
}

# ============================================================
# --- ساختار منوی آموزش ---
# ============================================================

TUTORIAL_CATEGORIES = {
    "android": {
        "title": "📱 آموزش برای Android",
        "apps": [
            {"name": "Hiddify (توصیه شده)", "key": "hiddify_android"},
            {"name": "V2rayNG", "key": "v2rayng_android"},
        ]
    },
    "ios": {
        "title": "📱 آموزش برای iOS",
        "apps": [
            {"name": "Hiddify (توصیه شده)", "key": "hiddify_ios"},
            {"name": "V2Box", "key": "v2box_ios"},
        ]
    },
    "windows": {
        "title": "💻 آموزش برای Windows",
        "apps": [
            {"name": "Hiddify (توصیه شده)", "key": "hiddify_windows"},
            {"name": "V2rayN", "key": "v2rayn_windows"},
        ]
    },
    "tips": {
        "title": "📌 نکات کلی و عیب‌یابی",
        "apps": [
            {"name": "مشکلات رایج و راه‌حل", "key": "general_tips"},
        ]
    }
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
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        logger.error(f"Error loading {USERS_FILE}. Returning empty dict.")
        return {}

def save_users(users: dict):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

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
    
    if sub_link:
        message += f"🔗 **لینک اشتراک:** `{sub_link[:50]}`\n"
    
    message += f"🕒 **زمان {action}:** {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n"
    
    # ارسال به تمام ادمین‌ها
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="Markdown"
            )
            
            # اگر vmess_link داریم، آن را هم در یک پیام جداگانه ارسال کنیم
            if vmess_link and len(vmess_link) < 4000:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        #text=f"🔗 **لینک VMess برای {config_name}:**\n\n`{vmess_link}`",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to send VMess link to admin {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to send service log to admin {admin_id}: {e}")
            
# ============================================================
# --- توابع مدیریت تاریخچه تراکنش‌ها ---
# ============================================================

def load_transaction_history() -> dict:
    """بارگذاری تاریخچه تراکنش‌ها"""
    if not os.path.exists(TRANSACTION_HISTORY_FILE):
        return {}
    try:
        with open(TRANSACTION_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_transaction_history(history: dict):
    """ذخیره تاریخچه تراکنش‌ها"""
    with open(TRANSACTION_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

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
    """بارگذاری لیست کاربرانی که از تست رایگان استفاده کرده‌اند"""
    if not os.path.exists(FREE_TRIAL_USERS_FILE):
        return {}
    try:
        with open(FREE_TRIAL_USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_free_trial_users(users: dict):
    """ذخیره لیست کاربران تست رایگان"""
    with open(FREE_TRIAL_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

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
    """بارگذاری لیست رسیدهای در انتظار تأیید"""
    if not os.path.exists(PENDING_RECEIPTS_FILE):
        return {}
    try:
        with open(PENDING_RECEIPTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_pending_receipts(receipts: dict):
    """ذخیره لیست رسیدهای در انتظار تأیید"""
    with open(PENDING_RECEIPTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(receipts, f, indent=4, ensure_ascii=False)

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
    """بارگذاری اطلاعات رفرال"""
    if not os.path.exists(REFERRAL_DATA_FILE):
        return {"referrals": {}, "earnings_history": {}}
    try:
        with open(REFERRAL_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {"referrals": {}, "earnings_history": {}}

def save_referral_data(data: dict):
    """ذخیره اطلاعات رفرال"""
    with open(REFERRAL_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

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
    
    # محاسبه پورسانت
    referral_earning = (amount_toman * REFERRAL_PERCENT) / 100
    
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
        "percent": REFERRAL_PERCENT,
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
    message_text += f"• درصد رفرال: {REFERRAL_PERCENT}%\n\n"
    
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
# --- توابع API پنل X-UI (سیستم چند سروره) ---
# ============================================================

async def xui_login(server_key: str) -> bool:
    """ورود به پنل X-UI برای سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    server_config = SERVERS_CONFIG[server_key]
    login_url = f"{server_config['xui_panel_url']}{server_config['login_path']}"
    data = {"username": server_config['xui_username'], "password": server_config['xui_password']}
    
    try:
        # verify=False برای نادیده گرفتن خطاهای SSL در سرورهای محلی X-UI
        response = requests.post(login_url, data=data, timeout=5, verify=False)
        response.raise_for_status()
        
        if 'session' in response.cookies:
            cookie_value = response.cookies['session']
            XUI_AUTH_COOKIES[server_key] = f"session={cookie_value}"
            logger.info(f"X-UI login successful for {server_key}")
            return True
        
        if 'set-cookie' in response.headers:
            set_cookie_header = response.headers.get('set-cookie', '')
            match = re.search(r'((?:3x-ui|session|x_session|X_SESSION|panel_session)=[^;]+)', set_cookie_header, re.IGNORECASE)
            if match:
                full_cookie_string = match.group(1)
                XUI_AUTH_COOKIES[server_key] = full_cookie_string.split(';')[0].strip()
                logger.info(f"X-UI login successful for {server_key} (from Set-Cookie header)")
                return True
        
        if response.json().get('success') == True:
            logger.error(f"X-UI login successful for {server_key} but NO VALID SESSION COOKIE was found.")
            return False
        
        logger.error(f"X-UI login failed for {server_key}. Response: {response.text}")
        return False
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for {server_key}: {e}")
        XUI_AUTH_COOKIES[server_key] = None
        return False

async def xui_get_headers(server_key: str) -> dict | None:
    """دریافت Headers اتصال برای سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    if XUI_AUTH_COOKIES.get(server_key) is None:
        if not await xui_login(server_key):
            return None
    
    return {"Cookie": XUI_AUTH_COOKIES[server_key]}

async def xui_check_config_name_exists(server_key: str, config_name: str) -> bool | None:
    """بررسی تکراری نبودن نام در سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    headers = await xui_get_headers(server_key)
    if headers is None: return None
    
    server_config = SERVERS_CONFIG[server_key]
    inbound_id = server_config['inbound_id']
    base_path = server_config['base_path']
    xui_panel_url = server_config['xui_panel_url']
    
    inbound_list_url = f"{xui_panel_url}{base_path}/panel/api/inbounds/list"
    
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10, verify=False)
        if response.status_code == 401:
            XUI_AUTH_COOKIES[server_key] = None
            logger.warning(f"X-UI cookie expired for {server_key}. Retrying login...")
            return await xui_check_config_name_exists(server_key, config_name)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            inbounds = result.get('obj', [])
            target_inbound = next((item for item in inbounds if item.get('id') == inbound_id), None)
            if not target_inbound:
                logger.error(f"Inbound with ID {inbound_id} not found in {server_key}")
                return None
            
            settings = json.loads(target_inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            for client in clients:
                if client.get('email') == config_name:
                    return True
            return False
        else:
            logger.error(f"X-UI failed to get clients list for {server_key}: {result.get('msg')}")
            return None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for {server_key}: {e}")
        return None

async def xui_add_client(server_key: str, user_id: int, volume_gb: int, config_name: str, days: int, limit_ip: int, existing_uuid: str = None, existing_sub_id: str = None) -> tuple[str | None, str | None, str | None]:
    """ایجاد کلاینت در سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    headers = await xui_get_headers(server_key)
    if headers is None: return None, None, None
    
    server_config = SERVERS_CONFIG[server_key]
    inbound_id = server_config['inbound_id']
    base_path = server_config['base_path']
    xui_panel_url = server_config['xui_panel_url']
    server_address = server_config['server_address']
    server_port_subscription = server_config['server_port_subscription']
    subscribe_path = server_config['subscribe_path']
    
    add_url = f"{xui_panel_url}{base_path}/panel/api/inbounds/addClient"
    volume_bytes = volume_gb * 1024 * 1024 * 1024
    
    client_uuid = existing_uuid if existing_uuid else str(uuid.uuid4())
    sub_id = existing_sub_id if existing_sub_id else config_name

    if days > 0:
        expiry_time_ms = int((time.time() + days * 24 * 3600) * 1000)
    else:
        expiry_time_ms = 0
    
    client_settings_object = {
        "clients": [
            {
                "id": client_uuid,
                "flow": "",
                "email": config_name,
                "limitIp": limit_ip,
                "totalGB": volume_bytes,
                "expiryTime": expiry_time_ms,
                "enable": True,
                "tgId": "",
                "subId": sub_id
            }
        ]
    }
    
    data = {"id": inbound_id, "settings": json.dumps(client_settings_object)}
    
    if 'Content-Type' in headers:
        del headers['Content-Type']
    
    try:
        response = requests.post(add_url, headers=headers, data=data, timeout=10, verify=False)
        if response.status_code == 401:
            XUI_AUTH_COOKIES[server_key] = None
            logger.warning(f"X-UI cookie expired for {server_key}. Retrying login...")
            return await xui_add_client(server_key, user_id, volume_gb, config_name, days, limit_ip, existing_uuid, existing_sub_id)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            logger.info(f"X-UI client created on {server_key} for user {user_id}. UUID: {client_uuid} with name: {config_name}")
            
            vmess_obj = get_protocol_settings(server_key).copy()
            vmess_obj["id"] = client_uuid
            vmess_obj["ps"] = config_name
            vmess_json = json.dumps(vmess_obj)
            vmess_base64 = base64.b64encode(vmess_json.encode('utf-8')).decode('utf-8')
            vmess_link = f"vmess://{vmess_base64}"
            
            sub_link = f"{xui_panel_url.split(':')[0]}://{server_address}:{server_port_subscription}{subscribe_path}{sub_id}"
            
            return vmess_link, client_uuid, sub_link
        else:
            logger.error(f"X-UI failed to add client on {server_key}: {result.get('msg')}. Full response: {result}")
            return None, None, None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for {server_key}: {e}")
        return None, None, None

async def xui_update_client_v2(server_key: str, user_id: int, config_name: str, volume_add: int, days_add: int) -> tuple[bool, float, int]:
    """به‌روزرسانی کلاینت در سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    headers = await xui_get_headers(server_key)
    if headers is None: return False, 0.0, 0
    
    server_config = SERVERS_CONFIG[server_key]
    inbound_id = server_config['inbound_id']
    base_path = server_config['base_path']
    xui_panel_url = server_config['xui_panel_url']
    
    inbound_list_url = f"{xui_panel_url}{base_path}/panel/api/inbounds/list"
    
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10, verify=False)
        if response.status_code == 401:
            XUI_AUTH_COOKIES[server_key] = None
            return await xui_update_client_v2(server_key, user_id, config_name, volume_add, days_add)
        
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch inbound list for update on {server_key}: {e}")
        return False, 0.0, 0

    if not result.get('success'):
        logger.error(f"X-UI failed to get clients list for update on {server_key}: {result.get('msg')}")
        return False, 0.0, 0

    inbounds = result.get('obj', [])
    target_inbound_obj = next((item for item in inbounds if item.get('id') == inbound_id), None)
    if not target_inbound_obj:
        logger.error(f"Inbound ID {inbound_id} not found for update on {server_key}")
        return False, 0.0, 0

    try:
        settings = json.loads(target_inbound_obj.get('settings', '{}'))
        clients = settings.get('clients', [])
        
        target_client_index = next((i for i, client in enumerate(clients) if client.get('email') == config_name), -1)
        if target_client_index == -1:
            logger.error(f"Client {config_name} not found on {server_key} for update")
            return False, 0.0, 0
        
        target_client = clients[target_client_index]
        
        current_up = target_client.get('up', 0)
        current_down = target_client.get('down', 0)
        current_limit_ip = target_client.get('limitIp', 1)

        current_total_bytes = target_client.get('totalGB', 0)
        current_total_gb = current_total_bytes / (1024**3)
        new_total_gb = current_total_gb + volume_add
        new_total_bytes = int(new_total_gb * (1024**3))

        current_expiry_ms = target_client.get('expiryTime', 0)
        current_time_seconds = time.time()

        if current_expiry_ms == 0:
            new_expiry_seconds = current_time_seconds + days_add * 24 * 3600
        else:
            current_expiry_seconds = current_expiry_ms / 1000
            start_time = max(current_time_seconds, current_expiry_seconds)
            new_expiry_seconds = start_time + days_add * 24 * 3600
        
        new_expiry_ms = int(new_expiry_seconds * 1000)
        new_expiry_days = int((new_expiry_seconds - current_time_seconds) / (24 * 3600))
        
        target_client['totalGB'] = new_total_bytes
        target_client['expiryTime'] = new_expiry_ms
        target_client['up'] = current_up
        target_client['down'] = current_down
        target_client['limitIp'] = current_limit_ip
        
        clients[target_client_index] = target_client
        settings['clients'] = clients
        target_inbound_obj['settings'] = json.dumps(settings)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error on {server_key}: {e}")
        return False, 0.0, 0
    except Exception as e:
        logger.error(f"General error during client update on {server_key}: {e}")
        return False, 0.0, 0
    
    update_url = f"{xui_panel_url}{base_path}/panel/api/inbounds/update/{inbound_id}"
    
    data = {
        "remark": target_inbound_obj['remark'],
        "enable": target_inbound_obj['enable'],
        "protocol": target_inbound_obj['protocol'],
        "port": target_inbound_obj['port'],
        "expiryTime": target_inbound_obj['expiryTime'],
        "total": target_inbound_obj['total'],
        "settings": target_inbound_obj['settings'],
        "streamSettings": target_inbound_obj['streamSettings'],
        "sniffing": target_inbound_obj['sniffing']
    }
    
    if 'Content-Type' in headers:
        del headers['Content-Type']
        
    try:
        response = requests.post(update_url, headers=headers, data=data, timeout=10, verify=False)
        if response.status_code == 401:
            XUI_AUTH_COOKIES[server_key] = None
            return await xui_update_client_v2(server_key, user_id, config_name, volume_add, days_add)
            
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            logger.info(f"X-UI client {config_name} updated on {server_key}. Added {volume_add} GB, {days_add} days.")
            return True, new_total_gb, new_expiry_days
        else:
            logger.error(f"X-UI failed to update client on {server_key}: {result.get('msg')}")
            return False, 0.0, 0
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for update on {server_key}: {e}")
        return False, 0.0, 0

async def xui_get_client_info_by_name(server_key: str, config_name: str) -> tuple[int | None, dict | None]:
    """دریافت اطلاعات و ایندکس کلاینت با نام (ایمیل) در سرور مشخص"""
    global XUI_AUTH_COOKIES
    
    headers = await xui_get_headers(server_key)
    if headers is None: return None, None
    
    server_config = SERVERS_CONFIG[server_key]
    inbound_id = server_config['inbound_id']
    base_path = server_config['base_path']
    xui_panel_url = server_config['xui_panel_url']
    
    inbound_list_url = f"{xui_panel_url}{base_path}/panel/api/inbounds/list"
    
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10, verify=False)
        if response.status_code == 401:
            XUI_AUTH_COOKIES[server_key] = None
            return await xui_get_client_info_by_name(server_key, config_name)
        
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            inbounds = result.get('obj', [])
            target_inbound = next((item for item in inbounds if item.get('id') == inbound_id), None)
            if not target_inbound:
                logger.error(f"Inbound with ID {inbound_id} not found on {server_key}")
                return None, None
            
            settings = json.loads(target_inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            target_client_index = next((i for i, client in enumerate(clients) if client.get('email') == config_name), -1)
            
            if target_client_index != -1:
                return target_client_index, clients[target_client_index]
            
            logger.warning(f"Client {config_name} not found on {server_key}")
            return None, None
        else:
            logger.error(f"X-UI failed to get clients list for {server_key}: {result.get('msg')}")
            return None, None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel on {server_key}: {e}")
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
        if update and update.effective_user and update.effective_user.id:
            user_id = update.effective_user.id
            if isinstance(context.error, error.Conflict):
                return
            
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ متأسفانه خطایی در عملکرد ربات رخ داد. لطفاً دوباره امتحان کنید یا با پشتیبانی تماس بگیرید.",
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
        
        error_message = f"**❌ خطای جدی در ربات!**\n\n`{context.error}`\n\nUpdate: `{update}`"
        for admin_id in ADMIN_CHAT_IDS:
            await context.bot.send_message(admin_id, error_message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Failed to handle error or notify user/admin: {e}")

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش موجودی کیف پول و مشخصات کاربر با اطلاعات رفرال"""
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)
    num_services = len(get_user_services(user_id))
    
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
        f"🔹 **درآمد رفرال:** **{referral_earnings:,.0f}** تومان\n\n"
        f"**نکته:** برای شارژ، از دکمه «💰 شارژ کیف پول» در منوی اصلی استفاده کنید.\n"
        f"برای دریافت لینک رفرال خود، روی دکمه «🔗 لینک رفرال» کلیک کنید."
    )
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
    )

async def my_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لینک رفرال کاربر"""
    user_id = update.effective_user.id
    
    # ساخت لینک رفرال
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # دریافت اطلاعات رفرال
    referral_info = get_user_referral_info(user_id)
    referral_by = referral_info.get("referral_by")
    referral_earnings = referral_info.get("referral_earnings", 0.0)
    referrals_count = referral_info.get("referrals_count", 0)
    
    # دریافت لیست کاربران رفرال شده
    referral_history = get_referral_history(user_id)
    
    message_text = (
        f"**🔗 لینک رفرال شما**\n\n"
        f"لینک اختصاصی شما:\n`{ref_link}`\n\n"
        f"📊 آمار رفرال شما:**\n"
        f"🔸 تعداد کاربران جذب شده: **{referrals_count}** نفر\n"
        f"🔸 مجموع درآمد رفرال: **{referral_earnings:,.0f}** تومان\n"
        f"🔸 درصد رفرال: **{REFERRAL_PERCENT}%**\n"
    )
    
    # نمایش رفرال دهنده (اگر دارد)
    if referral_by:
        message_text += f"🔸 رفرال دهنده شما: {format_user_info(referral_by, show_copyable=False)}\n"
    
    message_text += "\n**📝 نحوه کار:**\n"
    message_text += "1. لینک بالا را برای دوستان خود ارسال کنید\n"
    message_text += "2. دوستان شما با کلیک روی لینک وارد ربات می‌شوند\n"
    message_text += "3. رفرال شما برای همیشه در پروفایلشان ثبت می‌شود\n"
    message_text += f"4. از هر شارژی که انجام دهند، **{REFERRAL_PERCENT}%** به حساب شما اضافه می‌شود\n\n"
    
    message_text += "\n**⚠️ توجه:**\n"
    message_text += f"• رفرال هر کاربر فقط یک بار و در اولین ورود ثبت می‌شود\n"
    message_text += f"• مبلغ شارژ باید حداقل **{REFERRAL_MIN_AMOUNT:,}** تومان باشد تا رفرال محاسبه شود\n"
    message_text += f"• رفرال پس از تأیید رسید شارژ توسط ادمین به حساب شما واریز می‌شود"
    
    message_text += "\n\n**‼️ نکته:**\n"
    message_text += f"• در صورتی که مبلغ درآمد شما از رفرال بیش از 500,000 تومان شود\n"
    message_text += f"• میتوانید با ثبت درخواست در پشتیبانی مبلغ درآمد خود را به کارت بانکی خود واریز کنید\n"
    
    # ایجاد دکمه‌های اشتراک‌گذاری
    keyboard = [
        [InlineKeyboardButton("📲 اشتراک‌گذاری لینک", url=f"tg://msg_url?url={ref_link}&text=لینک%20رفرال%20من")],
        [InlineKeyboardButton("📊 تاریخچه درآمد رفرال", callback_data=f"REFERRAL_HISTORY_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
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
# --- بخش آموزش اتصال ---
# ============================================================

async def connection_tutorials_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع بخش آموزش اتصال"""
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
    panel_info = SERVICES[internal_key]
    
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
        
        panel_info = SERVICES[internal_key]
        volume_gb = int(panel_info['volume'].split(' ')[0])
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
        
        final_message = (
            f"✅ خرید شما با موفقیت انجام شد!\n\n"
            f"سرویس: {panel_info['label']}\n"
            f"نام کانفیگ: {config_name}\n"
            f"سرور: {server_name}\n"
            f"حجم و اعتبار: {volume_display} - {days} روز\n"
            f"هزینه: {price_text}\n"
        )
        
        if price_toman > 0:
            final_message += f"موجودی جدید: {new_balance:,.0f} تومان\n\n"
        else:
            final_message += f"\n"
        
        final_message += (
            f"🔗 لینک اشتراک:\n{sub_link}\n\n"
            f"🔗 لینک مستقیم کانفیگ (VMess):\n{vmess_link}\n\n"
            f"توجه: لینک اشتراک را در اپلیکیشن‌های مربوطه وارد کنید. در صورت مشکل، با پشتیبانی تماس بگیرید."
        )
        
        # پیام اضافی برای سرویس تست رایگان
        if internal_key == "FREE_TRIAL":
            final_message += f"\n\n⚠️ توجه: این سرویس تست رایگان فقط 1 روز اعتبار دارد و قابل تمدید نیست."
        
        try:
            await query.edit_message_text(final_message)
            await send_main_menu(user_id, context)
        except Exception:
            await context.bot.send_message(user_id, final_message)
            await send_main_menu(user_id, context)
            
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
    
    message_text = f"📝 لینک اشتراک سرویس {config_name}:\n\n{sub_link}"
    
    await context.bot.send_message(user_id, message_text)
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
    
    # اطلاع به ادمین
    user_link = format_user_info(user_id)
    await update.message.reply_text(
        f"✅ موجودی کاربر {user_link} به میزان {amount:,.0f} تومان افزایش یافت.\n\n💰 موجودی جدید: {new_balance:,.0f} تومان",
        parse_mode="Markdown"
    )
    
    # اطلاع به کاربر
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💰 موجودی کیف پول شما توسط ادمین به میزان {amount:,.0f} تومان افزایش یافت.\n\n💳 موجودی جدید: {new_balance:,.0f} تومان",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send balance update notification")
        await update.message.reply_text(f"⚠️ موجودی افزایش یافت اما کاربر {user_link} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
        await update.message.reply_text(f"⚠️ کاربر {user_link} پیدا نشد یا خطا در ارسال پیام.", parse_mode="Markdown")

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
    
    await my_referral(update, context)

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
    await query.answer("❌ این دکمه هنوز پیاده‌سازی نشده است.", show_alert=True)

def main() -> None:
    """شروع به کار ربات"""
    # ایجاد Application با روش جدید
    application = Application.builder().token(BOT_TOKEN).build()

    # ========== تغییر 1: اضافه کردن هندلرهای اصلی در ابتدا ==========
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_balance_command))  # دستور ادمین
    application.add_handler(CommandHandler("announce", announce_command))  # دستور ارسال پیام همگانی
    application.add_handler(CommandHandler("check", check_user_profile))  # دستور بررسی پروفایل کاربر
    application.add_handler(CommandHandler("myref", my_referral))  # دستور نمایش لینک رفرال
    application.add_handler(CommandHandler("tutorial", connection_tutorials_start))  # دستور آموزش
    
    # هندلر جدید برای `/check` با ریپلای
    application.add_handler(MessageHandler(
        filters.Chat(ADMIN_CHAT_IDS) & filters.TEXT & filters.REPLY,
        reply_to_ticket
    ))
    
    # ========== تغییر 2: هندلرهای دکمه‌های منوی اصلی قبل از مکالمات ==========
    application.add_handler(MessageHandler(filters.Regex(r"^👤 حساب من$"), my_account))
    application.add_handler(MessageHandler(filters.Regex(r"^📂 سرویس‌های من$"), my_services))
    application.add_handler(MessageHandler(filters.Regex(r"^🔗 لینک رفرال$"), my_referral))  # هندلر دکمه لینک رفرال
    application.add_handler(MessageHandler(filters.Regex(r"^📚 آموزش اتصال$"), connection_tutorials_start))  # هندلر دکمه آموزش اتصال
    
    # ========== تغییر 3: سپس هندلرهای مکالمه ==========
    # مکالمه جدید شارژ کیف پول (کارت به کارت)
    wallet_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 شارژ کیف پول$"), wallet_start)],
        states={
            STATE_WAITING_FOR_RECEIPT: [
                MessageHandler(filters.PHOTO, wallet_receive_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_receive_receipt)
            ],
            STATE_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_receive_amount)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), 
            MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)
        ],
    )

    support_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📞 پشتیبانی$"), support_start)],
        states={
            STATE_GET_TICKET: [
                MessageHandler(
                    filters.ALL & ~filters.COMMAND & filters.ChatType.PRIVATE, 
                    support_receive_message
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), 
            MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)
        ],
    )

    purchase_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🛍️ خرید سرویس$"), select_server_for_purchase)],
        states={
            STATE_SELECT_SERVER: [
                CallbackQueryHandler(select_service_plan, pattern="^SELECT_SERVER_"),
                MessageHandler(filters.Regex(r"^🛍️ خرید سرویس$"), select_server_for_purchase),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation), 
            MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation),
        ],
    )

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
    
    # ========== تغییر 4: اضافه کردن مکالمات بعد از هندلرهای اصلی ==========
    application.add_handler(wallet_conv_handler)
    application.add_handler(support_conv_handler)
    application.add_handler(purchase_conv_handler) 
    application.add_handler(config_name_conv_handler) 
    application.add_handler(renewal_conv_handler)
    
    # هندلر یکپارچه برای دریافت ورودی‌های ویرایش ادمین
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(ADMIN_CHAT_IDS) & ~filters.COMMAND,
        handle_admin_edit_input
    ))
    
    # هندلرهای دکمه‌های شیشه‌ای
    application.add_handler(CallbackQueryHandler(back_to_select_server, pattern="^back_to_select_server$"))
    application.add_handler(CallbackQueryHandler(back_to_tutorial_categories, pattern="^back_to_tutorial_categories$"))
    
    # هندلر جامع برای تمام دکمه‌های شیشه‌ای
    application.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^SERVICE_DETAILS_|SHOW_SUB_LINK_|back_to_main_from_services|back_to_services|OPEN_MY_SERVICES|approve_receipt_|reject_receipt_|REFERRAL_HISTORY_|back_to_referral_link|TUTORIAL_CAT_|TUTORIAL_APP_|back_to_main_from_tutorial|add_balance_|copy_user_id_|refresh_profile_|transaction_details_|service_details_|edit_user_|edit_balance_|edit_referral_|edit_notes_|investigate_user_|register_user_|full_referral_list_|referral_earnings_history_|close_profile|transaction_page_info|service_page_info|referral_page_info|earnings_page_info"))
    
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