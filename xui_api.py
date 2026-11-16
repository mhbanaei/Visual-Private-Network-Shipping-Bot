"""
کلاینت همگام (sync) برای API پنل 3x-ui — استفاده در پنل وب ادمین.

همان مسیر ورودی/CSRF/Endpointهایی که ربات استفاده می‌کند، اینجا هم به کار می‌رود،
ولی به صورت همگام تا داخل تردهای پنل ساده باشد.
"""

import json
import time
import urllib3

import requests

from servers import SERVERS_CONFIG

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_session = requests.Session()
_session.verify = False


def server_keys() -> list:
    return list(SERVERS_CONFIG.keys())


def cfg(server_key: str) -> dict:
    return SERVERS_CONFIG.get(server_key, {}) or {}


def display_name(server_key: str) -> str:
    return cfg(server_key).get("display_name") or server_key


def base_url(server_key: str) -> str:
    conf = cfg(server_key)
    panel_url = str(conf.get("xui_panel_url") or "").strip().rstrip("/")
    base_path = str(conf.get("base_path") or "").strip()
    if base_path.lower() in ("", "/", "base_path", "/base_path", "login_path", "/login_path"):
        base_path = ""
    if base_path:
        if not base_path.startswith("/"):
            base_path = "/" + base_path
        base_path = base_path.rstrip("/")
        if panel_url.endswith(base_path):
            base_path = ""
    return panel_url + base_path


def _origin(server_key: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(base_url(server_key))
    return f"{parts.scheme}://{parts.netloc}"


_cookies = {}
_csrf = {}
_logged_in = {}


def _token_of(server_key: str) -> str:
    return str(cfg(server_key).get("api_token") or "").strip()


def _load_csrf(server_key: str) -> None:
    if _token_of(server_key):
        return
    try:
        response = _session.get(base_url(server_key) + "/csrf-token", timeout=10)
        if response.status_code == 200:
            payload = response.json()
            token = payload.get("obj")
            if token:
                _csrf[server_key] = str(token)
    except Exception:
        pass


def login(server_key: str) -> bool:
    """ورود به پنل؛ با API Token یا یوزر/پس + CSRF"""
    if _token_of(server_key):
        return True
    conf = cfg(server_key)
    username = str(conf.get("xui_username") or "").strip()
    password = str(conf.get("xui_password") or "")
    if not username or not password:
        return False

    _load_csrf(server_key)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": _origin(server_key),
        "Referer": base_url(server_key) + "/",
    }
    if _csrf.get(server_key):
        headers["X-CSRF-Token"] = _csrf[server_key]
    try:
        response = _session.post(base_url(server_key) + "/login",
                                 json={"username": username, "password": password},
                                 headers=headers, timeout=15)
        payload = response.json() if response.content else {}
    except Exception:
        return False
    if response.status_code == 200 and payload.get("success") is True:
        _logged_in[server_key] = True
        _csrf.pop(server_key, None)
        _load_csrf(server_key)
        return True
    return False


def request(server_key: str, method: str, path: str, json_body=None, retry=True):
    headers = {"Accept": "application/json, text/plain, */*"}
    if _token_of(server_key):
        headers["Authorization"] = f"Bearer {_token_of(server_key)}"
    else:
        if not _logged_in.get(server_key) and not login(server_key):
            return None
        headers["Origin"] = _origin(server_key)
        headers["Referer"] = base_url(server_key) + "/"
        if method.upper() not in ("GET", "HEAD") and _csrf.get(server_key):
            headers["X-CSRF-Token"] = _csrf[server_key]

    url = path if path.startswith("http") else base_url(server_key) + path
    try:
        response = _session.request(method, url, headers=headers, json=json_body, timeout=20)
    except Exception:
        return None

    if response.status_code in (401, 403) and retry and not _token_of(server_key):
        _logged_in.pop(server_key, None)
        _csrf.pop(server_key, None)
        _load_csrf(server_key)
        if login(server_key):
            return request(server_key, method, path, json_body=json_body, retry=False)
    return response


