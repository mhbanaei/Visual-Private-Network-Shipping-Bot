"""تنظیمات سرورهای 3x-ui (مشترک بین ربات‌ها و پنل ادمین)"""

SERVERS_CONFIG = {
    "Server_1": {
        "display_name": "Server 🟣",
        "xui_panel_url": "https://your-panel-domain:2042/your-secret-path/",
        "xui_username": "admin",
        "xui_password": "CHANGE_ME",   # رمز پنل را اینجا بگذارید
        "api_token": "",   # اختیاری: API Token پنل (Settings → Security → API Token)
        "login_path": "",   # خالی = /login زیر base path
        "inbound_id": 1,   # 🌟 0 = آخرین اینباند پنل (خودکار)
        "server_address": "example.com",
        "server_port_subscription": 2096,
        "server_port_client": 8080,
        "base_path": "/base_path",
        "subscribe_path": "/subscribe/",
        "active": 1,   # 🌟 1 = قابل خرید | 0 = ظرفیت پر
        "tamdid": 1    # 🌟 1 = قابل تمدید | 0 = تمدید غیرفعال
    }
}
