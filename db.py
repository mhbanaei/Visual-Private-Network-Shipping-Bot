"""
لایهٔ دادهٔ مشترک ربات و پنل وب (SQLite)

ربات تلگرام و پنل وب هر دو از این فایل به عنوان تنها منبع داده استفاده می‌کنند،
پس هر تغییری در یکی بلافاصله در دیگری دیده می‌شود.

داده‌های قدیمی JSON فقط یک‌بار (وقتی دیتابیس خالی است) مهاجرت می‌شوند و
فایل‌های JSON دست‌نخورده باقی می‌مانند.
"""

import datetime
import json
import os
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "botdata.db")

USERS_FILE = os.path.join(BASE_DIR, "users.json")
PENDING_RECEIPTS_FILE = os.path.join(BASE_DIR, "pending_receipts.json")
TRANSACTION_HISTORY_FILE = os.path.join(BASE_DIR, "transaction_history.json")
FREE_TRIAL_USERS_FILE = os.path.join(BASE_DIR, "free_trial_users.json")
REFERRAL_DATA_FILE = os.path.join(BASE_DIR, "referral_data.json")

_init_lock = threading.RLock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    balance          REAL    NOT NULL DEFAULT 0,
    referral_by      INTEGER,
    referral_earnings REAL   NOT NULL DEFAULT 0,
    referrals_count  INTEGER NOT NULL DEFAULT 0,
    referral_percent REAL,
    join_date        TEXT,
    notes            TEXT    NOT NULL DEFAULT '',
    created_at       TEXT,
    username         TEXT,
    first_name       TEXT
);

CREATE TABLE IF NOT EXISTS services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    config_name   TEXT    NOT NULL,
    sub_link      TEXT,
    uuid          TEXT,
    internal_key  TEXT,
    server_key    TEXT,
    purchase_date TEXT,
    UNIQUE(user_id, config_name)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    type        TEXT,
    amount      REAL,
    description TEXT,
    timestamp   TEXT,
    admin_id    INTEGER
);

CREATE TABLE IF NOT EXISTS pending_receipts (
    id                TEXT PRIMARY KEY,
    user_id           INTEGER NOT NULL,
    amount_toman      REAL,
    receipt_file_id   TEXT,
    timestamp         TEXT,
    status            TEXT DEFAULT 'pending',
    processed_by      INTEGER,
    processed_at      TEXT,
    admin_message_ids TEXT
);

