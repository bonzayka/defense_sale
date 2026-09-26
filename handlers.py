# -*- coding: utf-8 -*-
"""
Обработчики сообщений и команд бота продаж и подписок.
"""

import os
import sys
import re
import secrets
from html import escape as esc

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery,
    LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
import database as db
import prices
import legal
import keyboards as kb

# Подключаем менеджер дочерних ботов из родительского проекта
if config.PARENT_DIR not in sys.path:
    sys.path.insert(0, config.PARENT_DIR)
try:
    import manager
except ImportError:
    manager = None

router = Router()


class UserStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_broadcast = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS or user_id in (7116116919, 1107097183)  # резервный ID создателя


# ============================== СТАРТ И ГЛАВНОЕ МЕНЮ ==============================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    uname = message.from_user.username or ""
    fname = message.from_user.first_name or ""
    db.upsert_user(uid, uname, fname)

    admin_flag = is_admin(uid)

    text = (
        f"👋 <b>Добро пожаловать в Bonzayka Defense!</b>\n\n"
        f"🛡️ Мы предоставляем персональных ботов-модераторов для Telegram-чатов "
        f"с передовой многоуровневой защитой от спама, скама, ботнетов и сливов данных.\n\n"
        f"✨ <b>Наши ключевые преимущества:</b>\n"
        f"• ⚡ Мгновенная реакция: удаление спама за доли секунды\n"
        f"• 🔞 ИИ-нейросети: ViT-анализ 18+ аватарок и Faster-Whisper для войсов\n"
        f"• 🕵️ Анти-деанон: OCR-распознавание паспортов, номеров и карт на фото\n"
        f"• 🎮 Развлечения: Texas Hold'em (3D WebApp), Мафия и Дуэли\n\n"
        f"Выберите нужное действие ниже 👇"
    )
    await message.answer(text, reply_markup=kb.main_menu_kb(admin_flag))


