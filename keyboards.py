# -*- coding: utf-8 -*-
"""
Клавиатуры и кнопки интерфейса бота продаж.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import prices
import config


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💳 Выбрать тариф и купить", callback_data="nav:plans")],
        [InlineKeyboardButton(text="🤖 Мои боты и подписка", callback_data="nav:my_subs")],
        [InlineKeyboardButton(text="🛡️ Возможности защиты", callback_data="nav:features")],
        [
            InlineKeyboardButton(text="❓ FAQ", callback_data="nav:faq"),
            InlineKeyboardButton(text="📜 Оферта", callback_data="nav:legal")
        ],
        [InlineKeyboardButton(text="👨‍💻 Поддержка (@Bonzayka)", url=f"https://t.me/{config.SUPPORT_USERNAME}")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🛡️ Обычный (от 149 ₽ / мес)", callback_data="plan:standard")],
        [InlineKeyboardButton(text="💎 PRO с нейросетями (от 239 ₽ / мес)", callback_data="plan:pro")],
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
        [InlineKeyboardButton(text=f"💳 Банковская карта / СБП ({pr['rub']} ₽)", callback_data=f"pay:manual:{plan_id}:{months}")],
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
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🎁 Выдать подписку", callback_data="admin:give")],
        [InlineKeyboardButton(text="⬅️ В меню пользователя", callback_data="nav:home")],
    ])
