# -*- coding: utf-8 -*-
"""
База данных SQLite для бота продаж и подписок.
"""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "sales.db")
ADMIN_IDS = [7116116919, 1107097183]
OWNER_ID = 7116116919

try:
    import config
    if hasattr(config, "DB_FILE"):
        DB_FILE = config.DB_FILE
    if hasattr(config, "ADMIN_IDS"):
        ADMIN_IDS = config.ADMIN_IDS
    if hasattr(config, "OWNER_ID"):
        OWNER_ID = config.OWNER_ID
except Exception:
    pass


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Подстраховка: если таблица создавалась без колонки is_admin
        try:
            db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                plan TEXT,
                months INTEGER,
                amount_rub REAL,
                amount_stars INTEGER,
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bot_id TEXT,
                bot_username TEXT,
                bot_token TEXT,
                plan TEXT,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        # Сразу делаем владельца админом в БД
        db.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin) VALUES (?, 'Bonzayka', 1)", (config.OWNER_ID,))
        db.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (config.OWNER_ID,))
        db.commit()


def upsert_user(user_id: int, username: str = "", first_name: str = "") -> None:
    admin_val = 1 if user_id in config.ADMIN_IDS or user_id == config.OWNER_ID else 0
    with _conn() as db:
        db.execute("""
            INSERT INTO users (user_id, username, first_name, is_admin)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_admin = CASE WHEN excluded.is_admin = 1 THEN 1 ELSE users.is_admin END
        """, (user_id, username or "", first_name or "", admin_val))
        db.commit()


def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS or user_id == OWNER_ID:
        return True
    with _conn() as db:
        cur = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row["is_admin"])


def set_admin(user_id: int, status: int = 1) -> None:
    with _conn() as db:
        db.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin) VALUES (?, '', ?)", (user_id, status))
        db.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (status, user_id))
        db.commit()


def create_order(order_id: str, user_id: int, plan: str, months: int,
                 amount_rub: float, amount_stars: int, payment_method: str) -> None:
    with _conn() as db:
        db.execute("""
            INSERT INTO orders (order_id, user_id, plan, months, amount_rub, amount_stars, payment_method, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (order_id, user_id, plan, months, amount_rub, amount_stars, payment_method))
        db.commit()


def get_order(order_id: str) -> dict | None:
    with _conn() as db:
        cur = db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def mark_order_paid(order_id: str) -> bool:
    with _conn() as db:
        cur = db.execute("SELECT * FROM orders WHERE order_id = ? AND status = 'pending'", (order_id,))
        row = cur.fetchone()
        if not row:
            return False
        db.execute("UPDATE orders SET status = 'paid' WHERE order_id = ?", (order_id,))
        db.commit()
        return True


def add_or_extend_sub(user_id: int, plan: str, months: int,
                      bot_token: str = "", bot_username: str = "", bot_id: str = "") -> dict:
    now = datetime.now()
    days = months * 30

    with _conn() as db:
        cur = db.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        row = cur.fetchone()

        if row:
            cur_end = datetime.fromisoformat(row["end_date"])
            start_point = cur_end if cur_end > now else now
            new_end = start_point + timedelta(days=days)
            b_id = bot_id or row["bot_id"]
            b_uname = bot_username or row["bot_username"]
            b_token = bot_token or row["bot_token"]

            db.execute("""
                UPDATE subscriptions
                SET plan = ?, end_date = ?, bot_id = ?, bot_username = ?, bot_token = ?, is_active = 1
                WHERE id = ?
            """, (plan, new_end.isoformat(), b_id, b_uname, b_token, row["id"]))
            db.commit()
            return {
                "id": row["id"],
                "user_id": user_id,
                "plan": plan,
                "end_date": new_end.strftime("%d.%m.%Y"),
                "is_extended": True,
                "bot_username": b_uname
            }
        else:
            new_end = now + timedelta(days=days)
            cur = db.execute("""
                INSERT INTO subscriptions (user_id, bot_id, bot_username, bot_token, plan, start_date, end_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (user_id, bot_id, bot_username, bot_token, plan, now.isoformat(), new_end.isoformat()))
            sub_id = cur.lastrowid
            db.commit()
            return {
                "id": sub_id,
                "user_id": user_id,
                "plan": plan,
                "end_date": new_end.strftime("%d.%m.%Y"),
                "is_extended": False,
                "bot_username": bot_username
            }


def update_sub_bot(sub_id: int, bot_id: str, bot_username: str, bot_token: str) -> None:
    with _conn() as db:
        db.execute("""
            UPDATE subscriptions
            SET bot_id = ?, bot_username = ?, bot_token = ?
            WHERE id = ?
        """, (bot_id, bot_username, bot_token, sub_id))
        db.commit()


def get_user_subs(user_id: int) -> list[dict]:
    with _conn() as db:
        cur = db.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_stats() -> dict:
    with _conn() as db:
        users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders_paid = db.execute("SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM orders WHERE status = 'paid'").fetchone()
        active_subs = db.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1 AND end_date > ?",
                                 (datetime.now().isoformat(),)).fetchone()[0]
        return {
            "users": users_count,
            "paid_orders": orders_paid[0],
            "total_rub": orders_paid[1],
            "active_subs": active_subs
        }