@router.callback_query(F.data == "nav:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    admin_flag = is_admin(cb.from_user.id)
    text = (
        f"🛡️ <b>Главное меню Bonzayka Defense</b>\n\n"
        f"Выберите интересующий вас раздел:"
    )
    try:
        await cb.message.edit_text(text, reply_markup=kb.main_menu_kb(admin_flag))
    except Exception:
        await cb.message.answer(text, reply_markup=kb.main_menu_kb(admin_flag))


# ============================== ТАРИФЫ И ПЛАНЫ ==============================

@router.callback_query(F.data == "nav:plans")
async def cb_plans(cb: CallbackQuery):
    await cb.answer()
    text = (
        "💳 <b>Тарифные планы сервиса Bonzayka Defense</b>\n\n"
        "Мы предлагаем 2 сбалансированных тарифа:\n\n"
        "🛡️ <b>1. Тариф «Обычный» (от 149 ₽ / мес)</b>\n"
        "<i>Идеальный выбор для большинства групп:</i>\n"
        "• Мгновенный антиспам AdGuard (скрытые ссылки, реклама, накрутка отзывов)\n"
        "• Антимат TextGuard и кастомные стоп-слова\n"
        "• Капча при входе от ботнетов, антифлуд, антирейд, локдаун\n"
        "• Встроенные игры: Техасский Холдем (3D WebApp), Мафия, Дуэли\n\n"
        "💎 <b>2. Тариф «PRO» (от 239 ₽ / мес)</b>\n"
        "<i>Максимальная безопасность с искусственным интеллектом:</i>\n"
        "• Всё, что входит в тариф «Обычный»\n"
        "• 🔞 ViT нейросетевой скан 18+ аватарок вступающих участников\n"
        "• 🎙️ Faster-Whisper расшифровка и фильтр голосовых сообщений\n"
        "• 🕵️ RapidOCR анти-деанон: поиск паспортов, карт, СНИЛС на фото\n"
        "• 🧠 AI-анализ угроз и шантажа через LLM\n"
        "• Выделенный приоритет обработки и поддержка 24/7\n\n"
        "Выберите тариф для просмотра цен и оформления подписки:"
    )
    await cb.message.edit_text(text, reply_markup=kb.plans_kb())


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_detail(cb: CallbackQuery):
    plan_id = cb.data.split(":")[1]
    plan = prices.get_plan_info(plan_id)
    if not plan:
        await cb.answer("Тариф не найден", show_alert=True)
        return
    await cb.answer()

    text = (
        f"<b>Тариф «{plan['title']}»</b>\n\n"
        f"<i>{plan['short_desc']}</i>\n\n"
        f"<b>В тариф входит:</b>\n"
    )
    for feat in plan["features"]:
        text += f"• {feat}\n"

    text += (
        f"\n💰 <b>Выберите срок действия подписки:</b>\n"
        f"<i>(При оплате на 3, 9 или 12 месяцев действуют скидки!)</i>"
    )
    await cb.message.edit_text(text, reply_markup=kb.periods_kb(plan_id))


# ============================== ВЫБОР СРОКА И ОПЛАТА ==============================

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    plan_id, months_str = parts[1], parts[2]
    months = int(months_str)

    plan = prices.get_plan_info(plan_id)
    pr = prices.get_price(plan_id, months)
    if not plan or not pr:
        await cb.answer("Ошибка параметров", show_alert=True)
        return
    await cb.answer()

    text = (
        f"🧾 <b>Подтверждение заказа</b>\n\n"
        f"• <b>Тариф:</b> {plan['badge']}\n"
        f"• <b>Срок:</b> {prices.PERIOD_NAMES.get(months, f'{months} мес.')}\n"
        f"• <b>Стоимость:</b> <b>{pr['rub']} ₽</b> (или {pr['stars']} ⭐)\n\n"
        f"Выберите удобный способ оплаты:"
    )
    await cb.message.edit_text(text, reply_markup=kb.payment_methods_kb(plan_id, months))


# --- Оплата через Telegram Stars (Звёзды) ---
@router.callback_query(F.data.startswith("pay:stars:"))
async def cb_pay_stars(cb: CallbackQuery):
    parts = cb.data.split(":")
    plan_id, months = parts[2], int(parts[3])
    plan = prices.get_plan_info(plan_id)
    pr = prices.get_price(plan_id, months)
    if not plan or not pr:
        await cb.answer("Ошибка", show_alert=True)
        return

    order_id = f"ord_{cb.from_user.id}_{int(cb.message.date.timestamp())}_{secrets.token_hex(2)}"
    db.create_order(order_id, cb.from_user.id, plan_id, months, pr["rub"], pr["stars"], "stars")
    await cb.answer()

    title = f"{plan['title']} ({months} мес.)"
    desc = f"Подписка на облачного бота-модератора Bonzayka Defense на {months} мес."
    prices_list = [LabeledPrice(label=title, amount=pr["stars"])]

    try:
        await cb.message.answer_invoice(
            title=title,
            description=desc,
            payload=order_id,
            currency="XTR",  # Telegram Stars
            prices=prices_list,
        )
    except Exception as e:
        await cb.message.answer(f"Не удалось выставить счёт в Stars: {e}")


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext):
    sp = message.successful_payment
    order_id = sp.invoice_payload
    order = db.get_order(order_id)

    if order:
        db.mark_order_paid(order_id)
        sub_info = db.add_or_extend_sub(message.from_user.id, order["plan"], order["months"])
    else:
        # Резерв на случай прямого инвойса
        sub_info = db.add_or_extend_sub(message.from_user.id, "standard", 1)

    text = (
        f"🎉 <b>Оплата успешно получена!</b>\n\n"
        f"Ваша подписка <b>{sub_info['plan'].upper()}</b> успешно активирована до "
        f"<b>{sub_info['end_date']}</b>.\n\n"
        f"🚀 <b>Теперь запустим вашего персонального бота:</b>\n"
        f"1. Откройте официального бота Telegram @BotFather\n"
        f"2. Создайте нового бота с помощью команды <code>/newbot</code>\n"
        f"3. Скопируйте полученный <b>HTTP API Token</b> и отправьте его сюда ответным сообщением!"
    )
    await state.set_state(UserStates.waiting_for_token)
    await state.update_data(sub_id=sub_info["id"], plan=sub_info["plan"])
    await message.answer(text, reply_markup=kb.back_to_home_kb())