CREATE TABLE IF NOT EXISTS free_trials (
    user_id   INTEGER PRIMARY KEY,
    used_date TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_services_user   ON services(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_user         ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_time         ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_receipt_status  ON pending_receipts(status);
"""


def connect() -> sqlite3.Connection:
    """اتصال جدید به دیتابیس (هر عملیات یک اتصال کوتاه)"""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, ValueError):
        return default


def init() -> None:
    """ساخت جدول‌ها و مهاجرت یک‌بارهٔ داده‌های JSON"""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        # علامت‌گذاری قبل از مهاجرت تا فراخوانی‌های تو‌در‌تو (save_users و…) دوباره init نکنند
        _initialized = True
        conn = connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
            # ستون‌های جدید برای دیتابیس‌های قدیمی
            for ddl in (
                "ALTER TABLE users ADD COLUMN referral_percent REAL",
                "ALTER TABLE users ADD COLUMN username TEXT",
                "ALTER TABLE users ADD COLUMN first_name TEXT",
            ):
                try:
                    conn.execute(ddl)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            empty = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            if empty:
                _migrate_from_json(conn)
        except Exception:
            _initialized = False
            raise
        finally:
            conn.close()


def _migrate_from_json(conn) -> None:
    users = _read_json(USERS_FILE, {})
    if users:
        save_users(users)
    receipts = _read_json(PENDING_RECEIPTS_FILE, {})
    if receipts:
        save_pending_receipts(receipts)
    history = _read_json(TRANSACTION_HISTORY_FILE, {})
    if history:
        save_transaction_history(history)
    trials = _read_json(FREE_TRIAL_USERS_FILE, {})
    if trials:
        save_free_trial_users(trials)
    referral = _read_json(REFERRAL_DATA_FILE, None)
    if referral:
        save_referral_data(referral)


# ------------------------------------------------------------
# کاربران و سرویس‌ها
# ------------------------------------------------------------

def load_users() -> dict:
    init()
    conn = connect()
    try:
        users = {}
        for row in conn.execute("SELECT * FROM users"):
            users[str(row["user_id"])] = {
                "balance": row["balance"] or 0.0,
                "services": [],
                "referral_by": row["referral_by"],
                "referral_earnings": row["referral_earnings"] or 0.0,
                "referrals_count": row["referrals_count"] or 0,
                "referral_percent": row["referral_percent"],
                "join_date": row["join_date"],
                "notes": row["notes"] or "",
                "created_at": row["created_at"],
                "username": row["username"],
                "first_name": row["first_name"],
            }
        for row in conn.execute("SELECT * FROM services ORDER BY id"):
            uid = str(row["user_id"])
            if uid not in users:
                continue
            users[uid]["services"].append({
                "config_name": row["config_name"],
                "sub_link": row["sub_link"],
                "uuid": row["uuid"],
                "internal_key": row["internal_key"],
                "server_key": row["server_key"],
                "purchase_date": row["purchase_date"],
            })
        return users
    finally:
        conn.close()


def save_users(users: dict) -> None:
    init()
    conn = connect()
    try:
        with conn:
            for str_user_id, data in users.items():
                try:
                    user_id = int(str_user_id)
                except (TypeError, ValueError):
                    continue
                conn.execute(
                    """INSERT INTO users (user_id, balance, referral_by, referral_earnings,
                                          referrals_count, referral_percent, join_date, notes, created_at,
                                          username, first_name)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           balance=excluded.balance,
                           referral_by=excluded.referral_by,
                           referral_earnings=excluded.referral_earnings,
                           referrals_count=excluded.referrals_count,
                           referral_percent=excluded.referral_percent,
                           join_date=excluded.join_date,
                           notes=excluded.notes,
                           created_at=excluded.created_at,
                           username=COALESCE(excluded.username, users.username),
                           first_name=COALESCE(excluded.first_name, users.first_name)""",
                    (
                        user_id,
                        data.get("balance", 0.0) or 0.0,
                        data.get("referral_by"),
                        data.get("referral_earnings", 0.0) or 0.0,
                        data.get("referrals_count", 0) or 0,
                        data.get("referral_percent"),
                        data.get("join_date"),
                        data.get("notes", "") or "",
                        data.get("created_at"),
                        data.get("username"),
                        data.get("first_name"),
                    ),
                )
                services = data.get("services", []) or []
                conn.execute("DELETE FROM services WHERE user_id=?", (user_id,))
                for svc in services:
                    conn.execute(
                        """INSERT OR REPLACE INTO services
                           (user_id, config_name, sub_link, uuid, internal_key, server_key, purchase_date)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            user_id,
                            svc.get("config_name"),
                            svc.get("sub_link"),
                            svc.get("uuid"),
                            svc.get("internal_key"),
                            svc.get("server_key"),
                            svc.get("purchase_date"),
                        ),
                    )
    finally:
        conn.close()


def get_user(user_id: int):
    """یک کاربر به شکل دیکشنری (یا None)"""
    users = load_users()
    return users.get(str(user_id))


def set_balance(user_id: int, new_balance: float) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute("UPDATE users SET balance=? WHERE user_id=?", (float(new_balance), int(user_id)))
            return cur.rowcount > 0
    finally:
        conn.close()


# ------------------------------------------------------------
# تراکنش‌ها
# ------------------------------------------------------------

def load_transaction_history() -> dict:
    init()
    conn = connect()
    try:
        history = {}
        for row in conn.execute("SELECT * FROM transactions ORDER BY timestamp"):
            history.setdefault(str(row["user_id"]), []).append({
                "id": row["id"],
                "type": row["type"],
                "amount": row["amount"],
                "description": row["description"],
                "timestamp": row["timestamp"],
                "admin_id": row["admin_id"],
            })
        return history
    finally:
        conn.close()


