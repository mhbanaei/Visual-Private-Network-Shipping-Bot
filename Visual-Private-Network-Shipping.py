
import logging
import requests
import json
import os
import re 
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters, ApplicationBuilder
)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, Bot, error
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
# --- متغیرهای کلیدی (حتماً جایگزین کنید!) 🔑 ---
# ==========================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" 
ADMIN_CHAT_ID = 1234567890 
ZARINPAL_MERCHANT_ID = "YOUR_ZARINPAL_MERCHANT_ID_HERE" 

# --- اطلاعات اتصال به پنل x-ui (حتماً با دقت جایگزین شود!) ---
XUI_PANEL_URL = "panel_url"  
XUI_USERNAME = "your_username"
XUI_PASSWORD = "your_password"
LOGIN_PATH = "/LOGIN_PATH" 

# --- تنظیمات اینباند X-UI ---
INBOUND_ID = 1 
SERVER_ADDRESS = XUI_PANEL_URL.split("//")[1].split(":")[0] 
SERVER_PORT_SUBSCRIPTION = 2096 
SERVER_PORT_CLIENT = 8080       

# ⚠️ تنظیمات پروتکل VMESS (بر اساس Base64 شما تنظیم شده است)
PROTOCOL_SETTINGS = {
    "add": SERVER_ADDRESS,
    "port": SERVER_PORT_CLIENT,
    "id": "", 
    "aid": 0, 
    "net": "ws",
    "type": "none",
    "host": SERVER_ADDRESS,
    "path": "/ws",
    "tls": "tls",
    "sni": SERVER_ADDRESS,
    "scy": "auto",
    "v": "2"
} 

# --- تنظیمات آدرس‌دهی پنل ---
# ⚠️ این مسیر سفارشی شماست و باید برای همه API ها استفاده شود.
BASE_PATH = "/fRCZlF8gq0"  
SUBSCRIBE_PATH = "/subscribe/" 
# ==========================================================

# --- فایل‌های ذخیره‌سازی دائمی ---
PENDING_PAYMENTS_FILE = 'pending_payments.json' 
USERS_FILE = 'users.json' 

# --- تنظیمات زرین‌پال ---
ZARINPAL_WEBSERVICE = 'https://api.zarinpal.com/pg/v4/payment/request.json'
ZARINPAL_VERIFY_WEBSERVICE = 'https://api.zarinpal.com/pg/v4/payment/verify.json'
ZARINPAL_STARTPAY = 'https://www.zarinpal.com/pg/StartPay/'

# --- لیست قیمت نهایی (واحد: تومان) ---
SERVICES = {
    "Nano_Lite":      {"label": "نانو لایت", "users": 1, "volume": "10 گیگ",  "days": 30, "price_toman": 35000, "description": "برای استفاده سبک مثل پیام‌رسان و مرور روزانه."},
    "Pint_Lite":      {"label": "پینت لایت", "users": 1, "volume": "30 گیگ",  "days": 30, "price_toman": 69000, "description": "مناسب کاربران نیمه‌فعال و شبکه‌های اجتماعی."},
    "Standard":       {"label": "استاندارد", "users": 1, "volume": "50 گیگ",  "days": 30, "price_toman": 89000, "description": "تعادل عالی بین سرعت."},
    "Smart_Online":   {"label": "اسمارت آنلاین", "users": 1, "volume": "100 گیگ", "days": 30, "price_toman": 129000, "description": "محبوب میان کاربران حرفه‌ای ایرانی."},
    "Pro_Plus":       {"label": "پرو پلاس +", "users": 1, "volume": "200 گیگ", "days": 30, "price_toman": 179000, "description": "انتخاب همیشگی برای فریلنسرها و گیمرها."},
    "Family":         {"label": "خانواده", "users": 2, "volume": "500 گیگ", "days": 30, "price_toman": 379000, "description": "طراحی شده برای خانواده یا گروه کاری کوچک."},
    "Titanium":       {"label": "تیتانیوم", "users": 1, "volume": "700 گیگ", "days": 30, "price_toman": 419000, "description": "تعادل هوشمند بین ترافیک زیاد و کنترل کیفیت."},
    "VIP":            {"label": "VIP", "users": 1, "volume": "900 گیگ", "days": 30, "price_toman": 459000, "description": "مخصوص یوزرهای دائم آنلاین و پرمصرف."},
    "VIP_Plus":       {"label": "VIP_Plus", "users": 2, "volume": "1000 گیگ", "days": 30, "price_toman": 599000, "description": "سطح بالای امنیت، اختصاصی مدیران و حرفه‌ای‌ها."},
    "Organizational": {"label": "سازمانی", "users": 5, "volume": "2500 گیگ", "days": 30, "price_toman": 749000, "description": "انتخاب اقتصادی برای تیم‌ها و سازمان‌ها."},
    "Unlimited":      {"label": "نامحدود + هدیه", "users": 1, "volume": "9999 گیگ", "days": 30, "price_toman": 899000, "description": "IP ثابت آلمان، سرعت اختصاصی."},
}


# --- دکمه‌های منوی اصلی و وضعیت‌ها ---
MAIN_MENU_KEYBOARD = [
    ["🛍️ خرید سرویس (انتخاب پلن)"],
    ["📂 سرویس‌های من", "👤 حساب من"], 
    ["💰 شارژ کیف پول", "📞 پشتیبانی"],
]
MAIN_MENU_REPLY_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

# وضعیت‌های Conversation (به‌روز شده)
STATE_GET_AMOUNT = 1
STATE_GET_TICKET = 2
STATE_WAITING_FOR_CONFIG_NAME = 3
STATE_WAITING_FOR_CONFIG_NAME_CONFIRM = 4 
STATE_WAITING_FOR_RENEWAL_NAME = 5 
STATE_WAITING_FOR_RENEWAL_CONFIRM = 6 

## 🗄️ توابع مدیریت دیتابیس کاربران (JSON)
def load_users() -> dict:
    """بارگذاری اطلاعات کاربران از فایل."""
    if not os.path.exists(USERS_FILE):
        return {} 
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        logger.error(f"Error loading {USERS_FILE}. Returning empty dict.")
        return {}

