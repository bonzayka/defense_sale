# -*- coding: utf-8 -*-
"""
Главная точка входа для бота продаж и подписок Bonzayka Defense.
Запуск: python main.py
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database as db
import handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("sales_bot")


async def main():
    log.info("Инициализация базы данных...")
    db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(handlers.router)

    me = await bot.get_me()
    log.info("Бот продаж запущен: @%s (%s)", me.username, me.full_name)
    print(f"✅ Бот продаж @{me.username} успешно стартовал и слушает сообщения!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен.")
