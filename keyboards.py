# -*- coding: utf-8 -*-
"""
Клавиатуры и кнопки интерфейса бота продаж Chat Defense.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import prices
import config


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💳 Выбрать тариф и купить", callback_data="nav:plans")],
        [InlineKeyboardButton(text="🤖 Мои боты и подписка", callback_data="nav:my_subs")],
        [InlineKeyboardButton(text="🛡️ Что умеет бот", callback_data="nav:features")],
        [
            InlineKeyboardButton(text="❓ Вопросы (FAQ)", callback_data="nav:faq"),
            InlineKeyboardButton(text="📜 Оферта", callback_data="nav:legal")
        ],
        [InlineKeyboardButton(text="👨‍💻 Поддержка (@Bonzayka)", url=f"https://t.me/{config.SUPPORT_USERNAME}")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Панель админа", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🛡️ Обычный (от 149 руб/мес)", callback_data="plan:standard")],
        [InlineKeyboardButton(text="💎 PRO (от 239 руб/мес)", callback_data="plan:pro")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def periods_kb(plan_id: str) -> InlineKeyboardMarkup:
    plan = prices.get_plan_info(plan_id)
    if not plan:
        return plans_kb()

    rows = []
    for m, pr in plan["prices"].items():
        rows.append([InlineKeyboardButton(
            text=f"📅 {pr['label']} ({pr['stars']} ⭐)",
            callback_data=f"buy:{plan_id}:{m}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к тарифам", callback_data="nav:plans")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_methods_kb(plan_id: str, months: int) -> InlineKeyboardMarkup:
    pr = prices.get_price(plan_id, months)
    if not pr:
        return plans_kb()

    rows = [
        [InlineKeyboardButton(text=f"⭐ Telegram Stars ({pr['stars']} ⭐)", callback_data=f"pay:stars:{plan_id}:{months}")],
        [InlineKeyboardButton(text=f"💳 Банковская карта / СБП ({pr['rub']} руб)", callback_data=f"pay:manual:{plan_id}:{months}")],
    ]
    if config.CRYPTOBOT_TOKEN:
        rows.append([InlineKeyboardButton(text="💎 CryptoBot (USDT / TON)", callback_data=f"pay:crypto:{plan_id}:{months}")])

    rows.append([InlineKeyboardButton(text="⬅️ Назад к срокам", callback_data=f"plan:{plan_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")]
    ])


def bot_setup_kb(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Привязать токен от @BotFather", callback_data=f"token:bind:{sub_id}")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление подписками", callback_data="admin:subs:0")],
        [
            InlineKeyboardButton(text="🎁 Выдать подписку", callback_data="admin:give"),
            InlineKeyboardButton(text="🔍 Поиск подписки", callback_data="admin:search")
        ],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])


def admin_subs_list_kb(subs: list[dict], page: int, total_count: int, page_size: int = 6) -> InlineKeyboardMarkup:
    rows = []
    for s in subs:
        is_act = bool(s.get("is_active", 1))
        badge = "💎" if s.get("plan", "").lower() == "pro" else "🛡️"
        status_dot = "🟢" if is_act else "🔴"
        u_label = f"@{s['user_username']}" if s.get("user_username") else f"ID {s['user_id']}"
        b_label = f"(@{s['bot_username']})" if s.get("bot_username") else "(нет бота)"
        btn_text = f"{status_dot} {badge} #{s['id']} {u_label} {b_label}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"admin:sub:{s['id']}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:subs:{page-1}"))

    total_pages = max(1, (total_count + page_size - 1) // page_size)
    nav_row.append(InlineKeyboardButton(text=f"Стр. {page+1}/{total_pages}", callback_data="admin:noop"))

    if (page + 1) * page_size < total_count:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin:subs:{page+1}"))

    if nav_row:
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="🔍 Поиск", callback_data="admin:search"),
        InlineKeyboardButton(text="⬅️ В админку", callback_data="admin:menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_sub_card_kb(sub: dict) -> InlineKeyboardMarkup:
    sub_id = sub["id"]
    is_act = bool(sub.get("is_active", 1))
    plan = sub.get("plan", "standard").lower()
    next_plan = "PRO" if plan == "standard" else "Standard"

    rows = [
        [
            InlineKeyboardButton(text="➕ 30 дн.", callback_data=f"admin:sub:add:{sub_id}:30"),
            InlineKeyboardButton(text="➕ 3 мес.", callback_data=f"admin:sub:add:{sub_id}:90"),
            InlineKeyboardButton(text="➕ 1 год", callback_data=f"admin:sub:add:{sub_id}:365"),
        ],
        [
            InlineKeyboardButton(text="➖ 30 дн.", callback_data=f"admin:sub:sub:{sub_id}:30"),
            InlineKeyboardButton(text="✏️ Задать дни вручную", callback_data=f"admin:sub:custom:{sub_id}"),
        ],
        [
            InlineKeyboardButton(text=f"🔄 Сменить тариф на {next_plan}", callback_data=f"admin:sub:plan:{sub_id}"),
        ],
        [
            InlineKeyboardButton(
                text="⛔ Отозвать подписку" if is_act else "🟢 Активировать подписку",
                callback_data=f"admin:sub:toggle:{sub_id}"
            )
        ]
    ]

    if sub.get("bot_username") or sub.get("bot_token"):
        rows.append([
            InlineKeyboardButton(text="🗑 Отвязать токен бота", callback_data=f"admin:sub:unbind:{sub_id}")
        ])

    rows.append([InlineKeyboardButton(text="⬅️ К списку подписок", callback_data="admin:subs:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