def save_users(users: dict):
    """ذخیره اطلاعات کاربران در فایل."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def get_user_balance(user_id: int) -> float:
    """دریافت موجودی کیف پول کاربر. اگر کاربر وجود نداشت، آن را ثبت اولیه می‌کند."""
    users = load_users()
    str_user_id = str(user_id) 
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": []} 
        save_users(users)
        return 0.0
        
    return users[str_user_id].get("balance", 0.0)

def update_user_balance(user_id: int, amount_change: float):
    """به‌روزرسانی موجودی کیف پول کاربر (مثبت برای شارژ، منفی برای خرید). واحد ورودی تومان است."""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id not in users:
        users[str_user_id] = {"balance": 0.0, "services": []}
        
    current_balance = users[str_user_id]["balance"]
    new_balance = current_balance + amount_change
    users[str_user_id]["balance"] = new_balance
    
    save_users(users)
    return new_balance

def add_user_service(user_id: int, config_name: str, sub_link: str, uuid: str, internal_key: str):
    """ذخیره جزئیات کانفیگ خریداری شده."""
    users = load_users()
    str_user_id = str(user_id)
    
    # اطمینان از وجود بخش services
    if str_user_id not in users or 'services' not in users[str_user_id]:
         users[str_user_id] = {"balance": users.get(str_user_id, {}).get("balance", 0.0), "services": []}
    
    # بررسی عدم وجود سرویس با این نام قبلاً (در صورت تمدید، این تابع نباید فراخوانی شود)
    if not any(s['config_name'] == config_name for s in users[str_user_id]['services']):
        users[str_user_id]['services'].append({
            'config_name': config_name,
            'sub_link': sub_link,
            'uuid': uuid,
            'internal_key': internal_key, 
            'purchase_date': datetime.datetime.now().isoformat()
        })
        save_users(users)
        logger.info(f"New service added for user {user_id}: {config_name}")

def get_user_services(user_id: int) -> list:
    """دریافت لیست سرویس‌های خریداری شده کاربر."""
    users = load_users()
    return users.get(str(user_id), {}).get('services', [])

def update_user_service_key(user_id: int, config_name: str, new_key: str, new_value: any):
    """به‌روزرسانی یک فیلد خاص در سرویس کاربر (مثلا sub_link یا uuid)."""
    users = load_users()
    str_user_id = str(user_id)
    
    if str_user_id in users and 'services' in users[str_user_id]:
        for service in users[str_user_id]['services']:
            if service['config_name'] == config_name:
                service[new_key] = new_value
                save_users(users)
                return True
    return False


## 🗄️ توابع مدیریت وضعیت پرداخت در انتظار (JSON)
def load_pending_payments() -> dict:
    if not os.path.exists(PENDING_PAYMENTS_FILE): return {}
    try:
        with open(PENDING_PAYMENTS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError): return {}
def save_pending_payments(payments: dict):
    with open(PENDING_PAYMENTS_FILE, 'w') as f:
        json.dump(payments, f, indent=4)
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

## 🔐 توابع اتصال به درگاه پرداخت 
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
    req_data = {"merchant_id": ZARINPAL_MERCHANT_ID,"amount": amount_rial,"description": description,"callback_url": callback_url,}
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
    req_data = {"merchant_id": ZARINPAL_MERCHANT_ID,"authority": str(authority),"amount": int(amount_rial)}
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
            f"مبلغ **{charge_amount_toman:,.0f} تومان** به کیف پول شما اضافه شد.\n\n" 
            f"موجودی جدید: **{new_balance:,.0f}** تومان", 
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        if effective_user:
            try:
                await context.bot.send_message(
                    ADMIN_CHAT_ID,
                    f"شارژ موفق کیف پول:\nکاربر: {effective_user.first_name} (ID: {user_id})\nمبلغ: {charge_amount_toman:,.0f} تومان" 
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ پرداخت شما تایید نشد.\nلطفاً در صورت کسر وجه، کد پیگیری را به پشتیبانی ارسال کنید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )

# --- توابع API پنل x-ui ---
XUI_AUTH_COOKIE = None
async def xui_login() -> bool:
    global XUI_AUTH_COOKIE
    # آدرس لاگین باید همیشه مسیر سفارشی شما را شامل شود
    login_url = f"{XUI_PANEL_URL}{LOGIN_PATH}" 
    data = {"username": XUI_USERNAME, "password": XUI_PASSWORD}
    try:
        response = requests.post(login_url, data=data, timeout=5)
        response.raise_for_status()
        if 'session' in response.cookies:
            cookie_value = response.cookies['session']
            XUI_AUTH_COOKIE = f"session={cookie_value}"
            logger.info("X-UI login successful and cookie saved (standard).")
            return True
        if 'set-cookie' in response.headers:
            set_cookie_header = response.headers.get('set-cookie', '')
            match = re.search(r'((?:3x-ui|session|x_session|X_SESSION|panel_session)=[^;]+)', set_cookie_header, re.IGNORECASE)
            if match:
                full_cookie_string = match.group(1)
                XUI_AUTH_COOKIE = full_cookie_string.split(';')[0].strip()
                logger.info(f"X-UI login successful and cookie saved (from Set-Cookie header: {XUI_AUTH_COOKIE.split('=')[0]}).")
                return True
        if response.json().get('success') == True:
            logger.error(f"X-UI login successful but NO VALID SESSION COOKIE was found. Response Headers: {response.headers}")
            return False
        logger.error(f"X-UI login failed. Response: {response.text}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for login: {e}")
        XUI_AUTH_COOKIE = None
        return False

async def xui_get_headers() -> dict | None:
    global XUI_AUTH_COOKIE
    if XUI_AUTH_COOKIE is None:
        if not await xui_login():
            return None
    return {"Cookie": XUI_AUTH_COOKIE}

# ✅ اصلاح شده: دستور global به ابتدای تابع منتقل شد
async def xui_check_config_name_exists(config_name: str) -> bool | None:
    global XUI_AUTH_COOKIE 
    headers = await xui_get_headers()
    if headers is None: return None
    # از BASE_PATH استفاده می‌کند که اکنون شامل مسیر سفارشی است: /fRCZlF8gq0/panel/api/inbounds/list
    inbound_list_url = f"{XUI_PANEL_URL}{BASE_PATH}/panel/api/inbounds/list" 
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10)
        if response.status_code == 401:
            XUI_AUTH_COOKIE = None
            logger.warning("X-UI cookie expired. Retrying login...")
            return await xui_check_config_name_exists(config_name)
        response.raise_for_status()
        result = response.json()
        if result.get('success'):
            inbounds = result.get('obj', [])
            target_inbound = next((item for item in inbounds if item.get('id') == INBOUND_ID), None)
            if not target_inbound:
                 logger.error(f"Inbound with ID {INBOUND_ID} not found in list."); return None
            settings = json.loads(target_inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            for client in clients:
                if client.get('email') == config_name:
                    return True 
            return False
        else:
            logger.error(f"X-UI failed to get clients list: {result.get('msg')}"); return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for checking client list: {e}"); return None

# ✅ اصلاح شده: دستور global به ابتدای تابع منتقل شد و ساختار لینک سابسکریپشن اصلاح شد.
async def xui_add_client(user_id: int, volume_gb: int, config_name: str, days: int, limit_ip: int, existing_uuid: str = None, existing_sub_id: str = None) -> tuple[str | None, str | str | None]:
    """
    ایجاد یک کانفیگ VMESS جدید در x-ui با نام دلخواه، حجم، مدت اعتبار و محدودیت IP.
    پارامترهای اختیاری existing_uuid و existing_sub_id برای حفظ لینک‌های کاربر هنگام تمدید استفاده می‌شوند.
    برمی‌گرداند: (لینک کانفیگ VMESS، client_uuid، لینک سابسکریپشن)
    """
    global XUI_AUTH_COOKIE 
    headers = await xui_get_headers()
    if headers is None: return None, None, None
    # از BASE_PATH استفاده می‌کند که اکنون شامل مسیر سفارشی است: /fRCZlF8gq0/panel/api/inbounds/addClient
    add_url = f"{XUI_PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
    volume_bytes = volume_gb * 1024 * 1024 * 1024 
    
    client_uuid = existing_uuid if existing_uuid else str(uuid.uuid4())
    sub_id = existing_sub_id if existing_sub_id else config_name 

    # --- محاسبه زمان انقضا (در میلی‌ثانیه از Epoch) ---
    if days > 0:
        expiry_time_ms = int((time.time() + days * 24 * 3600) * 1000)
    else:
        expiry_time_ms = 0
    
    client_settings_object = {
        "clients": [
            {
                "id": client_uuid, # UUID حفظ شده یا جدید
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
    
    data = {"id": INBOUND_ID,"settings": json.dumps(client_settings_object)}
    
    if 'Content-Type' in headers:
        del headers['Content-Type']
        
    try:
        response = requests.post(add_url, headers=headers, data=data, timeout=10)
        if response.status_code == 401:
            XUI_AUTH_COOKIE = None
            logger.warning("X-UI cookie expired. Retrying login...")
            return await xui_add_client(user_id, volume_gb, config_name, days, limit_ip, existing_uuid, existing_sub_id) 
            
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            logger.info(f"X-UI client created for user {user_id}. UUID: {client_uuid} with name: {config_name}")
            vmess_obj = PROTOCOL_SETTINGS.copy()
            vmess_obj["id"] = client_uuid
            vmess_obj["ps"] = config_name
            vmess_json = json.dumps(vmess_obj) 
            vmess_base64 = base64.b64encode(vmess_json.encode('utf-8')).decode('utf-8')
            vmess_link = f"vmess://{vmess_base64}"
            
            # 🌟 اصلاح مشکل: حذف BASE_PATH از لینک سابسکریپشن
            sub_link = f"{XUI_PANEL_URL.split(':')[0]}://{SERVER_ADDRESS}:{SERVER_PORT_SUBSCRIPTION}{SUBSCRIBE_PATH}{sub_id}" 
            
            return vmess_link, client_uuid, sub_link

        else:
            logger.error(f"X-UI failed to add client: {result.get('msg')}. Full response: {result}")
            return None, None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for adding client: {e}")
        return None, None, None


# 🌟 تابع اصلاح شده: به‌روزرسانی سرویس (حفظ حجم مصرفی و limitIp)
# ✅ اصلاح شده: دستور global به ابتدای تابع منتقل شد
async def xui_update_client_v2(user_id: int, config_name: str, volume_add: int, days_add: int) -> tuple[bool, float, int]:
    """
    Updates the client's volume and expiry time cumulatively, and preserves usage (up/down).
    Also preserves the existing limitIp setting.
    
    Returns: (success: bool, new_total_gb: float, new_expiry_days: int)
    """
    global XUI_AUTH_COOKIE
    headers = await xui_get_headers()
    if headers is None: return False, 0.0, 0
    
    # 1. Fetch the entire inbound list (to get the full inbound object)
    inbound_list_url = f"{XUI_PANEL_URL}{BASE_PATH}/panel/api/inbounds/list"
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10)
        if response.status_code == 401:
            XUI_AUTH_COOKIE = None
            return await xui_update_client_v2(user_id, config_name, volume_add, days_add)
        response.raise_for_status() 
        result = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch inbound list for update: {e}"); return False, 0.0, 0

    if not result.get('success'):
        logger.error(f"X-UI failed to get clients list for update: {result.get('msg')}"); return False, 0.0, 0

    # Find the target inbound object
    inbounds = result.get('obj', [])
    target_inbound_obj = next((item for item in inbounds if item.get('id') == INBOUND_ID), None)
    if not target_inbound_obj:
        logger.error(f"Inbound ID {INBOUND_ID} not found for update."); return False, 0.0, 0

    # 2. Modify the target client data within the inbound object
    try:
        settings = json.loads(target_inbound_obj.get('settings', '{}'))
        clients = settings.get('clients', [])
        target_client_index = next((i for i, client in enumerate(clients) if client.get('email') == config_name), -1)
        
        if target_client_index == -1:
            logger.error(f"Client {config_name} not found in settings for update."); return False, 0.0, 0

        target_client = clients[target_client_index]

        # --- حفظ مقادیر مصرفی و Limit IP فعلی ---
        current_up = target_client.get('up', 0)
        current_down = target_client.get('down', 0)
        current_limit_ip = target_client.get('limitIp', 1) 
        
        # --- محاسبه حجم تجمعی و نهایی ---
        current_total_bytes = target_client.get('totalGB', 0)
        current_total_gb = current_total_bytes / (1024**3)
        new_total_gb = current_total_gb + volume_add
        new_total_bytes = int(new_total_gb * (1024**3))
        
        # --- محاسبه زمان انقضای تجمعی و نهایی ---
        current_expiry_ms = target_client.get('expiryTime', 0)
        current_time_seconds = time.time()
        
        if current_expiry_ms == 0:
            # اگر نامحدود بوده، از زمان حال + روزهای جدید
            new_expiry_seconds = current_time_seconds + days_add * 24 * 3600
        else:
            current_expiry_seconds = current_expiry_ms / 1000
            # اگر منقضی شده، از زمان حال + روزهای جدید. اگر فعال است، به انتهای زمان فعال اضافه می‌شود.
            start_time = max(current_time_seconds, current_expiry_seconds)
            new_expiry_seconds = start_time + days_add * 24 * 3600
            
        new_expiry_ms = int(new_expiry_seconds * 1000)
        
        # محاسبه تعداد روزهای باقیمانده برای نمایش
        new_expiry_days = int((new_expiry_seconds - current_time_seconds) / (24 * 3600))
        
        # --- اعمال تغییرات و **حفظ** مصرف و Limit IP ---
        target_client['totalGB'] = new_total_bytes
        target_client['expiryTime'] = new_expiry_ms
        target_client['up'] = current_up    # ⬅️ حفظ مصرف آپلود
        target_client['down'] = current_down # ⬅️ حفظ مصرف دانلود
        target_client['limitIp'] = current_limit_ip # ⬅️ حفظ محدودیت IP
        target_client['enable'] = True 
        
        # Re-encode settings back into the inbound object
        target_inbound_obj['settings'] = json.dumps(settings)
        
    except Exception as e:
        logger.error(f"Error while preparing inbound object for update: {e}"); return False, 0.0, 0

    # 3. Post the full, modified inbound object to the /inbounds/update API
    update_url = f"{XUI_PANEL_URL}{BASE_PATH}/panel/api/inbounds/update/{INBOUND_ID}"
    
    # ساخت دیتای payload برای API
    data_payload = {
        "id": INBOUND_ID,
        "up": target_inbound_obj.get('up', 0),
        "down": target_inbound_obj.get('down', 0),
        "total": target_inbound_obj.get('total', 0),
        "remark": target_inbound_obj.get('remark', ''),
        "enable": target_inbound_obj.get('enable', True),
        "expiryTime": target_inbound_obj.get('expiryTime', 0),
        "listen": target_inbound_obj.get('listen', ''),
        "port": target_inbound_obj.get('port', 0),
        "protocol": target_inbound_obj.get('protocol', 'vmess'),
        # Settings is the modified stringified JSON
        "settings": target_inbound_obj.get('settings', '{}'), 
        "streamSettings": target_inbound_obj.get('streamSettings', '{}'),
        "tag": target_inbound_obj.get('tag', ''),
        "sniffing": target_inbound_obj.get('sniffing', '{}'),
    }

    if 'Content-Type' in headers: del headers['Content-Type']
    
    try:
        response = requests.post(update_url, headers=headers, data=data_payload, timeout=10)
        if response.status_code == 401:
            XUI_AUTH_COOKIE = None
            return await xui_update_client_v2(user_id, config_name, volume_add, days_add) 
            
        response.raise_for_status()
        result = response.json()
        
        if result.get('success'):
            logger.info(f"X-UI client {config_name} updated successfully using /inbounds/update.")
            return True, new_total_gb, new_expiry_days
        else:
            logger.error(f"X-UI failed to update client {config_name} using /inbounds/update: {result.get('msg')}. Full response: {result}")
            return False, 0.0, 0

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for updating client: {e}")
        return False, 0.0, 0


# 🌟 اصلاح نهایی تابع: حذف فراخوانی API ناموفق /clientList
# ✅ اصلاح شده: دستور global به ابتدای تابع منتقل شد
async def xui_get_client_info_by_name(config_name: str) -> tuple[int | None, dict | None]:
    """
    پیدا کردن جزئیات کلاینت (client_data) با استفاده از نام (email) از API اصلی.
    اولین مقدار خروجی (client_id_row) همیشه None برگردانده می‌شود.
    """
    global XUI_AUTH_COOKIE
    headers = await xui_get_headers()
    if headers is None: 
        logger.error(f"Failed to get headers for fetching client info for {config_name}")
        return None, None
    
    inbound_list_url = f"{XUI_PANEL_URL}{BASE_PATH}/panel/api/inbounds/list"
    logger.info(f"DEBUG: Checking inbound list at: {inbound_list_url}") 
    
    try:
        response = requests.get(inbound_list_url, headers=headers, timeout=10)
        logger.info(f"DEBUG: inbound/list Status Code: {response.status_code}")
        
        if response.status_code == 401:
            XUI_AUTH_COOKIE = None
            logger.warning("X-UI cookie expired. Retrying login...")
            return await xui_get_client_info_by_name(config_name)
            
        response.raise_for_status() 
        result = response.json()
        
        if result.get('success'):
            inbounds = result.get('obj', [])
            target_inbound = next((item for item in inbounds if item.get('id') == INBOUND_ID), None)
            
            if not target_inbound: 
                logger.error(f"Inbound ID {INBOUND_ID} not found in the list.")
                return None, None

            settings = json.loads(target_inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            
            target_client_info = next((client for client in clients if client.get('email') == config_name), None)
            
            if target_client_info:
                logger.info(f"DEBUG: Client settings for {config_name} found in inbounds/list (via settings).")
                # تغییر: اولین عنصر (client_id_row) همیشه None است.
                return None, target_client_info 
            else:
                logger.warning(f"DEBUG: Client settings for {config_name} NOT found in inbounds/list (email mismatch or client deleted).")
                return None, None
            
        else:
            logger.error(f"X-UI failed to get clients list (inbounds/list API, success=False): {result.get('msg')}")
            return None, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to X-UI panel for getting client info: {e}"); return None, None


# --- توابع اعتبارسنجی ---
def validate_config_name(name: str) -> tuple[bool, str]:
    if not (3 <= len(name) <= 30): return False, "نام باید بین ۳ تا ۳۰ کاراکتر باشد."
    if ' ' in name: return False, "نام کاربری نباید حاوی فاصله باشد."
    if not re.match(r"^[a-zA-Z0-9_-]+$", name): return False, "فقط حروف انگلیسی (بزرگ و کوچک)، اعداد، خط زیر (_) و خط تیره (-) مجاز است."
    return True, "Valid"


## 🤖 هندلرها و Logic ربات

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    get_user_balance(user.id) 
    if context.args:
        payload = context.args[0]
        logger.info(f"START PAYLOAD received: {payload}")
        if payload.startswith("verify_"):
            authority = payload.split("verify_")[1]
            if authority and len(authority) > 10: 
                user_id, expected_amount_rial = get_pending_payment(authority) 
                if user_id == user.id and expected_amount_rial > 0:
                    message_to_edit = update.effective_message if update.effective_message else update.message
                    if message_to_edit:
                        try: await message_to_edit.delete() 
                        except error.BadRequest: pass
                    await verify_zarinpal_payment_callback(update, context, authority, expected_amount_rial)
                    return
                else:
                    await update.message.reply_text("❌ پرداخت شما در لیست پرداخت‌های در انتظار پیدا نشد یا قبلاً تأیید شده است.", reply_markup=MAIN_MENU_REPLY_MARKUP)
                    return
            logger.error("AUTHORITY IS MISSING IN PAYLOAD. Triggering manual check button.")
            keyboard = [[InlineKeyboardButton("🔍 پیگیری پرداخت ناموفق", callback_data="check_pending_payment")]]
            await update.message.reply_text(
                "⚠️ پرداخت شما در لیست در انتظار است. اگر وجه کسر شده است، لطفاً کد پیگیری را به پشتیبانی ارسال کنید.", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    await update.message.reply_html(
        f"سلام {user.mention_html()}!\nبه ربات فروش VPN خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=MAIN_MENU_REPLY_MARKUP,
    )
async def check_pending_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    await query.edit_message_text("در حال بررسی پرداخت‌های در انتظار...")
    pending_payments = load_pending_payments()
    found_payment = None
    for authority, info in pending_payments.items():
        if str(info['user_id']) == str(user_id):
            found_payment = (authority, info['amount']); break
    if found_payment:
        authority, expected_amount_rial = found_payment 
        await verify_zarinpal_payment_callback(query.message, context, authority, expected_amount_rial)
    else:
        await context.bot.send_message(user_id, "❌ هیچ پرداخت در انتظاری برای حساب شما پیدا نشد. لطفاً دوباره امتحان کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP)

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    balance = get_user_balance(update.effective_user.id)
    num_services = len(get_user_services(update.effective_user.id)) 
    
    await update.message.reply_text(
        f"👤 **حساب شما**\n\n شناسه کاربری: `{update.effective_user.id}`\n موجودی کیف پول: **{balance:,.0f}** تومان\n تعداد سرویس‌های فعال: **{num_services}**",
        parse_mode="Markdown"
    )

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = []
    for key, panel in SERVICES.items():
        callback_data = f"DETAILS_{key}"
        volume_display = panel['volume'].replace(' گیگ', 'GB')
        button_text = f"🔸 {panel['label']} ({volume_display}) - {panel['price_toman']:,.0f} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text( 
        "🇩🇪 **انتخاب پلن‌های Delta VPN (آلمان)**\n\n"
        "برای مشاهده جزئیات بیشتر هر پلن روی دکمه آن کلیک کنید:", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def back_to_select_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    keyboard = []
    for key, panel in SERVICES.items():
        callback_data = f"DETAILS_{key}"
        volume_display = panel['volume'].replace(' گیگ', 'GB')
        button_text = f"🔸 {panel['label']} ({volume_display}) - {panel['price_toman']:,.0f} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(
            "🇩🇪 **انتخاب پلن‌های Delta VPN (آلمان)**\n\n"
            "برای مشاهده جزئیات بیشتر هر پلن روی دکمه آن کلیک کنید:", 
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except error.BadRequest as e:
        logger.warning(f"Failed to edit message text on back: {e}")
        await query.answer("لیست پلن‌ها دوباره بارگذاری شد.", show_alert=False)

async def view_panel_details(update: Update, context: ContextTypes.DEFAULT_TYPE, internal_key: str) -> None:
    query = update.callback_query
    panel_info = SERVICES.get(internal_key)
    if not panel_info:
        await query.edit_message_text("❌ خطای داخلی: پلن نامعتبر.", reply_markup=MAIN_MENU_REPLY_MARKUP); return

    buy_callback_data = f"START_BUY_CONV_{internal_key}_{panel_info['price_toman']}"
    
    keyboard = [
        [InlineKeyboardButton(f"✅ تایید و خرید ({panel_info['price_toman']:,.0f} تومان)", callback_data=buy_callback_data)],
        [InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data="back_to_select_service")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    volume_display = panel_info['volume'].replace(' گیگ', 'GB')
    
    message_text = (
        f"**جزئیات پلن {panel_info['label']}**\n\n"
        f"**حجم ماهانه:** {volume_display}\n"
        f"**مدت اعتبار:** {panel_info['days']} روز\n"
        f"**👥 تعداد کاربر پیشنهادی:** {panel_info['users']} نفر\n"
        f"**💰 قیمت نهایی:** {panel_info['price_toman']:,.0f} تومان\n"
        f"--- \n"
        f"**توضیحات سرویس:**\n"
        f"{panel_info['description']}"
    )

    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ❌ تابع charge_now_handler دیگر مورد نیاز نیست و حذف شده است.
# async def charge_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
#     ...

# --- هندلر های Conversation برای خرید اولیه ---
async def prompt_for_config_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer("لطفا نام کانفیگ خود را وارد کنید...")
    try:
        data_string = query.data.split('START_BUY_CONV_')[1] 
        internal_key, price_toman_str = data_string.rsplit('_', 1) 
        price_toman = int(price_toman_str)
    except (IndexError, ValueError):
        logger.error(f"Failed to unpack START_BUY_CONV_ data: {query.data}")
        await query.edit_message_text("❌ خطای داده خرید. لطفاً دوباره تلاش کنید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_select_service")]])); return ConversationHandler.END

    user_id = query.from_user.id
    current_balance = get_user_balance(user_id)
    
    # 🌟 اصلاح مشکل ۱: هدایت کاربر به منوی شارژ در صورت کمبود موجودی
    if current_balance < price_toman:
        required = price_toman - current_balance
        
        await query.edit_message_text(
            f"⚠️ **موجودی کافی نیست!**\nموجودی فعلی شما: **{current_balance:,.0f} تومان**\nبرای خرید **{required:,.0f} تومان** دیگر نیاز دارید.\n\n"
            f"**لطفاً برای شارژ کیف پول، دکمه '💰 شارژ کیف پول' در منوی اصلی را انتخاب کنید.**",
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست پلن‌ها", callback_data="back_to_select_service")]])
        ); 
        return ConversationHandler.END # پایان مکالمه خرید

    context.user_data['purchase_data'] = {'internal_key': internal_key,'price_toman': price_toman}
    try: await query.edit_message_reply_markup(reply_markup=None) 
    except error.BadRequest: pass 
    await context.bot.send_message(
        user_id,
        "لطفاً یک نام دلخواه برای کانفیگ (Display Name) و سابسکریپشن خود وارد کنید.\n"
        "**قوانین نامگذاری:**\n"
        "• فقط حروف انگلیسی، اعداد، خط زیر (_) و خط تیره (-).\n"
        "• حداقل ۳ و حداکثر ۳۰ کاراکتر و **بدون فاصله.**",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    return STATE_WAITING_FOR_CONFIG_NAME

async def receive_config_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip(); user_id = update.effective_user.id
    if user_input == "❌ لغو عملیات": return await cancel_conversation(update, context) 
    is_valid, reason = validate_config_name(user_input)
    if not is_valid:
        await update.message.reply_text(f"❌ نام وارد شده معتبر نیست: {reason}\n\nلطفاً نام دیگری را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)); return STATE_WAITING_FOR_CONFIG_NAME
        
    await update.message.reply_text("⏳ در حال بررسی موجود بودن نام در پنل...")
    is_duplicate = await xui_check_config_name_exists(user_input)
    
    if is_duplicate is None:
        await update.message.reply_text("⚠️ خطای اتصال به پنل VPN. لطفاً لحظاتی بعد دوباره امتحان کنید.", reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)); return STATE_WAITING_FOR_CONFIG_NAME
    elif is_duplicate is True:
        await update.message.reply_text(f"❌ نام **`{user_input}`** قبلاً در سیستم ثبت شده است.\n\nلطفاً یک نام کاملاً جدید وارد کنید:", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)); return STATE_WAITING_FOR_CONFIG_NAME
        
    context.user_data['config_name'] = user_input
    purchase_data = context.user_data['purchase_data']
    internal_key = purchase_data['internal_key']
    price_toman = purchase_data['price_toman']
    panel_info = SERVICES[internal_key]
    
    message_text = (
        f"**تایید نهایی خرید**\n\n"
        f"سرویس انتخابی: **{panel_info['label']}** ({panel_info['volume'].replace(' گیگ', 'GB')})\n"
        f"مدت اعتبار: **{panel_info['days']} روز**\n"
        f"تعداد کاربر: **{panel_info['users']} نفر**\n"
        f"هزینه: **{price_toman:,.0f} تومان**\n"
        f"**نام کانفیگ شما:** `{user_input}`\n\n"
        "آیا اطلاعات بالا را تأیید می‌کنید؟"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ بله، خرید نهایی شود", callback_data="CONFIRM_FINAL_PURCHASE")],
        [InlineKeyboardButton("✏️ تغییر نام کانفیگ", callback_data="RE_ENTER_NAME")]
    ]
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STATE_WAITING_FOR_CONFIG_NAME_CONFIRM

async def finalize_purchase_with_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer("در حال نهایی کردن خرید...")
    user_id = query.from_user.id
    try: temp_msg = await context.bot.send_message(user_id, "...", reply_markup=MAIN_MENU_REPLY_MARKUP); await context.bot.delete_message(user_id, temp_msg.message_id)
    except Exception: pass
    
    purchase_data = context.user_data.get('purchase_data')
    config_name = context.user_data.get('config_name')
    if not purchase_data or not config_name:
        await context.bot.send_message(user_id, "❌ خطای داده: فرآیند خرید ناقص است. لطفاً از ابتدا شروع کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP); return ConversationHandler.END

    internal_key = purchase_data['internal_key']; price_toman = purchase_data['price_toman']
    panel_info = SERVICES.get(internal_key)
    
    try: volume_str = panel_info['volume'].replace(' گیگ', ''); volume_gb = int(volume_str)
    except ValueError: volume_gb = 9999 

    limit_ip = panel_info['users']; days = panel_info['days']
    current_balance = get_user_balance(user_id)
    
    if current_balance >= price_toman:
        update_user_balance(user_id, -price_toman)
        panel_name = f"{panel_info['label']} ({panel_info['volume'].replace(' گیگ', 'GB')})"
        
        # ⚠️ در خرید اولیه، existing_uuid و existing_sub_id برابر با None هستند.
        config_link, client_uuid, sub_link = await xui_add_client(user_id, volume_gb, config_name, days, limit_ip)
        
        if config_link and client_uuid and sub_link:
            
            # 🌟 ذخیره اطلاعات سرویس در دیتابیس کاربر
            add_user_service(user_id, config_name, sub_link, client_uuid, internal_key)

            summary_text = (
                f"✅ **خرید موفق**\n\n"
                f"سرویس: **{panel_name}**\n"
                f"نام کانفیگ: **`{config_name}`**\n" 
                f"مدت اعتبار: **{days} روز**\n"
                f"تعداد کاربر: **{limit_ip} نفر**\n"
                f"هزینه: **{price_toman:,.0f} تومان** (از کیف پول کسر شد)\n\n"
                f"موجودی جدید: **{get_user_balance(user_id):,.0f}** تومان"
            )
            vmess_text = (f"**🔗 لینک کانفیگ (VMESS Base64):**\n```\n{config_link}\n```")
            sub_text = (
                f"**🔄 لینک سابسکریپشن (توصیه شده):**\n"
                f"```\n{sub_link}\n```\n\n"
                f"این لینک را در نرم‌افزارهای خود اضافه کنید."
            )
            
            await context.bot.send_message( user_id, summary_text, parse_mode="Markdown")
            await context.bot.send_message( user_id, vmess_text, parse_mode="Markdown")
            await context.bot.send_message( 
                user_id, sub_text, parse_mode="Markdown", reply_markup=MAIN_MENU_REPLY_MARKUP
            )
            
            try: await query.message.delete()
            except Exception: pass
            
            try: await context.bot.send_message( ADMIN_CHAT_ID, f"**خرید جدید (با نام دلخواه):**\nکاربر: {query.from_user.first_name} (ID: {user_id})\nسرویس: {panel_name}\nنام: {config_name}\nمدت: {days} روز\nتعداد کاربر: {limit_ip}")
            except Exception as e: logger.error(f"Failed to notify admin: {e}")
            
            context.user_data.pop('purchase_data', None)
            context.user_data.pop('config_name', None)

        else:
            # برگشت وجه در صورت خطا
            update_user_balance(user_id, price_toman)
            await context.bot.send_message(
                user_id,
                f"❌ **خطا در ساخت کانفیگ**\n\n"
                f"لطفاً بلافاصله با پشتیبانی تماس بگیرید و شناسه کاربری خود (`{user_id}`) را اعلام کنید. مبلغ خرید به کیف پول شما بازگشت داده شد.",
                parse_mode="Markdown",
                reply_markup=MAIN_MENU_REPLY_MARKUP
            )
            try: await query.message.delete()
            except Exception: pass
    else:
        # اگر موجودی ناکافی بود (نباید به اینجا برسیم اگر flow قبلی درست باشد، اما برای اطمینان)
        await context.bot.send_message(user_id, f"⚠️ **موجودی کافی نیست!**\nلطفاً کیف پول خود را شارژ کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP)
        try: await query.message.delete()
        except Exception: pass

    return ConversationHandler.END

async def re_enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    try: await query.message.delete()
    except Exception: pass
    await context.bot.send_message(
        user_id,
        "لطفاً نام دلخواه جدید خود را برای کانفیگ وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    return STATE_WAITING_FOR_CONFIG_NAME

# --- هندلر های سرویس‌های من و تمدید ---

async def my_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لیست سرویس‌های خریداری شده کاربر به همراه لینک سابسکریپشن و دکمه تمدید."""
    
    user_id = update.effective_user.id
    user_services = get_user_services(user_id)
    
    if not user_services:
        await update.message.reply_text("⛔️ شما در حال حاضر هیچ سرویس فعالی خریداری نکرده‌اید.", 
                                        reply_markup=MAIN_MENU_REPLY_MARKUP)
        return

    message_text = "**📂 سرویس‌های فعال شما:**\n\n"
    keyboard = []

    for idx, service in enumerate(user_services):
        config_name = service['config_name']
        sub_link = service['sub_link']
        
        # client_id_row اکنون همیشه None است.
        client_id_row, client_data = await xui_get_client_info_by_name(config_name)
        
        status_text = f"**`{config_name}`** (⚠️ خطای اتصال به پنل یا پیدا نشدن سرویس)"
        
        # تنها به وجود client_data برای نمایش جزئیات سرویس تکیه می‌کنیم.
        if client_data:
            total_bytes = client_data.get('totalGB', 0)
            used_bytes = client_data.get('up', 0) + client_data.get('down', 0)
            expiry_ms = client_data.get('expiryTime', 0)
            
            total_gb = total_bytes / (1024**3)
            used_gb = used_bytes / (1024**3)
            remaining_gb = max(0, total_gb - used_gb)

            # تبدیل زمان انقضا
            if expiry_ms == 0:
                expiry_display = "نامحدود"
            else:
                expiry_date = datetime.datetime.fromtimestamp(expiry_ms / 1000)
                expiry_display = expiry_date.strftime("%Y/%m/%d")
            
            
            # محاسبه وضعیت
            if total_gb <= 0: 
                volume_status = "حجم: نامحدود"
            else:
                volume_status = f"حجم: {remaining_gb:,.2f} GB باقی مانده (مصرف: {used_gb:,.2f} GB)"
            
            status_text = (
                f"**`{config_name}`**\n"
                f"  🔸 {volume_status}\n"
                f"  📅 اعتبار تا: {expiry_display}"
            )

        message_text += f"{status_text}\n"
        message_text += f"   🔗 لینک سابسکریپشن:\n`{sub_link}`\n"
        message_text += f"   ➖ ➖ ➖ ➖ ➖\n"
        
        # دکمه تمدید
        keyboard.append([InlineKeyboardButton(f"🔁 تمدید سرویس {config_name}", callback_data=f"PROMPT_RENEW_{config_name}")])
    
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def prompt_renew_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry Point برای تمدید سرویس: ذخیره نام و انتقال به مرحله انتخاب پلن."""
    
    query = update.callback_query
    await query.answer()
    
    config_name = query.data.split("PROMPT_RENEW_")[1]
    
    # چک کردن وضعیت سرویس در X-UI
    # client_id_row اکنون همیشه None است.
    client_id_row, client_data = await xui_get_client_info_by_name(config_name)
    
    # ⚠️ اصلاح شرط خطا: تنها client_data را چک می‌کنیم.
    if not client_data:
        await context.bot.send_message(
            query.from_user.id,
            f"❌ سرویس **`{config_name}`** در پنل X-UI پیدا نشد. لطفاً با پشتیبانی تماس بگیرید.",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        return ConversationHandler.END
        
    # ذخیره داده‌ها
    context.user_data['renewal_target_name'] = config_name
    # client_data شامل uuid، totalGB، expiryTime و... است.
    context.user_data['renewal_target_client_data'] = client_data 

    # نمایش پلن‌های موجود برای تمدید
    keyboard = []
    
    for key, panel in SERVICES.items():
        callback_data = f"RENEW_SELECT_{key}_{panel['price_toman']}"
        volume_display = panel['volume'].replace(' گیگ', 'GB')
        button_text = f"🔸 {panel['label']} (+{panel['days']} روز، +{volume_display}) - {panel['price_toman']:,.0f} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            f"**🔁 انتخاب پلن تمدید برای سرویس `{config_name}`**\n\n"
            f"لطفاً یکی از پلن‌های زیر را انتخاب کنید. حجم و زمان آن به سرویس فعلی شما **اضافه** خواهد شد.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except error.BadRequest:
        await context.bot.send_message(
             query.from_user.id,
             f"**🔁 انتخاب پلن تمدید برای سرویس `{config_name}`**\n\n"
            f"لطفاً یکی از پلن‌های زیر را انتخاب کنید. حجم و زمان آن به سرویس فعلی شما **اضافه** خواهد شد.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    return ConversationHandler.END 


async def finalize_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نهایی کردن تمدید: کسر موجودی و به‌روزرسانی سرویس موجود."""
    
    query = update.callback_query
    await query.answer("در حال نهایی کردن تمدید...")
    
    user_id = query.from_user.id
    
    # 1. بازیابی داده‌ها 
    try:
        data_string = query.data.split('RENEW_SELECT_')[1] 
        internal_key, price_toman_str = data_string.rsplit('_', 1) 
        price_toman = int(price_toman_str)
        
        config_name = context.user_data.get('renewal_target_name')
        
    except (IndexError, ValueError, AttributeError):
        logger.error(f"Failed to unpack RENEW_SELECT_ data or renewal_target is missing.")
        await context.bot.send_message(user_id, "❌ خطای داده تمدید. لطفاً دوباره تلاش کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP); return

    panel_info = SERVICES.get(internal_key)
    if not panel_info or not config_name:
        await context.bot.send_message(user_id, "❌ خطای داخلی: اطلاعات پلن/سرویس نامعتبر است.", reply_markup=MAIN_MENU_REPLY_MARKUP); return

    # 2. چک کردن موجودی 
    current_balance = get_user_balance(user_id)
    if current_balance < price_toman:
        required = price_toman - current_balance
        
        await query.edit_message_text(
            f"⚠️ **موجودی کافی نیست!**\nموجودی فعلی شما: **{current_balance:,.0f} تومان**\nبرای تمدید **{required:,.0f} تومان** دیگر نیاز دارید.\n\n"
            f"**لطفاً برای شارژ کیف پول، دکمه '💰 شارژ کیف پول' در منوی اصلی را انتخاب کنید.**",
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به سرویس‌های من", callback_data="back_to_services")]])
        ); 
        
        # پاکسازی context
        context.user_data.pop('renewal_target_name', None)
        context.user_data.pop('renewal_target_client_data', None)
        return

    # 3. محاسبه مقادیر افزایشی
    try: volume_add = int(panel_info['volume'].replace(' گیگ', ''))
    except ValueError: volume_add = 9999
    days_add = panel_info['days']
    
    # 4. کسر موجودی
    update_user_balance(user_id, -price_toman)
    
    # 5. به‌روزرسانی سرویس در پنل (حفظ مصرف و Limit IP)
    update_success, new_total_gb, new_expiry_days = await xui_update_client_v2(user_id, config_name, volume_add, days_add)
    
    panel_name = f"{panel_info['label']} ({panel_info['volume'].replace(' گیگ', 'GB')})"

    if update_success:
        
        new_balance = get_user_balance(user_id)
        
        message_text = (
            f"✅ **تمدید سرویس موفق**\n\n"
            f"سرویس تمدید شده: **`{config_name}`**\n"
            f"پلن تمدید: **{panel_name}**\n"
            f"مقادیر اضافه شده:\n"
            f"  🔸 **{volume_add} GB حجم**\n"
            f"  📅 **{days_add} روز اعتبار**\n"
            f"هزینه: **{price_toman:,.0f} تومان** (از کیف پول کسر شد)\n\n"
            f"سرویس شما اکنون دارای:\n"
            f"  ⚡️ **{new_total_gb:,.2f} GB حجم** و **حداکثر {new_expiry_days} روز اعتبار** است.\n"
            f"موجودی جدید: **{new_balance:,.0f}** تومان"
        )
        
        # FIX: ابتدا پیام موجود را ویرایش کرده و کیبورد شیشه‌ای را حذف می‌کنیم.
        await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=None) 
        
        # سپس پیام جدیدی را با کیبورد اصلی (ReplyKeyboardMarkup) می‌فرستیم.
        await context.bot.send_message(
            user_id, 
            "شما به منوی اصلی بازگشتید.", 
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
        
        # اخطار به ادمین 
        try:
            await context.bot.send_message( 
                ADMIN_CHAT_ID,
                f"**تمدید سرویس (با حفظ مصرف):**\nکاربر: {query.from_user.first_name} (ID: {user_id})\nسرویس: `{config_name}`\nپلن تمدید: {panel_name}\nاضافه شد: {volume_add} GB و {days_add} روز (Usage: PRESERVED)"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin about renewal: {e}")

    else:
        # اگر به‌روزرسانی ناموفق بود، برگشت وجه
        update_user_balance(user_id, price_toman)
        await context.bot.send_message(
            user_id,
            f"❌ **خطا در به‌روزرسانی کانفیگ**\n\n"
            f"لطفاً بلافاصله با پشتیبانی تماس بگیرید. مبلغ تمدید به کیف پول شما بازگشت داده شد. (شناسه خطا: Update Fail)",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )

    # پاکسازی context
    context.user_data.pop('renewal_target_name', None)
    context.user_data.pop('renewal_target_client_data', None)
    
    return ConversationHandler.END


# --- هندلر های کلی ---

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query; data = query.data
    
    if data.startswith("DETAILS_"):
        await query.answer()
        internal_key = data.split("DETAILS_")[1]
        await view_panel_details(update, context, internal_key)
        
    elif data.startswith("START_BUY_CONV_"):
        pass 
            
    elif data == "back_to_select_service":
        await query.answer()
        await back_to_select_service_handler(update, context)

    elif data == "check_pending_payment":
        await check_pending_payment_callback(update, context)

    elif data == "back_to_services":
        await query.answer()
        await context.bot.send_message(query.from_user.id, "در حال بارگذاری سرویس‌های من...")
        await my_services(update, context) # فراخوانی مستقیم my_services برای نمایش لیست

    return ConversationHandler.END


async def wallet_charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_user_balance(update.effective_user.id) 
    await update.message.reply_text(
        "لطفاً مبلغ مورد نظر خود را برای شارژ کیف پول وارد کنید (حداقل ۱,۰۰۰ تومان):",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    return STATE_GET_AMOUNT

async def wallet_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "❌ لغو عملیات": return await cancel_conversation(update, context)
    try:
        amount_toman = int(update.message.text)
        if amount_toman < 1000: await update.message.reply_text("مبلغ وارد شده باید حداقل ۱,۰۰۰ تومان باشد."); return STATE_GET_AMOUNT
    except ValueError:
        await update.message.reply_text("لطفاً مبلغ را به صورت عددی وارد کنید."); return STATE_GET_AMOUNT

    user_id = update.effective_user.id
    amount_rial = amount_toman * 10
    payment_url, authority = await zarinpal_create_request(user_id, amount_rial, f"شارژ کیف پول کاربر {user_id}", context)
    
    if not payment_url:
        await update.message.reply_text("❌ متأسفانه در اتصال به درگاه پرداخت خطایی رخ داد. لطفراً بعداً تلاش کنید.", reply_markup=MAIN_MENU_REPLY_MARKUP); return ConversationHandler.END

    keyboard = [[InlineKeyboardButton("🔗 پرداخت آنلاین (اتصال به زرین‌پال)", url=payment_url)]]
    
    await update.message.reply_text(
        f"✅ لینک پرداخت برای مبلغ **{amount_toman:,.0f} تومان** ساخته شد.\n\n روی دکمه کلیک کرده و پرداخت را کامل کنید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "لطفاً پیام خود را برای ارسال به پشتیبانی تایپ کنید.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو عملیات"]], resize_keyboard=True)
    )
    return STATE_GET_TICKET

async def support_get_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user; message = update.message
    forwarded_message = await context.bot.forward_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=user.id,
        message_id=message.message_id
    )
    if 'support_tickets' not in context.bot_data: context.bot_data['support_tickets'] = {}
    context.bot_data['support_tickets'][forwarded_message.message_id] = user.id

    await update.message.reply_text("✅ پیام شما با موفقیت برای پشتیبانی ارسال شد.", reply_markup=MAIN_MENU_REPLY_MARKUP)
    return ConversationHandler.END

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_CHAT_ID: return
    replied_message = update.message.reply_to_message
    if not replied_message: return
    support_tickets = context.bot_data.get('support_tickets', {})
    original_user_id = support_tickets.get(replied_message.message_id)
    if original_user_id:
        try:
            await context.bot.send_message(chat_id=original_user_id, text=f"**پاسخ پشتیبانی:**\n\n{update.message.text}", parse_mode="Markdown")
            await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
            support_tickets.pop(replied_message.message_id)
        except Exception as e:
            logger.error(f"Failed to send admin reply to {original_user_id}: {e}")
            await update.message.reply_text(f"خطا در ارسال پیام به کاربر: {e}")

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('purchase_data', None)
    context.user_data.pop('config_name', None)
    context.user_data.pop('renewal_target_name', None)
    context.user_data.pop('renewal_target_client_data', None)
    
    if update.message:
        await update.message.reply_text("عملیات لغو شد. به منوی اصلی بازگشتید.", reply_markup=MAIN_MENU_REPLY_MARKUP)
    elif update.callback_query:
        await context.bot.send_message(update.effective_user.id, "عملیات لغو شد. به منوی اصلی بازگشتید.", reply_markup=MAIN_MENU_REPLY_MARKUP)
        
    return ConversationHandler.END 


## 🚀 تابع اصلی و راه‌اندازی ربات

def main() -> None: 
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    PROXIES = {}
    if PROXIES:
        application.bot._request.kwargs['proxies'] = PROXIES 
    
    wallet_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^💰 شارژ کیف پول$"), wallet_charge_start)],
        states={
            STATE_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.Regex(r"^❌ لغو عملیات$"), wallet_get_amount)],
        },
        # ❌ لغو عملیات اکنون در این فال بک‌ها کار خواهد کرد
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation), MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_conversation)],
    )

    config_name_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_for_config_name, pattern="^START_BUY_CONV_")],
        states={
            STATE_WAITING_FOR_CONFIG_NAME: [MessageHandler(filters.TEXT & ~filters.Regex(r"^❌ لغو عملیات$"), receive_config_name)],
            STATE_WAITING_FOR_CONFIG_NAME_CONFIRM: [
                CallbackQueryHandler(finalize_purchase_with_name, pattern="^CONFIRM_FINAL_PURCHASE$"),
                CallbackQueryHandler(re_enter_name, pattern="^RE_ENTER_NAME$"),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation)],
    )
    
    # 🌟 هندلر مکالمه برای تمدید سرویس
    renewal_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_renew_service, pattern="^PROMPT_RENEW_")],
        states={}, 
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )
    
    support_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📞 پشتیبانی$"), support_start)],
        states={
            STATE_GET_TICKET: [MessageHandler(filters.TEXT & ~filters.Regex(r"^❌ لغو عملیات$"), support_get_ticket)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation), MessageHandler(filters.Regex(r"^❌ لغو عملیات$"), cancel_conversation), MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_conversation)],
    )


    application.add_handler(CommandHandler("start", start))
    application.add_handler(wallet_conv_handler)
    application.add_handler(support_conv_handler)
    application.add_handler(config_name_conv_handler)
    application.add_handler(renewal_conv_handler) 
    
    # هندلر دکمه‌های منوی اصلی
    application.add_handler(MessageHandler(filters.Regex(r"^🛍️ خرید سرویس \(انتخاب پلن\)$"), select_service))
    application.add_handler(MessageHandler(filters.Regex(r"^👤 حساب من$"), my_account))
    application.add_handler(MessageHandler(filters.Regex(r"^📂 سرویس‌های من$"), my_services)) 
    
    # هندلر جامع دکمه‌های شیشه‌ای (charge_now حذف شد و back_to_services اضافه شد)
    application.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^DETAILS_|back_to_select_service|check_pending_payment|back_to_services"))
    
    # اضافه کردن هندلر finalize_renewal به صورت جداگانه
    application.add_handler(CallbackQueryHandler(finalize_renewal, pattern="^RENEW_SELECT_"))
    
    application.add_handler(
        MessageHandler(
            filters.Chat(chat_id=ADMIN_CHAT_ID) & filters.REPLY & filters.TEXT, 
            admin_reply_handler
        )
    )

    print("Bot is running...")
    
    application.run_polling(poll_interval=5, drop_pending_updates=True)


if __name__ == "__main__":
    main()