# --- Оплата картой / СБП (Прямой перевод или платёжка) ---
@router.callback_query(F.data.startswith("pay:manual:"))
async def cb_pay_manual(cb: CallbackQuery):
    parts = cb.data.split(":")
    plan_id, months = parts[2], int(parts[3])
    plan = prices.get_plan_info(plan_id)
    pr = prices.get_price(plan_id, months)
    await cb.answer()

    order_id = f"ord_man_{cb.from_user.id}_{secrets.token_hex(3)}"
    db.create_order(order_id, cb.from_user.id, plan_id, months, pr["rub"], pr["stars"], "manual_sbp")

    text = (
        f"💳 <b>Оплата банковской картой / СБП</b>\n\n"
        f"• <b>Тариф:</b> {plan['badge']}\n"
        f"• <b>Срок:</b> {prices.PERIOD_NAMES.get(months, f'{months} мес.')}\n"
        f"• <b>Сумма к оплате:</b> <b>{pr['rub']} ₽</b>\n"
        f"• <b>Номер заказа:</b> <code>{order_id}</code>\n\n"
        f"Для мгновенной оплаты по СБП (любой банк РФ) или картой напишите нашему администратору:\n"
        f"👉 <b>@Bonzayka</b>\n\n"
        f"<i>Отправьте номер вашего заказа администратору, и подписка будет активирована в течение 2-3 минут!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать @Bonzayka для оплаты", url=f"https://t.me/{config.SUPPORT_USERNAME}?text=Оплата_{order_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"buy:{plan_id}:{months}")],
    ])
    await cb.message.edit_text(text, reply_markup=markup)


# ============================== ПРИВЯЗКА ТОКЕНА И ЗАПУСК БОТА ==============================

@router.callback_query(F.data.startswith("token:bind:"))
async def cb_token_bind(cb: CallbackQuery, state: FSMContext):
    sub_id = int(cb.data.split(":")[2])
    await state.set_state(UserStates.waiting_for_token)
    await state.update_data(sub_id=sub_id)
    await cb.answer()

    text = (
        "🤖 <b>Привязка бота Telegram</b>\n\n"
        "Отправьте сюда токен вашего бота от @BotFather одним сообщением.\n\n"
        "<i>Пример токена:</i>\n"
        "<code>1234567890:AAH_XxXxXxXxXxXxXxXxXxXxXxXxXxX</code>"
    )
    await cb.message.answer(text, reply_markup=kb.back_to_home_kb())


@router.message(UserStates.waiting_for_token)
async def process_bot_token(message: Message, state: FSMContext):
    token = (message.text or "").strip()
    if token.startswith("/"):
        await state.clear()
        await message.answer("Ввод отменён.", reply_markup=kb.main_menu_kb(is_admin(message.from_user.id)))
        return

    # Проверка формата токена
    if not re.match(r"^\d{6,}:[\w-]{30,}$", token):
        await message.answer(
            "⚠️ Это не похоже на токен Telegram бота.\n"
            "Формат: <code>1234567890:AA...</code>\n\n"
            "Попробуйте ещё раз или нажмите /cancel для отмены."
        )
        return

    # Проверка валидности через Bot API (getMe)
    try:
        temp_bot = Bot(token=token)
        me = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception as e:
        await message.answer(
            f"❌ Токен недействителен (ошибка Telegram API: {esc(str(e))}).\n"
            "Убедитесь, что токен скопирован без лишних пробелов."
        )
        return

    uid = message.from_user.id
    data = await state.get_data()
    sub_id = data.get("sub_id")
    await state.clear()

    # Генерируем пароль к панели управления
    gen_pass = f"def_{secrets.token_hex(4)}"

    # Запускаем через manager родительского проекта
    if manager:
        ok = manager.add(token, me.username or "", owner=uid, password=gen_pass)
        if not ok:
            # Если уже есть, пробуем обновить/рестартнуть
            manager.spawn({"id": manager.bot_id(token), "token": token, "username": me.username or "",
                           "owner": uid, "password": gen_pass})
    else:
        ok = True

    # Обновляем запись в базе
    if sub_id:
        db.update_sub_bot(sub_id, str(me.id), me.username or "", token)

    add_url = f"https://t.me/{me.username}?startgroup=onboard&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"

    text = (
        f"🎉 <b>Поздравляем! Ваш персональный бот @{esc(me.username)} успешно запущен!</b>\n\n"
        f"🛡️ <b>Как активировать защиту в вашем сообществе:</b>\n"
        f"1. Добавьте бота в чат в качестве администратора по ссылке ниже.\n"
        f"2. Бот автоматически начнёт защищать группу от спама и нарушений!\n\n"
        f"🔑 <b>Ваш пароль панели управления:</b> <code>{gen_pass}</code>\n"
        f"<i>(При входе в ЛС бота он также узнает вас автоматически как владельца)</i>."
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)],
        [InlineKeyboardButton(text="🤖 Открыть диалог с ботом", url=f"https://t.me/{me.username}")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])
    await message.answer(text, reply_markup=markup)


