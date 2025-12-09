# Full corrected bot file with card-to-card payment system
# Changes applied: 
# 1. Removed Zarinpal gateway completely
# 2. Added card-to-card payment with receipt upload
# 3. Added admin command /add for manual balance update
# 4. Added FREE_TRIAL service (1GB, 1 day, 1 user) with one-time purchase limit
# 5. Added check to prevent renewal of free trial service
# 6. Moved free trial to services list (not separate button in main menu)

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
        "xui_username": "xui_username",
        "xui_password": "xui_password",
        "login_path": "/login_path/login",
        "inbound_id": 1,
        "server_address": "server_address",
        "server_port_subscription": 2096,
        "server_port_client": 8080,
        "base_path": "/login_path",
        "subscribe_path": "/subscribe/",
        "active": 1,   # 🌟 1 = قابل خرید | 0 = ظرفیت پر
        "tamdid": 1    # 🌟 1 = قابل تمدید | 0 = تمدید غیرفعال
    }
}

# تنظیمات اولیه 
BOT_TOKEN = "BOT_TOKEN"
ADMIN_CHAT_IDS = [6659266132, 8287371040]
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

# --- فایل‌های ذخیره‌سازی دائمی ---
PENDING_PAYMENTS_FILE = 'pending_payments.json'
USERS_FILE = 'users.json'
PENDING_RECEIPTS_FILE = 'pending_receipts.json'  # فایل جدید برای رسیدهای در انتظار تأیید
FREE_TRIAL_USERS_FILE = 'free_trial_users.json'  # فایل جدید برای رصد کاربران تست رایگان

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
# --- توابع مدیریت کاربران تست رایگان ---
# ============================================================

