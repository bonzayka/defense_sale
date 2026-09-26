# -*- coding: utf-8 -*-
"""
База данных SQLite для бота продаж и подписок.
"""

import sqlite3
import time
from datetime import datetime, timedelta
import config


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_FILE)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
        db.commit()


def upsert_user(user_id: int, username: str = "", first_name: str = "") -> None:
    with _conn() as db:
        db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username or "", first_name or ""))
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
        # Проверяем, есть ли уже активная подписка на этого бота или юзера
        cur = db.execute("""
            SELECT * FROM subscriptions
            WHERE user_id = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        row = cur.fetchone()

        if row:
            # Продлеваем существующую
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
            # Создаём новую
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