def payload(response) -> dict:
    if response is None:
        return {}
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def get_inbound(server_key: str):
    response = request(server_key, "GET", "/panel/api/inbounds/list")
    data = payload(response)
    if not data.get("success"):
        return None
    inbounds = data.get("obj") or []
    if not inbounds:
        return None
    try:
        wanted = int(cfg(server_key).get("inbound_id") or 0)
    except (TypeError, ValueError):
        wanted = 0
    if wanted > 0:
        for item in inbounds:
            if int(item.get("id") or 0) == wanted:
                return item
    return inbounds[-1]


def get_client(server_key: str, email: str):
    """اطلاعات کامل یک کلاینت + مصرف ترافیک"""
    response = request(server_key, "GET", f"/panel/api/clients/get/{email}")
    data = payload(response)
    if data.get("success") and isinstance(data.get("obj"), dict):
        obj = data["obj"]
        client = dict(obj.get("client") or {})
        traffic = obj.get("traffic") or {}
        if not isinstance(traffic, dict):
            traffic = {}
        if client:
            client["up"] = int(traffic.get("up", client.get("up", 0)) or 0)
            client["down"] = int(traffic.get("down", client.get("down", 0)) or 0)
            if not client["up"] and not client["down"] and obj.get("usedTraffic"):
                client["down"] = int(obj.get("usedTraffic") or 0)
            return client

    inbound = get_inbound(server_key)
    if not inbound:
        return None
    clients = (inbound.get("settings") or {}).get("clients") or []
    for client in clients:
        if client.get("email") == email:
            return dict(client)
    return None


EXISTS = "exists"
MISSING = "missing"
UNREACHABLE = "unreachable"


def all_inbounds(server_key: str):
    """همهٔ اینباندهای پنل (برای بررسی یک کلاینت در کل پنل، نه فقط یک اینباند)"""
    response = request(server_key, "GET", "/panel/api/inbounds/list")
    data = payload(response)
    if not data.get("success"):
        return None
    return data.get("obj") or []


def client_state(server_key: str, email: str) -> str:
    """وضعیت کلاینت در پنل: exists / missing / unreachable

    «unreachable» یعنی پنل جواب نداد؛ در این حالت هرگز نباید چیزی از ربات حذف شود.
    وجود کلاینت در همهٔ اینباندها بررسی می‌شود تا تغییر اینباند باعث حذف اشتباه نشود.
    """
    response = request(server_key, "GET", f"/panel/api/clients/get/{email}")
    if response is None:
        return UNREACHABLE
    data = payload(response)
    if data.get("success") and isinstance(data.get("obj"), dict) and data["obj"].get("client"):
        return EXISTS
    inbounds = all_inbounds(server_key)
    if not inbounds:
        return UNREACHABLE
    for inbound in inbounds:
        settings = inbound.get("settings") or {}
        if isinstance(settings, str):
            try:
                settings = json.loads(settings)
            except ValueError:
                settings = {}
        for client in settings.get("clients") or []:
            if client.get("email") == email:
                return EXISTS
    return MISSING


def update_client(server_key: str, email: str, new_email: str = None,
                  total_gb: float = None, expiry_ms: int = None,
                  limit_ip: int = None, enable: bool = None) -> tuple:
    """ویرایش کلاینت؛ فیلدهای None بدون تغییر می‌مانند"""
    current = get_client(server_key, email)
    if not current:
        return False, "کلاینت در پنل پیدا نشد"

    body = {
        "email": new_email or email,
        "limitIp": int(current.get("limitIp") or 0) if limit_ip is None else int(limit_ip),
        "totalGB": int(current.get("totalGB") or 0),
        "expiryTime": int(current.get("expiryTime") or 0),
        "enable": bool(current.get("enable", True)) if enable is None else bool(enable),
        "flow": current.get("flow") or "",
    }
    if total_gb is not None:
        body["totalGB"] = 0 if float(total_gb) <= 0 else int(float(total_gb) * 1024 ** 3)
    if expiry_ms is not None:
        body["expiryTime"] = int(expiry_ms)

    response = request(server_key, "POST", f"/panel/api/clients/update/{email}", json_body=body)
    data = payload(response)
    if response is not None and response.status_code == 200 and data.get("success", False):
        return True, ""
    message = data.get("msg") or (f"HTTP {response.status_code}" if response is not None else "بدون پاسخ")
    return False, message