def get_subscription(sub_id: int) -> dict | None:
    with _conn() as db:
        cur = db.execute("""
            SELECT s.*, u.username as user_username, u.first_name as user_first_name
            FROM subscriptions s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.id = ?
        """, (sub_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_all_subscriptions(limit: int = 50, offset: int = 0) -> list[dict]:
    with _conn() as db:
        cur = db.execute("""
            SELECT s.*, u.username as user_username, u.first_name as user_first_name
            FROM subscriptions s
            LEFT JOIN users u ON s.user_id = u.user_id
            ORDER BY s.id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [dict(r) for r in cur.fetchall()]


def count_subscriptions() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]


def find_user_subs(query: str | int) -> list[dict]:
    """Поиск подписок по user_id или @username."""
    with _conn() as db:
        if str(query).isdigit():
            cur = db.execute("""
                SELECT s.*, u.username as user_username, u.first_name as user_first_name
                FROM subscriptions s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.user_id = ? OR s.id = ?
                ORDER BY s.id DESC
            """, (int(query), int(query)))
        else:
            clean_q = str(query).lstrip("@").strip().lower()
            cur = db.execute("""
                SELECT s.*, u.username as user_username, u.first_name as user_first_name
                FROM subscriptions s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE LOWER(u.username) LIKE ? OR LOWER(s.bot_username) LIKE ?
                ORDER BY s.id DESC
            """, (f"%{clean_q}%", f"%{clean_q}%"))
        return [dict(r) for r in cur.fetchall()]


def extend_sub_days(sub_id: int, days: int) -> dict | None:
    now = datetime.now()
    with _conn() as db:
        cur = db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        row = cur.fetchone()
        if not row:
            return None

        cur_end = datetime.fromisoformat(row["end_date"])
        if days > 0:
            start_point = cur_end if cur_end > now else now
            new_end = start_point + timedelta(days=days)
        else:
            new_end = cur_end + timedelta(days=days)
            if new_end < now:
                new_end = now

        db.execute("""
            UPDATE subscriptions
            SET end_date = ?, is_active = 1
            WHERE id = ?
        """, (new_end.isoformat(), sub_id))
        db.commit()
        return {
            "id": sub_id,
            "user_id": row["user_id"],
            "plan": row["plan"],
            "end_date": new_end.strftime("%d.%m.%Y"),
            "end_iso": new_end.isoformat(),
            "bot_token": row["bot_token"],
            "bot_id": row["bot_id"],
            "bot_username": row["bot_username"]
        }


def set_sub_plan(sub_id: int, new_plan: str) -> dict | None:
    with _conn() as db:
        db.execute("UPDATE subscriptions SET plan = ? WHERE id = ?", (new_plan.lower(), sub_id))
        db.commit()
    return get_subscription(sub_id)


def toggle_sub_active(sub_id: int, is_active: int | None = None) -> bool:
    with _conn() as db:
        if is_active is None:
            cur = db.execute("SELECT is_active FROM subscriptions WHERE id = ?", (sub_id,))
            row = cur.fetchone()
            if not row:
                return False
            is_active = 0 if row["is_active"] else 1
        db.execute("UPDATE subscriptions SET is_active = ? WHERE id = ?", (is_active, sub_id))
        db.commit()
        return bool(is_active)


def unbind_sub_bot(sub_id: int) -> dict | None:
    with _conn() as db:
        cur = db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        row = cur.fetchone()
        if not row:
            return None
        db.execute("""
            UPDATE subscriptions
            SET bot_id = '', bot_username = '', bot_token = ''
            WHERE id = ?
        """, (sub_id,))
        db.commit()
        return dict(row)


def get_active_sub(user_id: int) -> dict | None:
    now = datetime.now().isoformat()
    with _conn() as db:
        cur = db.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = ? AND is_active = 1 AND end_date > ?
            ORDER BY id DESC LIMIT 1
        """, (user_id, now))
        row = cur.fetchone()
        return dict(row) if row else None

