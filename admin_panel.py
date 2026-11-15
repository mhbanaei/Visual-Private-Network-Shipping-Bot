"""
پنل وب ادمین (پورت 9997)

- داده‌ها را مستقیم از همان دیتابیس ربات (botdata.db) می‌خواند و می‌نویسد؛
  هر تغییری در پنل بلافاصله در ربات دیده می‌شود و برعکس.
- بدون وابستگی خارجی (فقط کتابخانهٔ استاندارد پایتون + requests برای اعلان).

پنل به صورت خودکار همراه start-card.bat یا start-zarinpal.bat بالا می‌آید.
اجرای دستی:  python admin_panel.py
رمز ورود: متغیر محیطی PANEL_PASSWORD (پیش‌فرض: CHANGE_ME)
درگاه: متغیر محیطی PANEL_PORT (پیش‌فرض: 9997)
"""

import datetime
import html
import http.cookies
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

import db
import xui_api

HOST = os.environ.get("PANEL_HOST", "0.0.0.0")
PORT = int(os.environ.get("PANEL_PORT", "9997"))
PASSWORD = os.environ.get("PANEL_PASSWORD", "CHANGE_ME")
SESSION_TTL = 12 * 3600
MAX_LOGIN_ATTEMPTS = 3

# ------------------------------------------------------------
# قفل پنل:
#   "0" = پنل باز است
#   "1" = پنل قفل است
# بعد از ۳ بار رمز اشتباه، این مقدار خودکار ۱ می‌شود.
# برای باز کردن پنل، همین 1 را به 0 تغییر بده و ربات/پنل را دوباره اجرا کن.
# ------------------------------------------------------------
PANEL_LOCK = "0"

LOCKED = PANEL_LOCK.strip() == "1"
_login_failures = 0
_fail_lock = threading.Lock()

_sessions = {}
_sessions_lock = threading.Lock()

# توکن ربات برای ارسال اعلان (توسط ربات پر می‌شود)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")


def fetch_bot_username(token: str) -> str:
    """گرفتن یوزرنیم ربات برای ساخت لینک رفرال در پنل"""
    if not token:
        return BOT_USERNAME
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = response.json()
        if data.get("ok"):
            return data["result"].get("username") or BOT_USERNAME
    except Exception:
        pass
    return BOT_USERNAME

TX_LABELS = {
    "deposit": "واریز",
    "withdrawal": "برداشت",
    "purchase": "خرید",
    "renewal": "تمدید",
    "referral_earning": "کمیسیون رفرال",
    "admin_adjustment": "اصلاح ادمین",
}


# ============================================================
# ابزارهای کمکی
# ============================================================