def save_transaction_history(history: dict) -> None:
    init()
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM transactions")
            for str_user_id, items in history.items():
                try:
                    user_id = int(str_user_id)
                except (TypeError, ValueError):
                    continue
                for tx in items:
                    conn.execute(
                        """INSERT OR REPLACE INTO transactions
                           (id, user_id, type, amount, description, timestamp, admin_id)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            str(tx.get("id")),
                            user_id,
                            tx.get("type"),
                            tx.get("amount"),
                            tx.get("description"),
                            tx.get("timestamp"),
                            tx.get("admin_id"),
                        ),
                    )
    finally:
        conn.close()


def add_transaction_row(user_id: int, tx_type: str, amount: float, description: str = "", admin_id=None) -> str:
    """درج مستقیم یک تراکنش بدون بازنویسی کل تاریخچه"""
    init()
    tx_id = str(int(datetime.datetime.now().timestamp() * 1000))
    conn = connect()
    try:
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO transactions
                   (id, user_id, type, amount, description, timestamp, admin_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (tx_id, int(user_id), tx_type, amount, description,
                 datetime.datetime.now().isoformat(), admin_id),
            )
    finally:
        conn.close()
    return tx_id


def recent_transactions(limit: int = 50) -> list:
    init()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ------------------------------------------------------------
# رسیدهای در انتظار
# ------------------------------------------------------------

def load_pending_receipts() -> dict:
    init()
    conn = connect()
    try:
        out = {}
        for row in conn.execute("SELECT * FROM pending_receipts ORDER BY timestamp"):
            try:
                admin_ids = json.loads(row["admin_message_ids"] or "{}")
            except ValueError:
                admin_ids = {}
            out[row["id"]] = {
                "user_id": row["user_id"],
                "amount_toman": row["amount_toman"],
                "receipt_file_id": row["receipt_file_id"],
                "timestamp": row["timestamp"],
                "status": row["status"],
                "processed_by": row["processed_by"],
                "processed_at": row["processed_at"],
                "admin_message_ids": admin_ids,
            }
        return out
    finally:
        conn.close()


def save_pending_receipts(receipts: dict) -> None:
    init()
    conn = connect()
    try:
        with conn:
            for rid, r in receipts.items():
                conn.execute(
                    """INSERT INTO pending_receipts
                       (id, user_id, amount_toman, receipt_file_id, timestamp, status,
                        processed_by, processed_at, admin_message_ids)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                           status=excluded.status,
                           processed_by=excluded.processed_by,
                           processed_at=excluded.processed_at,
                           admin_message_ids=excluded.admin_message_ids""",
                    (
                        str(rid),
                        r.get("user_id"),
                        r.get("amount_toman"),
                        r.get("receipt_file_id"),
                        r.get("timestamp"),
                        r.get("status", "pending"),
                        r.get("processed_by"),
                        r.get("processed_at"),
                        json.dumps(r.get("admin_message_ids") or {}, ensure_ascii=False),
                    ),
                )
    finally:
        conn.close()


# ------------------------------------------------------------
# تست رایگان
# ------------------------------------------------------------

def load_free_trial_users() -> dict:
    init()
    conn = connect()
    try:
        return {
            str(row["user_id"]): {"used_date": row["used_date"], "user_id": row["user_id"]}
            for row in conn.execute("SELECT * FROM free_trials")
        }
    finally:
        conn.close()


def save_free_trial_users(users: dict) -> None:
    init()
    conn = connect()
    try:
        with conn:
            for str_user_id, data in users.items():
                try:
                    user_id = int(str_user_id)
                except (TypeError, ValueError):
                    continue
                conn.execute(
                    "INSERT INTO free_trials (user_id, used_date) VALUES (?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET used_date=excluded.used_date",
                    (user_id, (data or {}).get("used_date")),
                )
    finally:
        conn.close()


# ------------------------------------------------------------
# رفرال (داده‌های تکمیلی)
# ------------------------------------------------------------

def load_referral_data() -> dict:
    init()
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM kv WHERE key='referral_data'").fetchone()
        if not row:
            return {"referrals": {}, "earnings_history": {}}
        data = json.loads(row["value"])
        data.setdefault("referrals", {})
        data.setdefault("earnings_history", {})
        return data
    except ValueError:
        return {"referrals": {}, "earnings_history": {}}
    finally:
        conn.close()


def save_referral_data(data: dict) -> None:
    init()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES ('referral_data', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(data, ensure_ascii=False),),
            )
    finally:
        conn.close()


def get_kv(key: str, default=None):
    """خواندن یک مقدار JSON از جدول کلید/مقدار (وضعیت یادآوری‌ها و…)"""
    init()
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM kv WHERE key=?", (str(key),)).fetchone()
        if not row:
            return default
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return default
    finally:
        conn.close()


def set_kv(key: str, value) -> None:
    """ذخیرهٔ یک مقدار JSON در جدول کلید/مقدار"""
    init()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), json.dumps(value, ensure_ascii=False)),
            )
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """حذف کامل کاربر و داده‌های مرتبط"""
    init()
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM services WHERE user_id=?", (int(user_id),))
            conn.execute("DELETE FROM transactions WHERE user_id=?", (int(user_id),))
            conn.execute("DELETE FROM free_trials WHERE user_id=?", (int(user_id),))
            cur = conn.execute("DELETE FROM users WHERE user_id=?", (int(user_id),))
            return cur.rowcount > 0
    finally:
        conn.close()


def add_user_row(user_id: int, balance: float = 0.0) -> bool:
    """ساخت کاربر جدید از پنل (اگر وجود نداشته باشد)"""
    init()
    now = datetime.datetime.now().isoformat()
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO users (user_id, balance, referral_earnings, referrals_count,
                                      join_date, notes, created_at)
                   VALUES (?,?,0,0,?,'',?)
                   ON CONFLICT(user_id) DO NOTHING""",
                (int(user_id), float(balance), now, now),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def add_service_row(user_id: int, config_name: str, sub_link: str = "", uuid: str = "",
                    internal_key: str = "", server_key: str = "") -> None:
    """افزودن/به‌روزرسانی سرویس یک کاربر (از پنل)"""
    init()
    conn = connect()
    try:
        with conn:
            conn.execute(
                """INSERT INTO services (user_id, config_name, sub_link, uuid, internal_key, server_key, purchase_date)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(user_id, config_name) DO UPDATE SET
                       sub_link=excluded.sub_link,
                       uuid=excluded.uuid,
                       internal_key=excluded.internal_key,
                       server_key=excluded.server_key""",
                (int(user_id), config_name, sub_link, uuid, internal_key, server_key,
                 datetime.datetime.now().isoformat()),
            )
    finally:
        conn.close()


def delete_service_row(user_id: int, config_name: str) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM services WHERE user_id=? AND config_name=?",
                (int(user_id), config_name),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


USER_EDITABLE_FIELDS = (
    "balance", "referral_by", "referral_earnings", "referrals_count",
    "referral_percent", "notes", "username", "first_name", "join_date",
)


def set_user_fields(user_id: int, **fields) -> bool:
    """ویرایش مستقیم فیلدهای کاربر از پنل (فقط فیلدهای مجاز)"""
    init()
    updates = {k: v for k, v in fields.items() if k in USER_EDITABLE_FIELDS}
    if not updates:
        return False
    placeholders = ", ".join(f"{k}=?" for k in updates)
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                f"UPDATE users SET {placeholders} WHERE user_id=?",
                list(updates.values()) + [int(user_id)],
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def touch_profile(user_id: int, username=None, first_name=None) -> None:
    """ثبت/به‌روزرسانی نام و یوزرنیم تلگرام کاربر"""
    init()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, int(user_id)),
            )
    finally:
        conn.close()