def reset_traffic(server_key: str, email: str) -> tuple:
    response = request(server_key, "POST", f"/panel/api/clients/resetTraffic/{email}")
    data = payload(response)
    if response is not None and response.status_code == 200 and data.get("success", False):
        return True, ""
    return False, data.get("msg") or "خطا در ریست ترافیک"


def delete_client(server_key: str, email: str) -> tuple:
    response = request(server_key, "POST", f"/panel/api/clients/del/{email}")
    data = payload(response)
    if response is not None and response.status_code == 200 and data.get("success", False):
        return True, ""
    inbound = get_inbound(server_key)
    if inbound:
        response = request(server_key, "POST",
                           f"/panel/api/inbounds/{int(inbound.get('id') or 1)}/delClient/{email}")
        data = payload(response)
        if response is not None and response.status_code == 200 and data.get("success", False):
            return True, ""
    return False, data.get("msg") or "خطا در حذف کلاینت"


def onlines(server_key: str) -> list:
    """لیست ایمیل کلاینت‌هایی که الان آنلاین هستند"""
    response = request(server_key, "POST", "/panel/api/inbounds/onlines")
    data = payload(response)
    if isinstance(data.get("obj"), list):
        return [str(x) for x in data["obj"]]
    return []


def add_client(server_key: str, email: str, uuid: str, total_gb: float = 0,
               days: int = 30, limit_ip: int = 1) -> tuple:
    """ساخت کلاینت ساده (برای تست/ساخت دستی از پنل)"""
    inbound = get_inbound(server_key)
    if not inbound:
        return False, "اینباند پیدا نشد"
    client = {
        "id": uuid,
        "flow": "",
        "email": email,
        "limitIp": int(limit_ip),
        "totalGB": 0 if total_gb <= 0 else int(total_gb * 1024 ** 3),
        "expiryTime": int((time.time() + days * 86400) * 1000) if days else 0,
        "enable": True,
        "tgId": 0,
        "subId": uuid[:16],
        "comment": "panel-test",
    }
    inbound_id = int(inbound.get("id") or 1)
    response = request(server_key, "POST", "/panel/api/clients/add",
                       json_body={"client": client, "inboundIds": [inbound_id]})
    data = payload(response)
    if response is not None and response.status_code == 200 and data.get("success", False):
        return True, ""
    if response is None or response.status_code == 404:
        settings = {"clients": [dict(client, tgId="")]}
        response = request(server_key, "POST", f"/panel/api/inbounds/addClient",
                           json_body={"id": inbound_id, "settings": json.dumps(settings)})
        data = payload(response)
        if response is not None and response.status_code == 200 and data.get("success", False):
            return True, ""
    return False, data.get("msg") or "خطا در ساخت کلاینت"


# ---------- کمک‌کننده‌های نمایش ----------

def human_bytes(value) -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.2f} TB"


def expiry_info(expiry_ms) -> dict:
    """روزهای باقی‌مانده و تاریخ انقضا"""
    try:
        expiry_ms = int(expiry_ms or 0)
    except (TypeError, ValueError):
        expiry_ms = 0
    if expiry_ms <= 0:
        return {"days_left": None, "date": "نامحدود", "expired": False}
    now = time.time()
    seconds = expiry_ms / 1000 - now
    date = time.strftime("%Y-%m-%d %H:%M", time.localtime(expiry_ms / 1000))
    return {
        "days_left": int(seconds // 86400),
        "date": date,
        "expired": seconds <= 0,
    }


def sub_link_for(new_name: str, old_link: str = "") -> str:
    """ساخت لینک اشتراک جدید بعد از تغییر نام (جایگزینی بخش آخر لینک)"""
    old_link = (old_link or "").rstrip("/")
    if not old_link:
        return ""
    if "/" not in old_link:
        return new_name
    head = old_link.rsplit("/", 1)[0]
    return f"{head}/{new_name}"
