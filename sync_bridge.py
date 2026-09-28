# -*- coding: utf-8 -*-
"""
Модуль синхронизации бота продаж со сервером защиты (lavka_defense).
Обеспечивает передачу данных о покупках, токенах и тарифах между серверами
через служебный Telegram-чат/канал или личный чат с владельцем.
"""

import json
import logging
from html import escape as esc
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config

logger = logging.getLogger("sync_bridge")


def make_sync_payload(event: str, data: dict) -> str:
    """Формирует закодированную строку синхронизации."""
    payload = {
        "sync_version": 1,
        "event": event,
        "data": data
    }
    return f"#SYNC#{json.dumps(payload, ensure_ascii=False)}#ENDSYNC#"


def make_sync_keyboard(event: str) -> InlineKeyboardMarkup | None:
    """Создает инлайн-кнопку прямого действия для администратора."""
    if event in ("add_bot", "start_bot"):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить бота на сервере", callback_data="sync:spawn")]
        ])
    elif event == "update_token":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Применить токен на сервере", callback_data="sync:spawn")]
        ])
    elif event == "update_plan":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Применить тариф на сервере", callback_data="sync:spawn")]
        ])
    elif event == "stop_bot":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏹ Остановить бота на сервере", callback_data="sync:stop")]
        ])
    return None


async def notify_sync_event(bot: Bot, event: str, **kwargs) -> bool:
    """
    Отправляет событие синхронизации в служебный чат/канал и владельцу.
    События:
      - 'add_bot': запуск нового бота
      - 'update_token': смена токена бота с переносом данных
      - 'start_bot': запуск процесса бота
      - 'stop_bot': остановка процесса бота
      - 'update_plan': смена тарифа или продление
    """
    token = kwargs.get("token") or kwargs.get("new_token", "")
    username = kwargs.get("username", "")
    owner = kwargs.get("owner", 0)
    plan = kwargs.get("plan", "standard")
    end_date = kwargs.get("end_date", "")

    event_titles = {
        "add_bot": "🆕 Привязка и запуск нового бота",
        "update_token": "🔄 Смена токена бота",
        "start_bot": "▶️ Запуск бота",
        "stop_bot": "⏹ Остановка бота",
        "update_plan": "💎 Обновление тарифа / срока подписки",
    }
    title = event_titles.get(event, f"Событие: {event}")
    badge = "💎 PRO" if plan.lower() == "pro" else "🛡️ Обычный"

    payload_str = make_sync_payload(event, kwargs)

    text = (
        f"⚡ <b>[Chat Defense Sync] {title}</b>\n\n"
        f"👤 <b>Владелец:</b> ID <code>{owner}</code>\n"
        f"🤖 <b>Бот:</b> @{esc(username) if username else 'не задан'}\n"
        f"🏷 <b>Тариф:</b> {badge}\n"
        f"📅 <b>Срок действия:</b> до <b>{end_date}</b>\n"
        f"🔑 <b>Токен:</b> <code>{token}</code>\n\n"
        f"<i>Служебные данные для сервера защиты:</i>\n"
        f"<code>{payload_str}</code>"
    )

    targets = set()
    sync_chat = getattr(config, "SYNC_CHAT_ID", None)
    if sync_chat:
        targets.add(sync_chat)
    if getattr(config, "OWNER_ID", None):
        targets.add(config.OWNER_ID)

    keyboard = make_sync_keyboard(event)

    sent = False
    for chat_id in targets:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            sent = True
        except Exception as e:
            logger.warning(f"Не удалось отправить sync-сообщение в {chat_id}: {e}")

    return sent