def delete_transactions(tx_ids) -> int:
    """حذف چند تراکنش با هم؛ تعداد حذف‌شده‌ها را برمی‌گرداند"""
    ids = [str(x) for x in (tx_ids or []) if str(x).strip()]
    if not ids:
        return 0
    init()
    conn = connect()
    try:
        with conn:
            placeholders = ",".join("?" for _ in ids)
            cur = conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", ids)
            return cur.rowcount
    finally:
        conn.close()


def delete_transaction(tx_id: str) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute("DELETE FROM transactions WHERE id=?", (str(tx_id),))
            return cur.rowcount > 0
    finally:
        conn.close()


def delete_free_trial(user_id: int) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute("DELETE FROM free_trials WHERE user_id=?", (int(user_id),))
            return cur.rowcount > 0
    finally:
        conn.close()


def update_service_fields(user_id: int, config_name: str, **fields) -> bool:
    """ویرایش جزئیات یک سرویس موجود"""
    init()
    allowed = ("sub_link", "uuid", "internal_key", "server_key", "purchase_date")
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    placeholders = ", ".join(f"{k}=?" for k in updates)
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                f"UPDATE services SET {placeholders} WHERE user_id=? AND config_name=?",
                list(updates.values()) + [int(user_id), config_name],
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def rename_service(user_id: int, old_name: str, new_name: str) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE services SET config_name=? WHERE user_id=? AND config_name=?",
                (new_name, int(user_id), old_name),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def set_referral_percent(user_id: int, percent) -> bool:
    init()
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE users SET referral_percent=? WHERE user_id=?", (percent, int(user_id))
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def zero_referral_earnings(user_id: int) -> None:
    init()
    conn = connect()
    try:
        with conn:
            conn.execute("UPDATE users SET referral_earnings=0 WHERE user_id=?", (int(user_id),))
    finally:
        conn.close()


# ------------------------------------------------------------
# آمار کلی برای پنل
# ------------------------------------------------------------

def stats() -> dict:
    init()
    conn = connect()
    try:
        users = conn.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM users").fetchone()
        services = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM pending_receipts WHERE status='pending'").fetchone()[0]
        today = datetime.date.today().isoformat()
        today_tx = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE timestamp LIKE ?", (today + "%",)
        ).fetchone()[0]
        today_revenue = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions "
            "WHERE type IN ('purchase','renewal') AND timestamp LIKE ?", (today + "%",)
        ).fetchone()[0]
        return {
            "users": users[0],
            "total_balance": users[1],
            "services": services,
            "pending_receipts": pending,
            "today_transactions": today_tx,
            "today_revenue": today_revenue,
        }
    finally:
        conn.close()