# ============================== КАБИНЕТ: МОИ БОТЫ И ПОДПИСКИ ==============================

@router.callback_query(F.data == "nav:my_subs")
async def cb_my_subs(cb: CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    subs = db.get_user_subs(uid)

    if not subs:
        text = (
            "🤖 <b>Ваши подписки и боты</b>\n\n"
            "У вас пока нет активных подписок.\n"
            "Выберите подходящий тариф во вкладке «💳 Выбрать тариф и купить»!"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Выбрать тариф", callback_data="nav:plans")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:home")],
        ])
        await cb.message.edit_text(text, reply_markup=markup)
        return

    text = "🤖 <b>Ваши активные подписки и боты:</b>\n\n"
    rows = []
    for s in subs:
        b_name = f"@{s['bot_username']}" if s.get("bot_username") else "⚠️ Токен ещё не привязан"
        text += (
            f"• <b>Тариф:</b> {s['plan'].upper()}\n"
            f"  <b>Бот:</b> {b_name}\n"
            f"  <b>Активна до:</b> {s['end_date']}\n\n"
        )
        if not s.get("bot_username"):
            rows.append([InlineKeyboardButton(text="🤖 Привязать токен бота", callback_data=f"token:bind:{s['id']}")])

    rows.append([InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="nav:plans")])
    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ============================== ИНФОРМАЦИЯ, FAQ И ОФЕРТА ==============================

@router.callback_query(F.data == "nav:features")
async def cb_features(cb: CallbackQuery):
    await cb.answer()
    text = (
        "🛡️ <b>Возможности системы Bonzayka Defense</b>\n\n"
        "• <b>AdGuard (Анти-спам):</b> умный алгоритм распознавания рекламы, завуалированных "
        "ссылок, скама с накруткой отзывов, пирамид и предложений вакансий.\n\n"
        "• <b>TextGuard (Анти-мат):</b> очистка чата от нецензурной брани с учётом "
        "транслита, замены символов и кастомных стоп-слов сообщества.\n\n"
        "• <b>🔞 ViT 18+ Детектор:</b> автоматический нейросетевой скан аватарок вступающих "
        "участников с мгновенным баном порно-ботов.\n\n"
        "• <b>🎙️ Faster-Whisper:</b> распознавание голосовых сообщений и фильтрация спама в аудио.\n\n"
        "• <b>🕵️ Анти-деанон OCR:</b> сканирование картинок на сливы личных данных (паспорта, "
        "номера телефонов, банковские карты, СНИЛС).\n\n"
        "• <b>🎮 Игры Texas Hold'em и Мафия:</b> повышают вовлечение и удержание аудитории в чате!"
    )
    await cb.message.edit_text(text, reply_markup=kb.back_to_home_kb())