def money(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "0"


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_amount(raw, default=None):
    """تبدیل ورودی کاربر به عدد؛ ارقام فارسی، ویرگول و واحد پول را قبول می‌کند"""
    if raw is None:
        return default
    text = str(raw).translate(PERSIAN_DIGITS)
    text = text.replace("٬", "").replace(",", "").replace("٫", ".")
    for word in ("تومان", "تومن", "rial", "ریال", " ", "\u200c", "_"):
        text = text.replace(word, "")
    if text in ("", "-", "+"):
        return default
    try:
        return float(text)
    except ValueError:
        return default


def show_int(value) -> str:
    """نمایش عدد صحیح بدون اعشار اضافی"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def parent_invalid_name(name: str) -> bool:
    """نام کانفیگ باید انگلیسی و بین ۳ تا ۳۲ کاراکتر باشد"""
    return not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", name or "")


def parse_date_to_ms(raw: str):
    """تبدیل تاریخ (2026-12-01 یا 2026-12-01 18:30) به timestamp میلی‌ثانیه"""
    text = (raw or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(text, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


def normalize_percent(value):
    """نرمال‌سازی درصد برای مقایسه (خالی/صفر/عدد)"""
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def find_client_by_uuid(server_key: str, uuid_value) -> str:
    """نام فعلی کلاینت در پنل 3x-ui بر اساس UUID (برای تشخیص تغییر نام از داخل پنل)"""
    uuid_value = str(uuid_value or "").strip()
    if not uuid_value:
        return ""
    try:
        inbound = xui_api.get_inbound(server_key) or {}
    except Exception:
        return ""
    for client in (inbound.get("settings") or {}).get("clients") or []:
        if str(client.get("id") or "") == uuid_value:
            return str(client.get("email") or "")
    return ""


def flash(url: str, message: str, kind: str = "ok") -> str:
    return f"{url}{'&' if '?' in url else '?'}flash={urllib.parse.quote(message)}&kind={kind}"


def telegram_send(chat_id, text: str) -> bool:
    if not BOT_TOKEN:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        return bool(response.ok and response.json().get("ok"))
    except Exception:
        return False


def new_session() -> str:
    token = secrets.token_hex(24)
    with _sessions_lock:
        _sessions[token] = time.time() + SESSION_TTL
    return token


def lock_panel() -> None:
    """قفل پنل و نوشتن PANEL_LOCK = \"1\" داخل همین فایل"""
    global LOCKED
    LOCKED = True
    try:
        path = os.path.abspath(__file__)
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        new = re.sub(r'(?m)^PANEL_LOCK = "[01]"', 'PANEL_LOCK = "1"', src, count=1)
        if new != src:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            print("[panel] LOCKED after 3 wrong passwords. Set PANEL_LOCK = \"0\" to unlock.")
    except Exception as exc:
        print(f"[panel] could not persist lock flag: {exc}")


def register_failed_login() -> None:
    global _login_failures
    with _fail_lock:
        _login_failures += 1
        reached = _login_failures >= MAX_LOGIN_ATTEMPTS
    if reached:
        lock_panel()


def valid_session(token: str) -> bool:
    if not token:
        return False
    with _sessions_lock:
        exp = _sessions.get(token)
        if not exp:
            return False
        if exp < time.time():
            _sessions.pop(token, None)
            return False
        return True


# ============================================================
# قالب صفحه
# ============================================================

PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · پنل مدیریت</title>
<style>
  :root {{ color-scheme: dark; --bg:#0b1120; --panel:#111c33; --line:#1e293b; --muted:#94a3b8; --text:#e2e8f0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:Tahoma,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); font-size:14px; }}
  a {{ color:#7dd3fc; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  header {{ position:sticky; top:0; z-index:10; background:#0f172aee; backdrop-filter:blur(6px);
           border-bottom:1px solid var(--line); padding:10px 16px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  header .brand {{ font-weight:bold; font-size:16px; color:#f8fafc; white-space:nowrap; }}
  header nav {{ display:flex; gap:4px; flex-wrap:wrap; }}
  header nav a {{ padding:7px 11px; border-radius:9px; color:#cbd5e1; }}
  header nav a:hover, header nav a.active {{ background:#1e293b; text-decoration:none; color:#f8fafc; }}
  main {{ max-width:1200px; margin:0 auto; padding:18px 14px 60px; }}
  h1 {{ font-size:19px; margin:0 0 14px; }}
  h2 {{ font-size:15px; margin:26px 0 10px; color:#cbd5e1; border-right:3px solid #2563eb; padding-right:8px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:13px; }}
  .card .k {{ color:var(--muted); font-size:11.5px; margin-bottom:6px; }}
  .card .v {{ font-size:18px; font-weight:bold; word-break:break-word; }}
  .tablewrap {{ overflow-x:auto; border-radius:12px; border:1px solid var(--line); }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); min-width:520px; }}
  th, td {{ padding:9px 10px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }}
  th {{ background:#16213c; color:var(--muted); font-weight:normal; font-size:12.5px; position:sticky; top:0; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#14203a; }}
  td.wrap {{ white-space:normal; word-break:break-all; min-width:180px; }}
  .muted {{ color:var(--muted); }}
  .small {{ font-size:12px; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11.5px; }}
  .pending {{ background:#7c2d12; color:#fed7aa; }}
  .approved, .ok {{ background:#14532d; color:#bbf7d0; }}
  .rejected, .bad {{ background:#7f1d1d; color:#fecaca; }}
  form.inline {{ display:inline; }}
  input, button, textarea, select {{ font-family:inherit; font-size:13px; }}
  input[type=text], input[type=password], input[type=number], select, textarea {{
      background:#0b1220; border:1px solid var(--line); color:var(--text);
      border-radius:9px; padding:7px 9px; max-width:100%; }}
  input:focus, textarea:focus, select:focus {{ outline:1px solid #2563eb; }}
  button {{ background:#2563eb; color:#fff; border:none; border-radius:9px; padding:7px 12px; cursor:pointer; }}
  button:hover {{ filter:brightness(1.1); }}
  button.grey {{ background:#334155; }}
  button.red {{ background:#b91c1c; }}
  button.mini {{ padding:4px 8px; font-size:11.5px; border-radius:7px; }}
  a.btn {{ display:inline-block; background:#2563eb; color:#fff; border-radius:9px; padding:7px 12px; font-size:13px; }}
  a.btn.grey {{ background:#334155; }}
  .row {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:12px; }}
  .grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
  .box {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .box h3 {{ margin:0 0 10px; font-size:13.5px; color:#cbd5e1; font-weight:normal; }}
  .login {{ max-width:360px; margin:10vh auto; }}
  .login input {{ width:100%; margin-bottom:10px; }}
  .err {{ color:#fca5a5; margin-bottom:8px; }}
  .notice {{ border-radius:10px; padding:10px 12px; margin-bottom:14px; font-size:13px; }}
  .notice.ok {{ background:#14532d; color:#bbf7d0; }}
  .notice.bad {{ background:#7f1d1d; color:#fecaca; }}
  details summary {{ cursor:pointer; color:#7dd3fc; font-size:12.5px; }}
  .tag {{ background:#1e293b; color:#cbd5e1; border-radius:6px; padding:1px 6px; font-size:11.5px; }}
  @media (max-width:640px) {{
    main {{ padding:12px 9px 60px; }}
    header {{ padding:9px 10px; gap:8px; }}
    header nav a {{ padding:6px 9px; font-size:12.5px; }}
    h1 {{ font-size:17px; }}
    .card .v {{ font-size:16px; }}
    table {{ min-width:460px; }}
  }}
</style>
</head>
<body>
{header}
<main>{body}</main>
</body>
</html>
"""


def render(handler, title, body, active=""):
    items = [
        ("/", "داشبورد"),
        ("/users", "کاربران"),
        ("/services", "سرویس‌ها"),
        ("/receipts", "رسیدها"),
        ("/transactions", "تراکنش‌ها"),
        ("/announce", "اعلان"),
    ]
    nav = "".join(
        f'<a href="{href}"{" class=\"active\"" if href == active else ""}>{label}</a>'
        for href, label in items
    )
    header = (f'<header><span class="brand">🛠 پنل مدیریت</span><nav>{nav}</nav>'
              f'<span style="margin-right:auto"><a href="/logout">خروج</a></span></header>')
    handler.send_html(PAGE.format(title=html.escape(title), header=header, body=body))


class PanelServer(ThreadingHTTPServer):
    """یک نمونه در هر زمان؛ پورت دوباره باز نمی‌شود"""
    allow_reuse_address = False
    allow_reuse_port = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "AdminPanel/2.0"

    # ---------- helpers ----------
    def send_html(self, content, status=200):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def session_token(self):
        raw = self.headers.get("Cookie", "")
        try:
            jar = http.cookies.SimpleCookie(raw)
            val = jar.get("panel_session")
            return val.value if val else None
        except Exception:
            return None

    def authed(self):
        return valid_session(self.session_token())

    def require_auth(self):
        if LOCKED:
            self.redirect("/login")
            return False
        if not self.authed():
            self.redirect("/login")
            return False
        return True

    def read_form(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        return {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}

    def flash_from_query(self, qs):
        message = qs.get("flash")
        if not message:
            return ""
        kind = qs.get("kind", "ok")
        css = "ok" if kind == "ok" else "bad"
        return f'<div class="notice {css}">{html.escape(message)}</div>'

    # ---------- routing ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            if path == "/login":
                return self.page_login()
            if path == "/logout":
                token = self.session_token()
                with _sessions_lock:
                    _sessions.pop(token, None)
                return self.redirect("/login", cookie="panel_session=; Max-Age=0; Path=/")
            if not self.require_auth():
                return
            if path == "/":
                return self.page_dashboard(qs)
            if path == "/users":
                return self.page_users(qs)
            if path.startswith("/user/"):
                parts = path.split("/")
                if len(parts) >= 5 and parts[3] == "service":
                    return self.page_service(parts[2], urllib.parse.unquote(parts[4]), qs)
                if len(parts) >= 3:
                    return self.page_user(parts[2], qs)
            if path == "/services":
                return self.page_services(qs)
            if path == "/receipts":
                return self.page_receipts(qs)
            if path == "/transactions":
                return self.page_transactions(qs)
            if path == "/announce":
                return self.page_announce()
            return self.not_found()
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.send_html(PAGE.format(title="خطا", header="", body=f"<h1>خطا</h1><pre>{html.escape(str(exc))}</pre>"), 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/login":
                return self.action_login()
            if not self.require_auth():
                return
            if path == "/users/add":
                return self.action_add_user()
            if path == "/announce":
                return self.action_announce()
            if path == "/receipts/approve" or path == "/receipts/reject":
                return self.action_receipt_by_form(path.endswith("approve"))
            if path.startswith("/receipts/") and len(path.split("/")) == 4:
                parts = path.split("/")
                if parts[3] in ("approve", "reject"):
                    return self.action_receipt(parts[2], parts[3])
            if path.startswith("/transactions/") and path.endswith("/delete"):
                return self.action_delete_transaction(path.split("/")[2])
            if path.startswith("/user/"):
                parts = path.split("/")
                if len(parts) >= 4:
                    uid, act = parts[2], parts[3]
                    if act == "delete":
                        return self.action_delete_user(uid)
                    if act == "settle":
                        return self.action_settle(uid)
                    if act == "fields":
                        return self.action_set_fields(uid)
                    if act == "balance":
                        return self.action_set_balance(uid)
                    if act == "reftrial":
                        return self.action_reset_trial(uid)
                    if act == "service" and len(parts) == 6:
                        return self.action_service_live(uid, urllib.parse.unquote(parts[4]))
                    if act == "service" and len(parts) == 5:
                        if parts[4] == "add":
                            return self.action_add_service(uid)
                        if parts[4] == "update":
                            return self.action_update_service(uid)
                        if parts[4] == "delete":
                            return self.action_delete_service(uid)
            return self.not_found()
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.send_html(PAGE.format(title="خطا", header="",
                                       body=f"<h1>خطا</h1><pre>{html.escape(str(exc))}</pre>"), 500)

    def not_found(self):
        self.send_html(PAGE.format(title="پیدا نشد", header="",
                                   body="<h1>صفحه پیدا نشد</h1><p><a href='/'>بازگشت به داشبورد</a></p>"), 404)

    # ---------- auth ----------
    def page_login(self, error=""):
        if LOCKED:
            body = """
<div class="login"><div class="box">
  <h2 style="margin-top:0;border:none;padding:0">🔒 پنل قفل شده است</h2>
  <p class="muted small">به دلیل ۳ بار رمز اشتباه، ورود بسته شد.</p>
  <p class="muted small">برای باز کردن: در فایل <b>admin_panel.py</b> مقدار
  <code>PANEL_LOCK = "1"</code> را به <code>PANEL_LOCK = "0"</code> تغییر بده و ربات/پنل را دوباره اجرا کن.</p>
</div></div>"""
            return self.send_html(PAGE.format(title="قفل", header="", body=body))
        body = f"""
<div class="login"><div class="box">
  <h2 style="margin-top:0;border:none;padding:0">ورود به پنل</h2>
  {f'<div class="err">{html.escape(error)}</div>' if error else ''}
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="رمز عبور" autofocus>
    <button type="submit" style="width:100%">ورود</button>
  </form>
</div></div>"""
        self.send_html(PAGE.format(title="ورود", header="", body=body))

    def action_login(self):
        global _login_failures
        if LOCKED:
            return self.page_login()
        form = self.read_form()
        if form.get("password") == PASSWORD:
            with _fail_lock:
                _login_failures = 0
            token = new_session()
            self.redirect("/", cookie=f"panel_session={token}; Path=/; HttpOnly; SameSite=Lax")
        else:
            register_failed_login()
            if LOCKED:
                return self.page_login()
            with _fail_lock:
                left = MAX_LOGIN_ATTEMPTS - _login_failures
            self.page_login(f"رمز عبور اشتباه است. {left} تلاش باقی مانده.")

    # ---------- dashboard ----------
    def page_dashboard(self, qs):
        s = db.stats()
        users = db.load_users()
        top_users = sorted(users.items(), key=lambda kv: -float(kv[1].get("balance") or 0))[:5]
        top_rows = "".join(
            f'<tr><td><a href="/user/{uid}">{uid}</a></td>'
            f'<td>{html.escape(("@" + u["username"]) if u.get("username") else (u.get("first_name") or "—"))}</td>'
            f'<td>{money(u.get("balance"))}</td></tr>'
            for uid, u in top_users
        ) or "<tr><td colspan='3' class='muted'>کاربری نیست.</td></tr>"

        tx_rows = ""
        for tx in db.recent_transactions(10):
            tx_rows += (
                f'<tr><td><a href="/user/{tx["user_id"]}">{tx["user_id"]}</a></td>'
                f'<td>{html.escape(TX_LABELS.get(tx["type"], tx["type"] or ""))}</td>'
                f'<td>{money(tx["amount"])}</td>'
                f'<td class="wrap muted">{html.escape(tx["description"] or "")}</td>'
                f'<td class="muted small">{html.escape((tx["timestamp"] or "")[:19].replace("T", " "))}</td></tr>'
            )
        if not tx_rows:
            tx_rows = "<tr><td colspan='5' class='muted'>تراکنشی نیست.</td></tr>"

        cards = [
            ("کاربران", f"{s['users']:,}"),
            ("مجموع موجودی", money(s["total_balance"])),
            ("سرویس‌ها", f"{s['services']:,}"),
            ("رسید در انتظار", f"{s['pending_receipts']:,}"),
            ("تراکنش امروز", f"{s['today_transactions']:,}"),
            ("فروش امروز", money(s["today_revenue"])),
        ]
        body = f"""
{self.flash_from_query(qs)}
<h1>داشبورد</h1>
<div class="cards">
  {''.join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in cards)}
</div>

<div class="grid2" style="margin-top:18px">
  <div>
    <h2>ثروتمندترین کاربران</h2>
    <div class="tablewrap"><table><tr><th>شناسه</th><th>کاربر</th><th>موجودی</th></tr>{top_rows}</table></div>
  </div>
  <div>
    <h2>وضعیت</h2>
    <div class="box">
      <p class="small muted" style="margin:0 0 8px">دیتابیس: <code>{html.escape(os.path.basename(db.DB_PATH))}</code></p>
      <p class="small muted" style="margin:0 0 8px">توکن ربات برای اعلان: {'✅ آماده' if BOT_TOKEN else '❌ تنظیم نشده (پنل را همراه ربات اجرا کن)'}</p>
      <p class="small muted" style="margin:0">پورت: {PORT} · وضعیت قفل: {'قفل' if LOCKED else 'باز'}</p>
    </div>
  </div>
</div>

<h2>آخرین تراکنش‌ها</h2>
<div class="tablewrap"><table>
<tr><th>کاربر</th><th>نوع</th><th>مبلغ</th><th>توضیح</th><th>زمان</th></tr>{tx_rows}</table></div>
"""
        render(self, "داشبورد", body, active="/")

    # ---------- users ----------
    def page_users(self, qs):
        query = (qs.get("q") or "").strip()
        sort = qs.get("sort") or "balance"
        users = db.load_users()
        items = []
        for uid, data in users.items():
            haystack = " ".join([
                uid, str(data.get("username") or ""), str(data.get("first_name") or ""),
                str(data.get("notes") or ""),
            ]).lower()
            if query and query.lower() not in haystack:
                continue
            items.append((uid, data))
        key = {
            "balance": lambda x: -float(x[1].get("balance") or 0),
            "services": lambda x: -len(x[1].get("services") or []),
            "join": lambda x: str(x[1].get("join_date") or ""),
            "id": lambda x: int(x[0]),
        }.get(sort, lambda x: -float(x[1].get("balance") or 0))
        items.sort(key=key)

        rows = ""
        for uid, data in items:
            username = f"@{data['username']}" if data.get("username") else "—"
            rows += (
                f'<tr><td><a href="/user/{uid}">{uid}</a></td>'
                f'<td>{html.escape(username)}</td>'
                f'<td>{html.escape(str(data.get("first_name") or "—"))}</td>'
                f'<td>{money(data.get("balance"))}</td>'
                f'<td>{len(data.get("services") or [])}</td>'
                f'<td>{data.get("referrals_count") or 0}</td>'
                f'<td>{html.escape(str(data.get("referral_percent")) if data.get("referral_percent") is not None else "—")}</td>'
                f'<td class="muted small">{html.escape(str(data.get("join_date") or "")[:10])}</td>'
                f'<td><a href="/user/{uid}" class="tag">مدیریت</a></td></tr>'
            )
        if not rows:
            rows = "<tr><td colspan='9' class='muted'>کاربری یافت نشد.</td></tr>"

        body = f"""
{self.flash_from_query(qs)}
<h1>کاربران ({len(items)})</h1>
<form class="row" method="get" action="/users">
  <input type="text" name="q" value="{html.escape(query)}" placeholder="شناسه، @یوزرنیم، نام یا یادداشت">
  <select name="sort">
    <option value="balance"{' selected' if sort == 'balance' else ''}>مرتب: موجودی</option>
    <option value="services"{' selected' if sort == 'services' else ''}>مرتب: تعداد سرویس</option>
    <option value="join"{' selected' if sort == 'join' else ''}>مرتب: تاریخ عضویت</option>
    <option value="id"{' selected' if sort == 'id' else ''}>مرتب: شناسه</option>
  </select>
  <button type="submit">جستجو</button>
  <a href="/users" class="muted small">حذف فیلتر</a>
</form>

<form class="row" method="post" action="/users/add">
  <input type="text" name="user_id" placeholder="شناسه کاربر جدید" required>
  <input type="text" name="balance" placeholder="موجودی اولیه (اختیاری)">
  <button type="submit">➕ افزودن کاربر</button>
</form>

<div class="tablewrap"><table>
<tr><th>شناسه</th><th>یوزرنیم</th><th>نام</th><th>موجودی</th><th>سرویس</th><th>رفرال</th><th>درصد</th><th>عضویت</th><th></th></tr>
{rows}</table></div>
"""
        render(self, "کاربران", body, active="/users")

    def page_user(self, uid, qs):
        try:
            user_id = int(uid)
        except ValueError:
            return self.not_found()
        user = db.get_user(user_id)
        if not user:
            return self.not_found()

        services = user.get("services") or []
        svc_rows = ""
        for s in services:
            name = str(s.get("config_name") or "")
            svc_rows += f"""
<tr>
  <td><a href="/user/{user_id}/service/{urllib.parse.quote(name)}">{html.escape(name)}</a></td>
  <td class="muted small">{html.escape(str(s.get("internal_key") or ""))}</td>
  <td class="muted small">{html.escape(str(s.get("server_key") or ""))}</td>
  <td class="wrap muted small">{html.escape(str(s.get("sub_link") or ""))}</td>
  <td class="muted small">{html.escape(str(s.get("purchase_date") or "")[:19].replace("T", " "))}</td>
  <td>
    <details><summary>ویرایش</summary>
      <form method="post" action="/user/{user_id}/service/update" class="row" style="margin-top:8px">
        <input type="hidden" name="config_name" value="{html.escape(name)}">
        <input type="text" name="new_name" value="{html.escape(name)}" placeholder="نام" style="width:110px">
        <input type="text" name="sub_link" value="{html.escape(str(s.get("sub_link") or ""))}" placeholder="لینک اشتراک" style="min-width:210px">
        <input type="text" name="uuid" value="{html.escape(str(s.get("uuid") or ""))}" placeholder="UUID" style="width:230px">
        <input type="text" name="internal_key" value="{html.escape(str(s.get("internal_key") or ""))}" placeholder="پلن" style="width:110px">
        <input type="text" name="server_key" value="{html.escape(str(s.get("server_key") or ""))}" placeholder="سرور" style="width:100px">
        <button type="submit" class="mini">ذخیره</button>
      </form>
      <form method="post" action="/user/{user_id}/service/delete" class="inline"
            onsubmit="return confirm('این سرویس حذف شود؟')">
        <input type="hidden" name="config_name" value="{html.escape(name)}">
        <button type="submit" class="red mini" style="margin-top:6px">حذف سرویس</button>
      </form>
    </details>
  </td>
</tr>"""
        if not svc_rows:
            svc_rows = "<tr><td colspan='6' class='muted'>سرویسی ندارد.</td></tr>"

        tx_rows = ""
        for tx in reversed(db.load_transaction_history().get(str(user_id), [])):
            tx_rows += (
                f'<tr><td class="muted small">{html.escape(str(tx.get("id") or ""))}</td>'
                f'<td>{html.escape(TX_LABELS.get(tx.get("type"), str(tx.get("type"))))}</td>'
                f'<td>{money(tx.get("amount"))}</td>'
                f'<td class="wrap">{html.escape(str(tx.get("description") or ""))}</td>'
                f'<td class="muted small">{html.escape(str(tx.get("timestamp") or "")[:19].replace("T", " "))}</td>'
                f'<td><form class="inline" method="post" action="/transactions/{html.escape(str(tx.get("id")))}/delete" '
                f'onsubmit="return confirm(\'این تراکنش حذف شود؟\')">'
                f'<button type="submit" class="red mini">حذف</button></form></td></tr>'
            )
        if not tx_rows:
            tx_rows = "<tr><td colspan='6' class='muted'>تراکنشی ندارد.</td></tr>"

        username = f"@{user['username']}" if user.get("username") else "—"
        referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}" if BOT_USERNAME else "—"
        balance = float(user.get("balance") or 0)
        body = f"""
{self.flash_from_query(qs)}
<h1>کاربر <code>{user_id}</code></h1>
<div class="cards">
  <div class="card"><div class="k">موجودی (تومان)</div><div class="v">{money(balance)}</div></div>
  <div class="card"><div class="k">یوزرنیم</div><div class="v" style="font-size:15px">{html.escape(username)}</div></div>
  <div class="card"><div class="k">نام</div><div class="v" style="font-size:15px">{html.escape(str(user.get('first_name') or '—'))}</div></div>
  <div class="card"><div class="k">سرویس</div><div class="v">{len(services)}</div></div>
  <div class="card"><div class="k">رفرال‌ها</div><div class="v">{user.get('referrals_count') or 0}</div></div>
  <div class="card"><div class="k">درآمد رفرال</div><div class="v">{money(user.get('referral_earnings'))}</div></div>
</div>

<h2>موجودی کیف پول</h2>
<div class="box">
  <form class="row" method="post" action="/user/{user_id}/balance">
    <input type="text" name="balance" value="{int(balance) if balance == int(balance) else balance}" style="width:190px">
    <button type="submit">ذخیرهٔ موجودی</button>
    <span class="muted small">هر عددی (با ویرگول هم) قابل قبول است؛ مقدار نهایی جایگزین می‌شود.</span>
  </form>
  <form class="row" method="post" action="/user/{user_id}/balance" style="margin:0">
    <input type="hidden" name="balance" value="{int(balance)}">
    <input type="text" name="delta" placeholder="مثلاً +500000 یا -120000" style="width:190px">
    <button type="submit" class="grey">اعمال تغییر نسبی</button>
  </form>
  <form class="row" method="post" action="/user/{user_id}/settle" style="margin:8px 0 0"
        onsubmit="return confirm('موجودی صفر شود؟')">
    <button type="submit" class="red">تسویه / صفر کردن موجودی</button>
    <span class="muted small">تراکنش برداشت با مبلغ فعلی ثبت می‌شود.</span>
  </form>
</div>

<h2>مشخصات و رفرال</h2>
<div class="box">
  <form class="row" method="post" action="/user/{user_id}/fields">
    <label class="small muted">نام نمایشی
      <input type="text" name="first_name" value="{html.escape(str(user.get('first_name') or ''))}" style="width:150px">
    </label>
    <label class="small muted">یوزرنیم
      <input type="text" name="username" value="{html.escape(str(user.get('username') or ''))}" style="width:150px">
    </label>
    <label class="small muted">درصد رفرال
      <input type="text" name="referral_percent" value="{html.escape('' if user.get('referral_percent') is None else str(user.get('referral_percent')))}" style="width:90px" placeholder="پیش‌فرض">
    </label>
    <label class="small muted">درآمد کل رفرال
      <input type="text" name="referral_earnings" value="{int(float(user.get('referral_earnings') or 0))}" style="width:130px">
    </label>
    <label class="small muted">تعداد رفرال
      <input type="text" name="referrals_count" value="{user.get('referrals_count') or 0}" style="width:80px">
    </label>
    <label class="small muted">شناسه رفرال‌دهنده
      <input type="text" name="referral_by" value="{html.escape('' if user.get('referral_by') is None else str(user.get('referral_by')))}" style="width:130px" placeholder="خالی = ندارد">
    </label>
    <label class="small muted" style="flex:1 1 260px">یادداشت
      <input type="text" name="notes" value="{html.escape(str(user.get('notes') or ''))}" style="width:100%">
    </label>
    <button type="submit">ذخیرهٔ همهٔ فیلدها</button>
  </form>
  <p class="small muted" style="margin:8px 0 0">درصد رفرال خالی = درصد پیش‌فرض ربات.
    لینک رفرال: <code>{html.escape(referral_link)}</code></p>
</div>

<h2>سرویس‌ها ({len(services)})</h2>
<div class="tablewrap"><table>
<tr><th>نام</th><th>پلن</th><th>سرور</th><th>لینک اشتراک</th><th>خرید</th><th>عملیات</th></tr>{svc_rows}</table></div>

<div class="box" style="margin-top:10px">
  <h3>افزودن سرویس (یا به‌روزرسانی با همان نام)</h3>
  <form class="row" method="post" action="/user/{user_id}/service/add" style="margin:0">
    <input type="text" name="config_name" placeholder="نام کانفیگ" required style="width:120px">
    <input type="text" name="sub_link" placeholder="لینک اشتراک" style="min-width:230px">
    <input type="text" name="uuid" placeholder="UUID" style="width:230px">
    <input type="text" name="internal_key" placeholder="پلن" style="width:110px">
    <input type="text" name="server_key" placeholder="سرور" value="Server_1" style="width:100px">
    <button type="submit">ذخیره</button>
  </form>
</div>

<h2>تراکنش‌ها</h2>
<div class="tablewrap"><table>
<tr><th>شناسه</th><th>نوع</th><th>مبلغ</th><th>توضیح</th><th>زمان</th><th></th></tr>{tx_rows}</table></div>

<h2>عملیات حساس</h2>
<div class="row">
  <form class="inline" method="post" action="/user/{user_id}/reftrial" onsubmit="return confirm('سابقهٔ تست رایگان پاک شود؟')">
    <button type="submit" class="grey">ریست تست رایگان</button>
  </form>
  <form class="inline" method="post" action="/user/{user_id}/delete" onsubmit="return confirm('کاربر و همهٔ داده‌هایش حذف شود؟')">
    <button type="submit" class="red">حذف کامل کاربر</button>
  </form>
</div>
"""
        render(self, f"کاربر {user_id}", body, active="/users")

    # ---------- service live page ----------
    def page_service(self, uid, name, qs):
        try:
            user_id = int(uid)
        except ValueError:
            return self.not_found()
        user = db.get_user(user_id)
        if not user:
            return self.not_found()
        service = next((s for s in user.get("services") or []
                        if str(s.get("config_name")) == name), None)
        if not service:
            return self.not_found()

        server_key = service.get("server_key") or "Server_1"
        client = xui_api.get_client(server_key, name) if server_key in xui_api.server_keys() else None
        if client is None and server_key in xui_api.server_keys():
            renamed = find_client_by_uuid(server_key, service.get("uuid"))
            if renamed and renamed != name:
                new_link = xui_api.sub_link_for(renamed, service.get("sub_link") or "")
                db.rename_service(user_id, name, renamed)
                if new_link:
                    db.update_service_fields(user_id, renamed, sub_link=new_link)
                return self.redirect(flash(
                    f"/user/{user_id}/service/{urllib.parse.quote(renamed)}",
                    f"نام کلاینت در پنل 3x-ui به «{renamed}» عوض شده بود؛ در ربات هم ذخیره شد."))
        if client:
            used = int(client.get("up") or 0) + int(client.get("down") or 0)
            total = int(client.get("totalGB") or 0)
            remaining = "نامحدود" if total <= 0 else xui_api.human_bytes(max(0, total - used))
            expiry = xui_api.expiry_info(client.get("expiryTime"))
            status = "آنلاین" if name in xui_api.onlines(server_key) else "آفلاین"
            enabled = "فعال" if bool(client.get("enable", True)) else "غیرفعال"
            limit_ip = int(client.get("limitIp") or 0)
            days_left = "—" if expiry["days_left"] is None else f"{expiry['days_left']} روز"
            live_cards = f"""
  <div class="card"><div class="k">مصرف شده</div><div class="v">{xui_api.human_bytes(used)}</div></div>
  <div class="card"><div class="k">حجم کل</div><div class="v">{'نامحدود' if total <= 0 else xui_api.human_bytes(total)}</div></div>
  <div class="card"><div class="k">باقی‌مانده</div><div class="v">{remaining}</div></div>
  <div class="card"><div class="k">اعتبار</div><div class="v" style="font-size:15px">{html.escape(expiry['date'])}</div>
    <div class="k" style="margin-top:4px">{days_left}</div></div>
  <div class="card"><div class="k">وضعیت اتصال</div><div class="v" style="font-size:15px">{status}</div></div>
  <div class="card"><div class="k">وضعیت کلاینت</div><div class="v" style="font-size:15px">{enabled}</div></div>
  <div class="card"><div class="k">تعداد دستگاه مجاز</div><div class="v">{limit_ip or 'نامحدود'}</div></div>"""
        else:
            live_cards = ('<div class="notice bad">اطلاعات زنده از پنل 3x-ui گرفته نشد '
                          '(کلاینت حذف شده یا اتصال پنل برقرار نیست).</div>')

        current_total_gb = round(int((client or {}).get("totalGB") or 0) / (1024 ** 3), 2)
        base = f"/user/{user_id}/service/{urllib.parse.quote(name)}/live"
        body = f"""
{self.flash_from_query(qs)}
<h1>سرویس <code>{html.escape(name)}</code></h1>
<p class="muted small">کاربر <a href="/user/{user_id}">{user_id}</a> · سرور {html.escape(xui_api.display_name(server_key))}
 ({html.escape(server_key)})</p>
<div class="cards">{live_cards}</div>

<div class="grid2" style="margin-top:18px">
  <div class="box">
    <h3>تغییر نام اکانت (نام کاربری در پنل)</h3>
    <form class="row" method="post" action="{base}" style="margin:0">
      <input type="hidden" name="action" value="rename">
      <input type="text" name="new_name" value="{html.escape(name)}" style="width:150px">
      <button type="submit">ذخیرهٔ نام و اطلاع به کاربر</button>
    </form>
    <p class="muted small" style="margin:8px 0 0">لینک اشتراک هم خودکار به نام جدید تغییر می‌کند و به کاربر اطلاع داده می‌شود.</p>
  </div>

  <div class="box">
    <h3>حجم سرویس (گیگابایت)</h3>
    <form class="row" method="post" action="{base}" style="margin:0">
      <input type="hidden" name="action" value="volume">
      <input type="text" name="total_gb" value="{current_total_gb}" style="width:110px">
      <button type="submit">تنظیم حجم کل</button>
      <span class="muted small">0 = نامحدود</span>
    </form>
    <form class="row" method="post" action="{base}" style="margin:8px 0 0">
      <input type="hidden" name="action" value="volume_delta">
      <input type="text" name="delta_gb" placeholder="مثلاً ۵ یا -۲" style="width:110px">
      <button type="submit" class="grey">افزودن/کم کردن حجم</button>
    </form>
  </div>

  <div class="box">
    <h3>اعتبار / تاریخ انقضا</h3>
    <form class="row" method="post" action="{base}" style="margin:0">
      <input type="hidden" name="action" value="expiry_days">
      <input type="text" name="days" placeholder="مثلا ۳۰" style="width:100px">
      <button type="submit">تمدید اعتبار (روز از الان)</button>
    </form>
    <form class="row" method="post" action="{base}" style="margin:8px 0 0">
      <input type="hidden" name="action" value="expiry_date">
      <input type="text" name="date" placeholder="2026-12-01 یا 2026-12-01 18:30" style="width:190px">
      <button type="submit" class="grey">تعیین تاریخ دقیق</button>
    </form>
  </div>

  <div class="box">
    <h3>دستگاه‌ها و وضعیت</h3>
    <form class="row" method="post" action="{base}" style="margin:0">
      <input type="hidden" name="action" value="limit_ip">
      <input type="text" name="limit_ip" value="{int((client or {}).get('limitIp') or 0)}" style="width:90px">
      <button type="submit">تعداد دستگاه مجاز</button>
      <span class="muted small">0 = نامحدود</span>
    </form>
    <div class="row" style="margin:8px 0 0">
      <form class="inline" method="post" action="{base}">
        <input type="hidden" name="action" value="enable">
        <button class="grey mini" type="submit">{'غیرفعال کردن' if (client or {}).get('enable', True) else 'فعال کردن'}</button>
      </form>
      <form class="inline" method="post" action="{base}" onsubmit="return confirm('مصرف ریست شود؟')">
        <input type="hidden" name="action" value="reset">
        <button class="grey mini" type="submit">ریست مصرف</button>
      </form>
    </div>
  </div>
</div>

<h2>لینک اشتراک</h2>
<div class="box"><code style="word-break:break-all">{html.escape(str(service.get('sub_link') or '—'))}</code></div>

<h2>ویرایش در پنل 3x-ui</h2>
<div class="box">
  <div class="row" style="margin:0">
    <a class="btn" href="{html.escape(xui_api.base_url(server_key) + '/panel/inbounds')}" target="_blank" rel="noopener">باز کردن پنل 3x-ui</a>
    <form class="inline" method="post" action="{base}">
      <input type="hidden" name="action" value="sync">
      <button class="grey" type="submit">بازخوانی از پنل 3x-ui</button>
    </form>
  </div>
  <p class="muted small" style="margin:8px 0 0">
    اگر در پنل 3x-ui نام کلاینت یا حجم و تاریخش را عوض کردی، با دکمهٔ «بازخوانی» تغییرات داخل ربات ذخیره می‌شود
    (تشخیص تغییر نام از روی UUID انجام می‌شود).
  </p>
</div>

<h2>عملیات حساس</h2>
<div class="row">
  <form class="inline" method="post" action="{base}" onsubmit="return confirm('این کلاینت از پنل 3x-ui و دیتابیس حذف شود؟')">
    <input type="hidden" name="action" value="delete">
    <button class="red" type="submit">حذف کامل سرویس</button>
  </form>
  <a href="/user/{user_id}" class="muted small">بازگشت به کاربر</a>
</div>
"""
        render(self, f"سرویس {name}", body, active="/users")

    def action_service_live(self, uid, name):
        form = self.read_form()
        action = (form.get("action") or "").strip()
        user_id = int(uid)
        user = db.get_user(user_id) or {}
        service = next((s for s in user.get("services") or []
                        if str(s.get("config_name")) == name), None)
        if not service:
            return self.redirect(flash(f"/user/{uid}", "سرویس پیدا نشد.", "bad"))
        server_key = service.get("server_key") or "Server_1"
        back = f"/user/{uid}/service/{urllib.parse.quote(name)}"

        if action == "rename":
            new_name = (form.get("new_name") or "").strip()
            if not new_name or parent_invalid_name(new_name):
                return self.redirect(flash(back, "نام جدید نامعتبر است (فقط حروف انگلیسی، عدد، - و _).", "bad"))
            ok, err = xui_api.update_client(server_key, name, new_email=new_name)
            if not ok:
                return self.redirect(flash(back, f"تغییر نام در پنل انجام نشد: {err}", "bad"))
            new_link = xui_api.sub_link_for(new_name, service.get("sub_link") or "")
            db.rename_service(user_id, name, new_name)
            if new_link:
                db.update_service_fields(user_id, new_name, sub_link=new_link)
            self.notify_service_change(user_id, new_name, new_link or service.get("sub_link"), server_key)
            return self.redirect(flash(f"/user/{uid}/service/{urllib.parse.quote(new_name)}",
                                       "نام اکانت و لینک اشتراک تغییر کرد و به کاربر اطلاع داده شد."))

        if action == "volume":
            total = parse_amount(form.get("total_gb"))
            if total is None or total < 0:
                return self.redirect(flash(back, "حجم نامعتبر است.", "bad"))
            ok, err = xui_api.update_client(server_key, name, total_gb=total)
            if not ok:
                return self.redirect(flash(back, f"تغییر حجم انجام نشد: {err}", "bad"))
            self.notify_service_change(user_id, name, service.get("sub_link"), server_key)
            return self.redirect(flash(back, "حجم کل سرویس به‌روزرسانی شد."))

        if action == "volume_delta":
            delta = parse_amount(form.get("delta_gb"))
            if delta is None:
                return self.redirect(flash(back, "مقدار افزایش/کاهش نامعتبر است.", "bad"))
            client = xui_api.get_client(server_key, name) or {}
            current = int(client.get("totalGB") or 0) / (1024 ** 3)
            new_total = max(0, current + delta)
            ok, err = xui_api.update_client(server_key, name, total_gb=new_total)
            if not ok:
                return self.redirect(flash(back, f"تغییر حجم انجام نشد: {err}", "bad"))
            self.notify_service_change(user_id, name, service.get("sub_link"), server_key)
            return self.redirect(flash(back, f"حجم کل روی {new_total:g} گیگ تنظیم شد."))

        if action == "expiry_days":
            days = parse_amount(form.get("days"))
            if days is None:
                return self.redirect(flash(back, "تعداد روز نامعتبر است.", "bad"))
            expiry_ms = int((time.time() + max(0, days) * 86400) * 1000)
            ok, err = xui_api.update_client(server_key, name, expiry_ms=expiry_ms)
            if not ok:
                return self.redirect(flash(back, f"تغییر اعتبار انجام نشد: {err}", "bad"))
            self.notify_service_change(user_id, name, service.get("sub_link"), server_key)
            return self.redirect(flash(back, f"اعتبار {int(days)} روز از الان تنظیم شد."))

        if action == "expiry_date":
            raw = (form.get("date") or "").strip()
            in_days = parse_date_to_ms(raw)
            if in_days is None:
                return self.redirect(flash(back, "تاریخ نامعتبر است (نمونه: 2026-12-01).", "bad"))
            ok, err = xui_api.update_client(server_key, name, expiry_ms=in_days)
            if not ok:
                return self.redirect(flash(back, f"تغییر اعتبار انجام نشد: {err}", "bad"))
            self.notify_service_change(user_id, name, service.get("sub_link"), server_key)
            return self.redirect(flash(back, "تاریخ انقضا تنظیم شد."))

        if action == "limit_ip":
            limit = parse_amount(form.get("limit_ip"))
            if limit is None:
                return self.redirect(flash(back, "تعداد دستگاه نامعتبر است.", "bad"))
            ok, err = xui_api.update_client(server_key, name, limit_ip=int(limit))
            if not ok:
                return self.redirect(flash(back, f"تغییر تعداد دستگاه انجام نشد: {err}", "bad"))
            return self.redirect(flash(back, "تعداد دستگاه مجاز به‌روزرسانی شد."))

        if action == "enable":
            client = xui_api.get_client(server_key, name) or {}
            want = not bool(client.get("enable", True))
            ok, err = xui_api.update_client(server_key, name, enable=want)
            if not ok:
                return self.redirect(flash(back, f"تغییر وضعیت انجام نشد: {err}", "bad"))
            return self.redirect(flash(back, "وضعیت سرویس فعال شد." if want else "سرویس غیرفعال شد."))

        if action == "reset":
            ok, err = xui_api.reset_traffic(server_key, name)
            if not ok:
                return self.redirect(flash(back, f"ریست انجام نشد: {err}", "bad"))
            return self.redirect(flash(back, "مصرف سرویس ریست شد."))

        if action == "sync":
            current = xui_api.get_client(server_key, name)
            if current:
                return self.redirect(flash(back, "اطلاعات سرویس از پنل 3x-ui تازه شد؛ تغییری برای ذخیره نبود."))
            renamed = find_client_by_uuid(server_key, service.get("uuid"))
            if not renamed:
                return self.redirect(flash(back, "کلاینت با این نام و UUID در پنل 3x-ui پیدا نشد.", "bad"))
            new_link = xui_api.sub_link_for(renamed, service.get("sub_link") or "") or service.get("sub_link")
            db.rename_service(user_id, name, renamed)
            if new_link:
                db.update_service_fields(user_id, renamed, sub_link=new_link)
            self.notify_service_change(user_id, renamed, new_link, server_key)
            return self.redirect(flash(f"/user/{uid}/service/{urllib.parse.quote(renamed)}",
                                       f"نام جدید «{renamed}» از پنل 3x-ui خوانده و در ربات ذخیره شد."))

        if action == "delete":
            ok, err = xui_api.delete_client(server_key, name)
            if not ok:
                return self.redirect(flash(back, f"حذف از پنل انجام نشد: {err}", "bad"))
            db.delete_service_row(user_id, name)
            return self.redirect(flash(f"/user/{uid}", "سرویس از پنل 3x-ui و دیتابیس حذف شد."))

        return self.redirect(flash(back, "عملیات ناشناخته.", "bad"))

    def notify_service_change(self, user_id, name, sub_link, server_key):
        """اطلاع‌رسانی تغییرات سرویس به کاربر در تلگرام"""
        if not BOT_TOKEN:
            return
        client = xui_api.get_client(server_key, name) or {}
        total = int(client.get("totalGB") or 0)
        used = int(client.get("up") or 0) + int(client.get("down") or 0)
        expiry = xui_api.expiry_info(client.get("expiryTime"))
        lines = [
            "🔔 سرویس شما به‌روزرسانی شد",
            "",
            f"📛 نام کانفیگ: {name}",
            f"💾 حجم کل: {'نامحدود' if total <= 0 else xui_api.human_bytes(total)}",
            f"📊 مصرف شده: {xui_api.human_bytes(used)}",
            f"⏳ انقضا: {expiry['date']}",
        ]
        if expiry["days_left"] is not None:
            lines.append(f"📅 روزهای باقی‌مانده: {expiry['days_left']} روز")
        if sub_link:
            lines += ["", f"🔗 لینک اشتراک: {sub_link}"]
        telegram_send(user_id, "\n".join(lines))

    # ---------- user actions ----------
    def action_set_balance(self, uid):
        form = self.read_form()
        current = float((db.get_user(int(uid)) or {}).get("balance") or 0)
        if "delta" in form and form.get("delta", "").strip():
            delta = parse_amount(form.get("delta"))
            if delta is None:
                return self.redirect(flash(f"/user/{uid}", "مقدار تغییر نسبی نامعتبر است.", "bad"))
            new_balance = current + delta
        else:
            value = parse_amount(form.get("balance"))
            if value is None:
                return self.redirect(flash(f"/user/{uid}", "موجودی وارد‌شده نامعتبر است.", "bad"))
            new_balance = value
        new_balance = max(0.0, new_balance)
        db.set_balance(int(uid), new_balance)
        db.add_transaction_row(int(uid), "admin_adjustment", new_balance,
                               f"تنظیم موجودی از پنل وب (از {money(current)} به {money(new_balance)})")
        self.redirect(flash(f"/user/{uid}", f"موجودی روی {money(new_balance)} تومان ذخیره شد."))

    def action_set_fields(self, uid):
        form = self.read_form()
        fields = {}

        first_name = (form.get("first_name") or "").strip()
        fields["first_name"] = first_name or None
        username = (form.get("username") or "").strip().lstrip("@")
        fields["username"] = username or None
        fields["notes"] = form.get("notes", "")

        raw_percent = (form.get("referral_percent") or "").strip()
        if raw_percent == "":
            fields["referral_percent"] = None
        else:
            percent = parse_amount(raw_percent)
            if percent is None:
                return self.redirect(flash(f"/user/{uid}", "درصد رفرال نامعتبر است.", "bad"))
            fields["referral_percent"] = max(0.0, min(100.0, percent))

        earnings = parse_amount(form.get("referral_earnings"))
        if earnings is None:
            return self.redirect(flash(f"/user/{uid}", "درآمد رفرال نامعتبر است.", "bad"))
        fields["referral_earnings"] = max(0.0, earnings)

        count = parse_amount(form.get("referrals_count"))
        fields["referrals_count"] = int(max(0, count if count is not None else 0))

        raw_ref = (form.get("referral_by") or "").strip()
        if raw_ref == "":
            fields["referral_by"] = None
        else:
            ref = parse_amount(raw_ref)
            if ref is None:
                return self.redirect(flash(f"/user/{uid}", "شناسه رفرال‌دهنده نامعتبر است.", "bad"))
            fields["referral_by"] = int(ref)

        before = db.get_user(int(uid)) or {}
        old_percent = before.get("referral_percent")
        db.set_user_fields(int(uid), **fields)
        new_percent = fields.get("referral_percent")
        if normalize_percent(old_percent) != normalize_percent(new_percent):
            self.notify_referral_percent(int(uid), new_percent)
        self.redirect(flash(f"/user/{uid}", "فیلدهای کاربر ذخیره شد."))

    def notify_referral_percent(self, user_id: int, percent):
        """اطلاع‌رسانی تغییر درصد رفرال به کاربر در تلگرام"""
        if not BOT_TOKEN:
            return
        if percent is None:
            text = ("🔔 درصد پورسانت رفرال شما از طرف مدیریت تغییر کرد.\n\n"
                    "از این به بعد طبق درصد پیش‌فرض ربات محاسبه می‌شود.")
        else:
            text = (f"🔔 درصد پورسانت رفرال شما از طرف مدیریت تغییر کرد.\n\n"
                    f"📈 درصد جدید: {percent:g}%")
        telegram_send(user_id, text)

    def action_settle(self, uid):
        user = db.get_user(int(uid)) or {}
        balance = float(user.get("balance") or 0)
        db.set_balance(int(uid), 0.0)
        db.add_transaction_row(int(uid), "withdrawal", balance,
                               "تسویه از پنل وب - صفر شدن موجودی")
        self.redirect(flash(f"/user/{uid}", "موجودی تسویه و صفر شد."))

    def action_reset_trial(self, uid):
        db.delete_free_trial(int(uid))
        self.redirect(flash(f"/user/{uid}", "سابقهٔ تست رایگان پاک شد."))

    def action_delete_user(self, uid):
        try:
            db.delete_user(int(uid))
        except (TypeError, ValueError):
            pass
        self.redirect(flash("/users", "کاربر حذف شد."))

    def action_add_user(self):
        form = self.read_form()
        raw = (form.get("user_id") or "").strip().lstrip("@")
        parsed = parse_amount(raw)
        if parsed is None:
            return self.redirect(flash("/users", "شناسهٔ کاربر نامعتبر است.", "bad"))
        user_id = int(parsed)
        balance = parse_amount(form.get("balance"), 0.0) or 0.0
        created = db.add_user_row(user_id, balance)
        message = "کاربر ساخته شد." if created else "این کاربر از قبل وجود داشت."
        self.redirect(flash(f"/user/{user_id}", message))

    def action_add_service(self, uid):
        form = self.read_form()
        config_name = (form.get("config_name") or "").strip()
        if not config_name:
            return self.redirect(flash(f"/user/{uid}", "نام کانفیگ لازم است.", "bad"))
        db.add_service_row(int(uid), config_name,
                           (form.get("sub_link") or "").strip(),
                           (form.get("uuid") or "").strip(),
                           (form.get("internal_key") or "").strip(),
                           (form.get("server_key") or "Server_1").strip())
        self.redirect(flash(f"/user/{uid}", "سرویس ذخیره شد."))

    def action_update_service(self, uid):
        form = self.read_form()
        old_name = (form.get("config_name") or "").strip()
        if not old_name:
            return self.redirect(flash(f"/user/{uid}", "سرویس مشخص نشد.", "bad"))
        new_name = (form.get("new_name") or "").strip()
        if new_name and new_name != old_name:
            db.rename_service(int(uid), old_name, new_name)
            target = new_name
        else:
            target = old_name
        db.update_service_fields(int(uid), target,
                                 sub_link=(form.get("sub_link") or "").strip(),
                                 uuid=(form.get("uuid") or "").strip(),
                                 internal_key=(form.get("internal_key") or "").strip(),
                                 server_key=(form.get("server_key") or "").strip())
        self.redirect(flash(f"/user/{uid}", "جزئیات سرویس ذخیره شد."))

    def action_delete_service(self, uid):
        form = self.read_form()
        config_name = (form.get("config_name") or "").strip()
        if config_name:
            db.delete_service_row(int(uid), config_name)
        self.redirect(flash(f"/user/{uid}", "سرویس حذف شد."))

    def action_delete_transaction(self, tx_id):
        db.delete_transaction(tx_id)
        self.redirect(flash("/transactions", "تراکنش حذف شد."))

    # ---------- receipts ----------
    def page_receipts(self, qs):
        receipts = db.load_pending_receipts()
        users = db.load_users()
        status_filter = qs.get("status") or "all"
        rows = ""
        for rid in sorted(receipts, reverse=True):
            r = receipts[rid]
            status = r.get("status") or "pending"
            if status_filter != "all" and status != status_filter:
                continue
            user = users.get(str(r.get("user_id"))) or {}
            who = f"@{user['username']}" if user.get("username") else (user.get("first_name") or "—")
            actions = ""
            if status == "pending":
                actions = (
                    f"<form class='inline' method='post' action='/receipts/{rid}/approve'>"
                    f"<button type='submit' class='mini'>تأیید</button></form> "
                    f"<form class='inline' method='post' action='/receipts/{rid}/reject'>"
                    f"<button type='submit' class='red mini'>رد</button></form>"
                )
            rows += (
                f'<tr><td class="muted small">{rid}</td>'
                f'<td><a href="/user/{r.get("user_id")}">{r.get("user_id")}</a><br>'
                f'<span class="muted small">{html.escape(str(who))}</span></td>'
                f'<td>{money(r.get("amount_toman"))}</td>'
                f'<td><span class="pill {status}">{html.escape(status)}</span></td>'
                f'<td class="muted small">{html.escape(str(r.get("timestamp") or "")[:19].replace("T", " "))}</td>'
                f'<td class="muted small">{html.escape(str(r.get("processed_by") or "—"))}</td>'
                f'<td>{actions}</td></tr>'
            )
        if not rows:
            rows = "<tr><td colspan='7' class='muted'>رسیدی با این وضعیت نیست.</td></tr>"
        body = f"""
{self.flash_from_query(qs)}
<h1>رسیدهای کارت به کارت</h1>
<form class="row" method="get" action="/receipts">
  <select name="status">
    <option value="all"{' selected' if status_filter == 'all' else ''}>همه</option>
    <option value="pending"{' selected' if status_filter == 'pending' else ''}>در انتظار</option>
    <option value="approved"{' selected' if status_filter == 'approved' else ''}>تأییدشده</option>
    <option value="rejected"{' selected' if status_filter == 'rejected' else ''}>رد‌شده</option>
  </select>
  <button type="submit">فیلتر</button>
</form>
<div class="tablewrap"><table>
<tr><th>شناسه</th><th>کاربر</th><th>مبلغ</th><th>وضعیت</th><th>زمان</th><th>پردازش‌کننده</th><th>عملیات</th></tr>
{rows}</table></div>
<p class="muted small" style="margin-top:12px">تأیید از پنل، موجودی کاربر را افزایش می‌دهد و تراکنش واریز ثبت می‌کند.</p>
"""
        render(self, "رسیدها", body, active="/receipts")

    def action_receipt(self, rid, action):
        receipts = db.load_pending_receipts()
        receipt = receipts.get(rid)
        message = "رسید پیدا نشد."
        kind = "bad"
        if receipt and (receipt.get("status") or "pending") == "pending":
            user_id = receipt.get("user_id")
            if action == "approve":
                amount = float(receipt.get("amount_toman") or 0)
                user = db.get_user(int(user_id)) or {}
                db.set_balance(int(user_id), float(user.get("balance") or 0) + amount)
                db.add_transaction_row(int(user_id), "deposit", amount,
                                       "واریز از طریق کارت به کارت - تأیید از پنل وب")
                receipt["status"] = "approved"
                message = "رسید تأیید و موجودی اضافه شد."
            else:
                receipt["status"] = "rejected"
                message = "رسید رد شد."
            receipt["processed_at"] = datetime.datetime.now().isoformat()
            receipts[rid] = receipt
            db.save_pending_receipts(receipts)
            kind = "ok"
        self.redirect(flash("/receipts", message, kind))

    def action_receipt_by_form(self, approve: bool):
        form = self.read_form()
        rid = (form.get("receipt_id") or "").strip()
        if rid:
            return self.action_receipt(rid, "approve" if approve else "reject")
        self.redirect("/receipts")

    # ---------- transactions / services ----------
    def page_transactions(self, qs):
        tx_type = qs.get("type") or "all"
        search = (qs.get("q") or "").strip().lower()
        rows = ""
        count = 0
        for tx in db.recent_transactions(500):
            if tx_type != "all" and tx.get("type") != tx_type:
                continue
            if search:
                hay = " ".join([str(tx.get("user_id")), str(tx.get("description") or ""),
                                str(tx.get("amount"))]).lower()
                if search not in hay:
                    continue
            count += 1
            rows += (
                f'<tr><td><a href="/user/{tx["user_id"]}">{tx["user_id"]}</a></td>'
                f'<td>{html.escape(TX_LABELS.get(tx["type"], tx["type"] or ""))}</td>'
                f'<td>{money(tx["amount"])}</td>'
                f'<td class="wrap">{html.escape(tx["description"] or "")}</td>'
                f'<td class="muted small">{html.escape((tx["timestamp"] or "")[:19].replace("T", " "))}</td>'
                f'<td><form class="inline" method="post" action="/transactions/{html.escape(str(tx["id"]))}/delete" '
                f'onsubmit="return confirm(\'حذف شود؟\')"><button class="red mini">حذف</button></form></td></tr>'
            )
        if not rows:
            rows = "<tr><td colspan='6' class='muted'>تراکنشی نیست.</td></tr>"
        options = "".join(
            f'<option value="{key}"{" selected" if tx_type == key else ""}>{label}</option>'
            for key, label in [("all", "همه")] + list(TX_LABELS.items())
        )
        body = f"""
{self.flash_from_query(qs)}
<h1>تراکنش‌ها ({count})</h1>
<form class="row" method="get" action="/transactions">
  <select name="type">{options}</select>
  <input type="text" name="q" value="{html.escape(qs.get('q') or '')}" placeholder="جستجو در توضیح، مبلغ یا شناسه کاربر">
  <button type="submit">فیلتر</button>
  <a href="/transactions" class="muted small">حذف فیلتر</a>
</form>
<div class="tablewrap"><table>
<tr><th>کاربر</th><th>نوع</th><th>مبلغ</th><th>توضیح</th><th>زمان</th><th></th></tr>{rows}</table></div>
"""
        render(self, "تراکنش‌ها", body, active="/transactions")

    def page_services(self, qs):
        search = (qs.get("q") or "").strip().lower()
        users = db.load_users()
        rows = ""
        count = 0
        for uid, data in users.items():
            for s in data.get("services") or []:
                hay = " ".join([str(s.get("config_name")), str(s.get("internal_key")),
                                str(s.get("server_key")), str(uid)]).lower()
                if search and search not in hay:
                    continue
                count += 1
                rows += (
                    f'<tr><td><a href="/user/{uid}/service/{urllib.parse.quote(str(s.get("config_name")))}">'
                    f'{html.escape(str(s.get("config_name")))}</a></td>'
                    f'<td><a href="/user/{uid}">{uid}</a></td>'
                    f'<td>{html.escape(str(s.get("internal_key") or ""))}</td>'
                    f'<td>{html.escape(str(s.get("server_key") or ""))}</td>'
                    f'<td class="wrap muted small">{html.escape(str(s.get("sub_link") or ""))}</td>'
                    f'<td class="muted small">{html.escape(str(s.get("purchase_date") or "")[:19].replace("T", " "))}</td></tr>'
                )
        if not rows:
            rows = "<tr><td colspan='6' class='muted'>سرویسی نیست.</td></tr>"
        body = f"""
<h1>همهٔ سرویس‌ها ({count})</h1>
<form class="row" method="get" action="/services">
  <input type="text" name="q" value="{html.escape(qs.get('q') or '')}" placeholder="نام کانفیگ، پلن، سرور یا شناسه کاربر">
  <button type="submit">جستجو</button>
  <a href="/services" class="muted small">حذف فیلتر</a>
</form>
<div class="tablewrap"><table>
<tr><th>نام کانفیگ</th><th>کاربر</th><th>پلن</th><th>سرور</th><th>لینک اشتراک</th><th>تاریخ خرید</th></tr>
{rows}</table></div>
"""
        render(self, "سرویس‌ها", body, active="/services")

    # ---------- announce ----------
    def page_announce(self, result: str = ""):
        users_count = db.stats()["users"]
        warning = "" if BOT_TOKEN else (
            '<div class="notice bad">توکن ربات در دسترس نیست؛ پنل را همراه ربات اجرا کن '
            '(start-card.bat / start-zarinpal.bat) یا متغیر BOT_TOKEN را ست کن.</div>'
        )
        body = f"""
<h1>اعلان همگانی</h1>
{warning}{result}
<div class="box">
  <form method="post" action="/announce">
    <p class="muted small">پیام برای {users_count} کاربر ربات ارسال می‌شود. متن به صورت ساده (بدون Markdown) ارسال می‌گردد.</p>
    <textarea name="text" rows="7" style="width:100%"
              placeholder="متن اعلان..."></textarea>
    <div class="row" style="margin:10px 0 0">
      <button type="submit">ارسال به همهٔ کاربران</button>
      <span class="muted small">ارسال مرحله‌به‌مرحله انجام می‌شود؛ صفحه تا پایان باز می‌ماند.</span>
    </div>
  </form>
</div>
"""
        render(self, "اعلان", body, active="/announce")

    def action_announce(self):
        form = self.read_form()
        text = (form.get("text") or "").strip()
        if not text:
            return self.page_announce('<div class="notice bad">متن اعلان خالی است.</div>')
        if not BOT_TOKEN:
            return self.page_announce('<div class="notice bad">توکن ربات موجود نیست.</div>')
        sent, failed = 0, 0
        for user_id in db.load_users():
            if telegram_send(user_id, text):
                sent += 1
            else:
                failed += 1
            time.sleep(0.05)
        result = (f'<div class="notice ok">✅ ارسال شد به {sent} کاربر'
                  f'{" | ❌ ناموفق: " + str(failed) if failed else ""}</div>')
        self.page_announce(result)

    def log_message(self, fmt, *args):
        sys_stderr_write("%s - %s\n" % (self.address_string(), fmt % args))


def sys_stderr_write(text: str) -> None:
    import sys
    sys.stderr.write(text)


def start_panel_thread(host: str = None, port: int = None, bot_token: str = None):
    """
    اجرای پنل در یک ترد پس‌زمینه (همراه ربات).
    اگر پورت در اشغال باشد، فقط پیام می‌دهد و ربات را متوقف نمی‌کند.
    """
    global BOT_TOKEN, BOT_USERNAME
    if bot_token:
        BOT_TOKEN = bot_token
    BOT_USERNAME = fetch_bot_username(BOT_TOKEN)
    host = host or HOST
    port = port or PORT
    db.init()
    try:
        server = PanelServer((host, port), Handler)
    except OSError as exc:
        print(f"[panel] not started, port {port} is not available: {exc}")
        return None
    thread = threading.Thread(target=server.serve_forever, name="admin-panel", daemon=True)
    thread.start()
    print(f"[panel] admin panel is running: http://127.0.0.1:{port}")
    if LOCKED:
        print('[panel] NOTE: panel is LOCKED (PANEL_LOCK = "1"). Set it to "0" in admin_panel.py to unlock.')
    return server


def main():
    global BOT_USERNAME
    db.init()
    BOT_USERNAME = fetch_bot_username(BOT_TOKEN)
    if LOCKED:
        print('Panel is LOCKED (PANEL_LOCK = "1"). Set PANEL_LOCK = "0" in admin_panel.py to unlock.')
    server = PanelServer((HOST, PORT), Handler)
    print(f"Admin panel: http://127.0.0.1:{PORT}  (db: {db.DB_PATH})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
