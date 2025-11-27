# Full corrected bot file.
# Fix applied: removed SERVICE_DETAILS_PLAN_ from config_name_conv_handler entry points so
# selecting a plan shows its details first; only CONFIRM_* callbacks start the purchase conversation.
# Other fixes from previous iterations (avoid ReplyKeyboardMarkup in edit_message_text, avoid Markdown parse issues) preserved.

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
# --- متغیرهای کلیدی: تنظیمات سرورها ---
# ==========================================================

# 🌟 تنظیمات چند سرور (دست نخورده)
SERVERS_CONFIG = {
    "Server_1": {
        "display_name": "Server 🟣",
        "xui_panel_url": "xui_panel_url",
        "xui_username": "xui_panel_url",
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
ADMIN_CHAT_IDS = [6659266132, 8287371040]
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
    "Nano_Lite": {"label": "نانو لایت", "users": 2, "volume": "10 گیگ", "days": 10, "price_toman": 35000, "description": "برای استفاده سبک مثل پیام‌رسان و مرور روزانه."},
    "Pint_Lite": {"label": "پینت لایت", "users": 2, "volume": "30 گیگ", "days": 20, "price_toman": 69000, "description": "مناسب کاربران نیمه‌فعال و شبکه‌های اجتماعی."},
    "Standard": {"label": "استاندارد", "users": 2, "volume": "50 گیگ", "days": 30, "price_toman": 89000, "description": "تعادل عالی بین سرعت."},
    "Smart_Online": {"label": "اسمارت آنلاین", "users": 2, "volume": "100 گیگ", "days": 30, "price_toman": 129000, "description": "محبوب میان کاربران حرفه‌ای ایرانی."},
    "Pro_Plus": {"label": "پرو پلاس +", "users": 3, "volume": "200 گیگ", "days": 30, "price_toman": 179000, "description": "انتخاب همیشگی برای فریلنسرها و گیمرها."},
    "Family": {"label": "خانواده", "users": 3, "volume": "500 گیگ", "days": 30, "price_toman": 379000, "description": "طراحی شده برای خانواده یا گروه کاری کوچک."},
    "Titanium": {"label": "تیتانیوم", "users": 4, "volume": "700 گیگ", "days": 30, "price_toman": 419000, "description": "تعادل هوشمند بین ترافیک زیاد و کنترل کیفیت."},
    "VIP": {"label": "VIP", "users": 5, "volume": "900 گیگ", "days": 30, "price_toman": 459000, "description": "مخصوص یوزرهای دائم آنلاین و پرمصرف."},
    "VIP_Plus": {"label": "VIP_Plus", "users": 5, "volume": "1000 گیگ", "days": 30, "price_toman": 599000, "description": "سطح بالای امنیت، اختصاصی مدیران و حرفه‌ای‌ها."},
    "Organizational": {"label": "سازمانی", "users": 5, "volume": "2500 گیگ", "days": 30, "price_toman": 749000, "description": "انتخاب اقتصادی برای تیم‌ها و سازمان‌ها."},
    "Unlimited": {"label": "نامحدود + هدیه", "users": 2, "volume": "9999 گیگ", "days": 30, "price_toman": 899000, "description": "IP ثابت آلمان، سرعت اختصاصی."},
}

# --- دکمه‌های منوی اصلی ---
MAIN_MENU_KEYBOARD = [
    ["🛍️ خرید سرویس (انتخاب پلن)"],
    ["📂 سرویس‌های من", "👤 حساب من"],
    ["💰 شارژ کیف پول", "📞 پشتیبانی"],
]
MAIN_MENU_REPLY_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

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
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        logger.error(f"Error loading {USERS_FILE}. Returning empty dict.")
        return {}

def save_users(users: dict):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

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
    panel_info = SERVICES[internal_key]
    
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
        
        final_message = (
            f"✅ خرید شما با موفقیت انجام شد!\n\n"
            f"سرویس: {panel_info['label']}\n"
            f"نام کانفیگ: {config_name}\n"
            f"سرور: {server_name}\n"
            f"حجم و اعتبار: {volume_display} - {days} روز\n"
            f"هزینه: {price_toman:,.0f} تومان\n"
            f"موجودی جدید: {new_balance:,.0f} تومان\n\n"
            f"لینک اشتراک:\n{sub_link}\n\n"
            f"لینک مستقیم کانفیگ (VMess):\n{vmess_link}\n\n"
            f"توجه: لینک اشتراک را در اپلیکیشن‌های مربوطه وارد کنید. در صورت مشکل، با پشتیبانی تماس بگیرید."
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

def main() -> None:
    """شروع به کار ربات"""
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
    application.add_handler(CommandHandler("start", start))
    
    application.add_handler(wallet_conv_handler)
    application.add_handler(support_conv_handler)
    
    application.add_handler(purchase_conv_handler) 
    
    application.add_handler(config_name_conv_handler) 
    application.add_handler(renewal_conv_handler)
    
    # 🌟 هندلر دکمه لغو پرداخت (از فایل 1 اضافه شد)
    application.add_handler(CallbackQueryHandler(cancel_payment_callback, pattern="^cancel_payment_"))
    
    application.add_handler(CallbackQueryHandler(back_to_select_server, pattern="^back_to_select_server$"))
    
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