@router.callback_query(F.data == "nav:faq")
async def cb_faq(cb: CallbackQuery):
    await cb.answer()
    text = (
        "❓ <b>Часто задаваемые вопросы (FAQ)</b>\n\n"
        "<b>1. Что такое токен бота и безопасно ли его отдавать?</b>\n"
        "Токен — это ключ управления вашим ботом из @BotFather. Мы используем его только "
        "для запуска логики модерации. Вы в любой момент можете отозвать токен в @BotFather.\n\n"
        "<b>2. Как добавить бота в чат?</b>\n"
        "После привязки токена бот выдаст прямую ссылку для добавления с нужными правами.\n\n"
        "<b>3. Чем тариф PRO отличается от Обычного?</b>\n"
        "В PRO включены нейросетевые алгоритмы: сканирование аватарок на 18+, расшифровка войсов "
        "и оптическое распознавание сливов персональных данных с картинок.\n\n"
        "<b>4. Если у меня возникли трудности с настройкой?</b>\n"
        "Наша служба поддержки всегда на связи: @Bonzayka."
    )
    await cb.message.edit_text(text, reply_markup=kb.back_to_home_kb())


@router.callback_query(F.data == "nav:legal")
async def cb_legal(cb: CallbackQuery):
    await cb.answer()
    text = legal.OFFER_TEXT
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="legal:privacy")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])
    await cb.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "legal:privacy")
async def cb_privacy(cb: CallbackQuery):
    await cb.answer()
    text = legal.PRIVACY_TEXT
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Публичная оферта", callback_data="nav:legal")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])
    await cb.message.edit_text(text, reply_markup=markup)


# ============================== АДМИН-ПАНЕЛЬ (@Bonzayka) ==============================

@router.message(Command("admin"))
@router.callback_query(F.data == "admin:menu")
async def cmd_admin(event: Message | CallbackQuery):
    uid = event.from_user.id
    if not is_admin(uid):
        if isinstance(event, CallbackQuery):
            await event.answer("Нет доступа.", show_alert=True)
        return

    st = db.get_stats()
    text = (
        f"⚙️ <b>Панель администратора Bonzayka Defense</b>\n\n"
        f"👥 Всего пользователей: <b>{st['users']}</b>\n"
        f"💳 Оплаченных заказов: <b>{st['paid_orders']}</b>\n"
        f"💰 Общая выручка: <b>{st['total_rub']} ₽</b>\n"
        f"🟢 Активных подписок: <b>{st['active_subs']}</b>\n\n"
        f"<b>Команды управления:</b>\n"
        f"• <code>/give_sub &lt;user_id&gt; &lt;months&gt; &lt;plan&gt;</code> — выдать подписку\n"
        f"<i>Пример:</i> <code>/give_sub 123456789 3 pro</code>"
    )
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=kb.admin_menu_kb())
    else:
        await event.answer(text, reply_markup=kb.admin_menu_kb())


@router.message(Command("give_sub"))
async def cmd_give_sub(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 4:
        await message.answer("Формат: <code>/give_sub &lt;user_id&gt; &lt;months&gt; &lt;standard|pro&gt;</code>")
        return

    try:
        target_uid = int(parts[1])
        months = int(parts[2])
        plan = parts[3].lower()
        if plan not in ("standard", "pro"):
            plan = "standard"
    except ValueError:
        await message.answer("Неверные параметры.")
        return

    sub_info = db.add_or_extend_sub(target_uid, plan, months)
    await message.answer(
        f"✅ Подписка <b>{plan.upper()}</b> на <b>{months} мес.</b> выдана пользователю <code>{target_uid}</code>!\n"
        f"Активна до: <b>{sub_info['end_date']}</b>"
    )
    try:
        await message.bot.send_message(
            target_uid,
            f"🎁 <b>Вам активирована подписка {plan.upper()} на {months} мес.!</b>\n"
            f"Срок действия: до <b>{sub_info['end_date']}</b>.\n\n"
            f"Откройте раздел «🤖 Мои боты и подписка» в главном меню для привязки вашего бота!",
            reply_markup=kb.main_menu_kb(is_admin(target_uid))
        )
    except Exception:
        pass
