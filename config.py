# -*- coding: utf-8 -*-
"""
Конфигурация бота продаж и подписок Bonzayka Defense.
"""

import os

# Основной токен бота продаж (@bonzayka_defense_bot)
BOT_TOKEN = os.environ.get("SALES_BOT_TOKEN", "8962924817:AAE9zL6SWst2Jn8Yw3QAi1qqv_k4V47GYFo")

# Логин поддержки для клиентов
SUPPORT_USERNAME = "Bonzayka"

# ID администраторов с доступом к панели управления и ручной выдаче подписок
ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# Токен CryptoPay (@CryptoBot) для приёма криптовалюты (USDT / TON / BTC)
CRYPTOBOT_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "")
CRYPTOBOT_NET = os.environ.get("CRYPTOBOT_NET", "mainnet")  # mainnet или testnet

# Токен провайдера Telegram Payments (ЮKassa / Сбербанк / etc.), если подключена касса через BotFather
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")

# База данных бота продаж
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales.db")

# Путь к родительскому проекту для авто-создания ботов через manager.py
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
