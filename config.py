# -*- coding: utf-8 -*-
"""
Конфигурация бота продаж и подписок Chat Defense (@Chat_defense_bot).
"""

import os

# Основной токен бота (@Chat_defense_bot)
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("SALES_BOT_TOKEN") or "8749963931:AAEjXNW1YfN3CmSlfDtooWaSdFdcXDlKUkk"

# Логин поддержки для клиентов
SUPPORT_USERNAME = "Bonzayka"

# Главный владелец
OWNER_ID = 7116116919

# Список ID администраторов
ADMIN_IDS = [7116116919, 1107097183] + [
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# Пароль для входа в админку (/admin 7116116919 или /login 7116116919)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "7116116919")

# Токен CryptoPay (@CryptoBot) для приёма криптовалюты (USDT / TON / BTC)
CRYPTOBOT_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "")
CRYPTOBOT_NET = os.environ.get("CRYPTOBOT_NET", "mainnet")

# Токен провайдера Telegram Payments (если подключен через BotFather)
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")

# База данных бота продаж
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales.db")

# Путь к родительскому проекту для авто-создания ботов через manager.py
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.environ.get("PARENT_DIR") or os.path.abspath(os.path.join(_CURRENT_DIR, ".."))