def load_free_trial_users() -> dict:
    """بارگذاری لیست کاربرانی که از تست رایگان استفاده کرده‌اند"""
    if not os.path.exists(FREE_TRIAL_USERS_FILE):
        return {}
    try:
        with open(FREE_TRIAL_USERS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_free_trial_users(users: dict):
    """ذخیره لیست کاربران تست رایگان"""
    with open(FREE_TRIAL_USERS_FILE, 'w') as f:
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
        with open(PENDING_RECEIPTS_FILE, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

def save_pending_receipts(receipts: dict):
    """ذخیره لیست رسیدهای در انتظار تأیید"""
    with open(PENDING_RECEIPTS_FILE, 'w') as f:
        json.dump(receipts, f, indent=4, ensure_ascii=False)

def add_pending_receipt(user_id: int, amount_toman: int, receipt_file_id: str, message_to_admin_id: int = None):
    """افزودن رسید جدید به لیست در انتظار"""
    receipts = load_pending_receipts()
    receipt_id = str(int(time.time() * 1000))  # شناسه یکتا بر اساس زمان
    
    receipts[receipt_id] = {
        'user_id': user_id,
        'amount_toman': amount_toman,
        'receipt_file_id': receipt_file_id,
        'message_to_admin_id': message_to_admin_id,
        'timestamp': datetime.datetime.now().isoformat(),
        'status': 'pending'  # pending, approved, rejected
    }
    
    save_pending_receipts(receipts)
    return receipt_id

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
            receipts[receipt_id]['admin_id'] = admin_id
            receipts[receipt_id]['processed_at'] = datetime.datetime.now().isoformat()
        save_pending_receipts(receipts)
        return True
    return False

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
    """هندلر دستور /start"""
    user = update.effective_user
    
    # پیام خوش‌آمدگویی
    await update.message.reply_text(
        f"سلام {user.first_name}،\nلطفاً یک گزینه را از منوی زیر انتخاب کنید:",
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
    else:
        new_balance = get_user_balance(user_id)
    
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
            
        try:
            for admin_id in ADMIN_CHAT_IDS:
                await context.bot.send_message(
                    admin_id,
                    f"خرید جدید:\nکاربر: {user_id}\nکانفیگ: {config_name}\nسرور: {server_name}\nپلن: {internal_key}"
                )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
            
    else:
        # بازگشت وجه فقط برای سرویس‌های پولی
        if price_toman > 0:
            update_user_balance(user_id, price_toman)
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
        f"`Mohammad Hossein Banaei`\n\n"
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
    
    # ارسال رسید به ادمین‌ها برای تأیید
    user = update.effective_user
    admin_message = (
        f"📩 درخواست شارژ کیف پول\n\n"
        f"👤 کاربر: {user.first_name} {user.last_name or ''}\n"
        f"🆔 ID: {user.id}\n"
        f"💰 مبلغ: {amount_toman:,.0f} تومان\n\n"
        f"لطفاً رسید را بررسی و تأیید کنید:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ تأیید رسید", callback_data=f"approve_receipt_{user.id}_{amount_toman}"),
            InlineKeyboardButton("❌ رد رسید", callback_data=f"reject_receipt_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_to_admin = None
    for admin_id in ADMIN_CHAT_IDS:
        try:
            # ارسال عکس رسید
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=receipt_file_id,
                caption=admin_message,
                reply_markup=reply_markup
            )
            # ذخیره اطلاعات پیام برای ادمین
            message_to_admin = admin_id
        except Exception as e:
            logger.error(f"Failed to send receipt to admin {admin_id}: {e}")
    
    # ذخیره رسید در لیست انتظار
    receipt_id = add_pending_receipt(user_id, amount_toman, receipt_file_id, message_to_admin)
    
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
    """هندلر تأیید رسید توسط ادمین با مدیریت خطای کاربر مسدود شده"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ شما دسترسی لازم برای این عمل را ندارید.")
        return
    
    data_parts = query.data.split('_')
    user_id = int(data_parts[2])
    amount_toman = int(data_parts[3])
    
    # افزایش موجودی کاربر
    new_balance = update_user_balance(user_id, amount_toman)
    
    # به‌روزرسانی وضعیت رسید
    receipt_id = None
    receipts = load_pending_receipts()
    for rid, receipt in receipts.items():
        if receipt['user_id'] == user_id and receipt['amount_toman'] == amount_toman and receipt['status'] == 'pending':
            receipt_id = rid
            break
    
    if receipt_id:
        update_receipt_status(receipt_id, 'approved', query.from_user.id)
    
    # اطلاع به کاربر
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ رسید شما تأیید شد!\n\n💰 مبلغ {amount_toman:,.0f} تومان به کیف پول شما اضافه شد.\n\n💳 موجودی جدید: {new_balance:,.0f} تومان",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send receipt approval notification")
        # اطلاع به ادمین که کاربر ربات را بلاک کرده
        await query.message.reply_text(f"⚠️ رسید تأیید شد اما کاربر {user_id} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
    
    # به‌روزرسانی پیام ادمین
    try:
        await query.edit_message_caption(
            caption=f"✅ رسید تأیید شد\n\n👤 کاربر: {user_id}\n💰 مبلغ: {amount_toman:,.0f} تومان\n✅ توسط: {query.from_user.first_name}"
        )
    except Exception as e:
        logger.error(f"Failed to edit admin message: {e}")

async def reject_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر رد رسید توسط ادمین با مدیریت خطای کاربر مسدود شده"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ شما دسترسی لازم برای این عمل را ندارید.")
        return
    
    data_parts = query.data.split('_')
    user_id = int(data_parts[2])
    
    # به‌روزرسانی وضعیت رسید
    receipt_id = None
    receipts = load_pending_receipts()
    for rid, receipt in receipts.items():
        if receipt['user_id'] == user_id and receipt['status'] == 'pending':
            receipt_id = rid
            break
    
    if receipt_id:
        update_receipt_status(receipt_id, 'rejected', query.from_user.id)
    
    # اطلاع به کاربر
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ متأسفانه رسید شما توسط پشتیبانی رد شد.\n\nلطفاً با ارسال رسید معتبر دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
            reply_markup=MAIN_MENU_REPLY_MARKUP
        )
    except error.Forbidden:
        logger.warning(f"User {user_id} blocked the bot, cannot send receipt rejection notification")
        await query.message.reply_text(f"⚠️ رسید رد شد اما کاربر {user_id} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
    
    # به‌روزرسانی پیام ادمین
    try:
        await query.edit_message_caption(
            caption=f"❌ رسید رد شد\n\n👤 کاربر: {user_id}\n❌ توسط: {query.from_user.first_name}"
        )
    except Exception as e:
        logger.error(f"Failed to edit admin message: {e}")

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
    
    # اطلاع به ادمین
    await update.message.reply_text(
        f"✅ موجودی کاربر {user_id} به میزان {amount:,.0f} تومان افزایش یافت.\n\n💰 موجودی جدید: {new_balance:,.0f} تومان"
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
        await update.message.reply_text(f"⚠️ موجودی افزایش یافت اما کاربر {user_id} ربات را مسدود کرده و نمی‌توان به او اطلاع داد.")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
        await update.message.reply_text(f"⚠️ کاربر {user_id} پیدا نشد یا خطا در ارسال پیام.")

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
    """فوروارد پیام تیکت به ادمین‌ها با پشتیبانی از تمام انواع محتوا"""
    user = update.effective_user
    original_message = update.message
    
    try:
        admin_message_header = f"📞 پیام پشتیبانی جدید\nنام کاربر: {user.first_name} (ID: {user.id})\n"
        
        if 'support_map' not in context.bot_data: 
            context.bot_data['support_map'] = {}
        
        success_count = 0
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(admin_id, admin_message_header)
                
                # فوروارد پیام اصلی به ادمین (کاربر برای همه نوع محتوا)
                forwarded_message = await context.bot.forward_message(
                    chat_id=admin_id,
                    from_chat_id=user.id,
                    message_id=original_message.message_id
                )
                context.bot_data['support_map'][forwarded_message.message_id] = user.id
                success_count += 1
                
            except error.Forbidden:
                logger.warning(f"Bot is blocked by admin {admin_id}, skipping this admin")
                continue
            except Exception as e:
                logger.error(f"Failed to forward message to admin {admin_id}: {e}")
                continue
        
        # اگر حداقل به یک ادمین ارسال شد، پیام تأیید به کاربر بفرست
        if success_count > 0:
            try:
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
    """پاسخ ادمین به تیکت با مدیریت خطای کاربر مسدود شده"""
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لطفاً برای پاسخ دادن، پیام اصلی کاربر را ریپلای کنید.")
        return
        
    original_message_id = update.message.reply_to_message.message_id
    user_id = context.bot_data.get('support_map', {}).get(original_message_id)
    
    if user_id:
        try:
            await context.bot.send_message(
                user_id,
                f"💬 پاسخ پشتیبانی:\n\n{update.message.text}"
            )
            await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
            
        except error.Forbidden:
            await update.message.reply_text(
                "❌ ارسال پاسخ به کاربر ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
            )
            logger.warning(f"Failed to send reply to user {user_id}: bot was blocked by the user")
            
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
        
    if data.startswith("approve_receipt_"):
        return await approve_receipt_callback(update, context)
        
    if data.startswith("reject_receipt_"):
        return await reject_receipt_callback(update, context)
        
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

def main() -> None:
    """شروع به کار ربات"""
    application = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_balance_command))  # دستور ادمین
    
    application.add_handler(wallet_conv_handler)
    application.add_handler(support_conv_handler)
    
    application.add_handler(purchase_conv_handler) 
    
    application.add_handler(config_name_conv_handler) 
    application.add_handler(renewal_conv_handler)
    
    # هندلرهای دکمه‌های شیشه‌ای
    application.add_handler(CallbackQueryHandler(back_to_select_server, pattern="^back_to_select_server$"))
    application.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^SERVICE_DETAILS_|SHOW_SUB_LINK_|back_to_main_from_services|back_to_services|OPEN_MY_SERVICES|approve_receipt_|reject_receipt_"))
    
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