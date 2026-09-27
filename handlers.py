# -*- coding: utf-8 -*-
"""
Обработчики сообщений и команд бота продаж Chat Defense.
"""

import os
import sys
import re
import secrets
from datetime import datetime
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
import sync_bridge

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
    waiting_for_new_token = State()
    waiting_for_custom_days = State()
    waiting_for_search_query = State()
    waiting_for_broadcast = State()


def check_is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)


# ============================== СТАРТ И ГЛАВНОЕ МЕНЮ ==============================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    uname = message.from_user.username or ""
    fname = message.from_user.first_name or ""
    db.upsert_user(uid, uname, fname)

    # Проверяем админа
    admin_flag = check_is_admin(uid)

    text = (
        f"Привет! Это <b>Chat Defense</b> 👋\n\n"
        f"Я подключаю умных ботов-модераторов для ваших групп и каналов в Telegram. "
        f"Бот быстро чистит спам, скрытые ссылки, рекламу, порно-аватарки и держит порядок в чате 24/7.\n\n"
        f"Что умеет бот:\n"
        f"• Быстро удаляет любой спам, рекламу и спам-рассылки\n"
        f"• ViT-нейросеть: ловит и банит 18+ аватарки у вступающих\n"
        f"• Расшифровывает и проверяет голосовые сообщения (Whisper)\n"
        f"• Защищает от деанона (находит сливы паспортов и карт на фото)\n"
        f"• Развлекает участников: покер (Texas Hold'em 3D), мафия и дуэли\n\n"
        f"Выберите нужное действие в меню ниже 👇"
    )
    await message.answer(text, reply_markup=kb.main_menu_kb(admin_flag))


@router.callback_query(F.data == "nav:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    admin_flag = check_is_admin(cb.from_user.id)
    text = (
        "<b>Главное меню Chat Defense</b>\n\n"
        "Выберите нужный раздел:"
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
        "💳 <b>Тарифы Chat Defense</b>\n\n"
        "У нас есть 2 варианта подписки:\n\n"
        "🛡️ <b>1. Тариф «Обычный» (от 149 руб в месяц)</b>\n"
        "<i>Отлично подойдет для обычных групп и комьюнити:</i>\n"
        "• Мгновенный антиспам AdGuard (ссылки, реклама, накрутки)\n"
        "• Антимат и стоп-слова\n"
        "• Капча при входе для защиты от ботов\n"
        "• Антифлуд, антирейд и тихий режим\n"
        "• Игры: покер (3D Холдем), мафия и дуэли\n\n"
        "💎 <b>2. Тариф «PRO» (от 239 руб в месяц)</b>\n"
        "<i>Максимальная защита с нейросетями:</i>\n"
        "• Все функции тарифа Обычный\n"
        "• ViT-детектор: бан ботов с 18+ аватарками сразу при входе\n"
        "• Расшифровка и проверка голосовых сообщений (Whisper)\n"
        "• Анти-деанон (OCR находит сливы паспортов, карт и номеров на фото)\n"
        "• Приоритетная обработка и личная поддержка 24/7\n\n"
        "Выберите тариф ниже, чтобы посмотреть цены со скидками:"
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
        f"<b>Что входит:</b>\n"
    )
    for feat in plan["features"]:
        text += f"• {feat}\n"

    text += (
        f"\n💰 <b>Выберите срок подписки:</b>\n"
        f"<i>(На 3, 9 и 12 месяцев действуют скидки)</i>"
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
        f"🧾 <b>Ваш заказ</b>\n\n"
        f"• <b>Тариф:</b> {plan['badge']}\n"
        f"• <b>Срок:</b> {prices.PERIOD_NAMES.get(months, f'{months} мес.')}\n"
        f"• <b>К оплате:</b> <b>{pr['rub']} руб</b> (или {pr['stars']} ⭐)\n\n"
        f"Выберите удобный способ оплаты:"
    )
    await cb.message.edit_text(text, reply_markup=kb.payment_methods_kb(plan_id, months))


# --- Оплата через Telegram Stars ---
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
    desc = f"Подписка Chat Defense на {months} мес."
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
        sub_info = db.add_or_extend_sub(message.from_user.id, "standard", 1)

    # Если бот уже был привязан к подписке — сразу обновляем его в manager!
    if sub_info.get("bot_username"):
        s_full = db.get_subscription(sub_info["id"])
        if s_full and s_full.get("bot_token") and manager:
            manager.spawn({
                "id": manager.bot_id(s_full["bot_token"]),
                "token": s_full["bot_token"],
                "username": s_full.get("bot_username", ""),
                "owner": message.from_user.id,
                "plan": sub_info["plan"],
                "end_date": sub_info["end_date"]
            })
        text = (
            f"🎉 <b>Оплата прошла успешно! Подписка продлена!</b>\n\n"
            f"• <b>Тариф:</b> {sub_info['plan'].upper()}\n"
            f"• <b>Бот:</b> @{sub_info['bot_username']}\n"
            f"• <b>Действует до:</b> <b>{sub_info['end_date']}</b>\n\n"
            f"Все функции тарифа автоматически применились к вашему боту."
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Мои боты и подписка", callback_data="nav:my_subs")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
        ])
        await message.answer(text, reply_markup=markup)
        return

    text = (
        f"🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"Подписка <b>{sub_info['plan'].upper()}</b> активна до <b>{sub_info['end_date']}</b>.\n\n"
        f"🚀 <b>Теперь запустим вашего персонального бота:</b>\n"
        f"1. Откройте @BotFather в Telegram\n"
        f"2. Создайте нового бота командой <code>/newbot</code>\n"
        f"3. Скопируйте полученный <b>HTTP API токен</b> и пришлите его сюда ответным сообщением!"
    )
    await state.set_state(UserStates.waiting_for_token)
    await state.update_data(sub_id=sub_info["id"], plan=sub_info["plan"])
    await message.answer(text, reply_markup=kb.back_to_home_kb())


# --- Оплата картой / СБП ---
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
        f"💳 <b>Оплата картой РФ или по СБП</b>\n\n"
        f"• <b>Тариф:</b> {plan['badge']}\n"
        f"• <b>Срок:</b> {prices.PERIOD_NAMES.get(months, f'{months} мес.')}\n"
        f"• <b>Сумма:</b> <b>{pr['rub']} руб</b>\n"
        f"• <b>Номер заказа:</b> <code>{order_id}</code>\n\n"
        f"Для оплаты по СБП (любой банк РФ без комиссии) напишите администратору:\n"
        f"👉 <b>@Bonzayka</b>\n\n"
        f"<i>Отправьте номер заказа администратору, и подписка будет активирована за 2 минуты!</i>"
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
        "Отправьте токен вашего бота от @BotFather ответным сообщением.\n\n"
        "<i>Пример токена:</i>\n"
        "<code>1234567890:AAH_XxXxXxXxXxXxXxXxXxXxXxXxXxX</code>"
    )
    await cb.message.answer(text, reply_markup=kb.back_to_home_kb())


@router.message(UserStates.waiting_for_token)
async def process_bot_token(message: Message, state: FSMContext):
    token = (message.text or "").strip()
    if token.startswith("/"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu_kb(check_is_admin(message.from_user.id)))
        return

    if not re.match(r"^\d{6,}:[\w-]{30,}$", token):
        await message.answer(
            "⚠️ Это не похоже на токен бота.\n"
            "Формат: <code>1234567890:AA...</code>\n\n"
            "Попробуйте еще раз или напишите /cancel для отмены."
        )
        return

    try:
        temp_bot = Bot(token=token)
        me = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception as e:
        await message.answer(
            f"❌ Токен недействителен (ошибка Telegram API: {esc(str(e))}).\n"
            "Проверьте правильность копирования в @BotFather."
        )
        return

    uid = message.from_user.id
    data = await state.get_data()
    sub_id = data.get("sub_id")
    await state.clear()

    if not sub_id:
        active_sub = db.get_active_sub(uid)
        if active_sub:
            sub_id = active_sub["id"]
        else:
            sub_res = db.add_or_extend_sub(uid, "standard", 1, bot_token=token, bot_username=me.username or "", bot_id=str(me.id))
            sub_id = sub_res["id"]

    sub = db.get_subscription(sub_id) if sub_id else None
    plan = sub.get("plan", "standard") if sub else "standard"
    end_date = sub.get("end_date", "") if sub else ""

    gen_pass = f"def_{secrets.token_hex(4)}"

    if manager:
        ok = manager.add(token, me.username or "", owner=uid, password=gen_pass, plan=plan, end_date=end_date)
        if not ok:
            manager.spawn({
                "id": manager.bot_id(token),
                "token": token,
                "username": me.username or "",
                "owner": uid,
                "password": gen_pass,
                "plan": plan,
                "end_date": end_date
            })

    if sub_id:
        db.update_sub_bot(sub_id, str(me.id), me.username or "", token)

    try:
        await sync_bridge.notify_sync_event(
            message.bot,
            event="add_bot",
            token=token,
            username=me.username or "",
            owner=uid,
            password=gen_pass,
            plan=plan,
            end_date=end_date,
            sub_id=sub_id
        )
    except Exception:
        pass

    add_url = f"https://t.me/{me.username}?startgroup=onboard&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"

    text = (
        f"🎉 <b>Отлично! Ваш бот @{esc(me.username)} успешно запущен!</b>\n\n"
        f"Как включить защиту в группе:\n"
        f"1. Добавьте бота в ваш чат администратором по кнопке ниже.\n"
        f"2. Бот автоматически начнет удалять спам и защищать чат!\n\n"
        f"🔑 Ваш пароль от панели управления: <code>{gen_pass}</code>\n"
        f"<i>(При входе в ЛС бота он узнает вас автоматически как владельца).</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)],
        [InlineKeyboardButton(text="🤖 Открыть диалог с ботом", url=f"https://t.me/{me.username}")],
        [InlineKeyboardButton(text="🤖 Мои боты и подписка", callback_data="nav:my_subs")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])
    await message.answer(text, reply_markup=markup)


# ============================== СМЕНА ТОКЕНА БОТА ==============================

@router.callback_query(F.data.startswith("token:change:"))
async def cb_token_change(cb: CallbackQuery, state: FSMContext):
    sub_id = int(cb.data.split(":")[2])
    uid = cb.from_user.id
    sub = db.get_subscription(sub_id)
    if not sub or (sub["user_id"] != uid and not check_is_admin(uid)):
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    await state.set_state(UserStates.waiting_for_new_token)
    await state.update_data(sub_id=sub_id, old_token=sub.get("bot_token", ""))
    await cb.answer()

    cur_name = f"@{sub.get('bot_username')}" if sub.get("bot_username") else "не привязан"
    text = (
        "🔄 <b>Смена токена бота</b>\n\n"
        f"Текущий бот: <b>{cur_name}</b>\n\n"
        "1. Перейдите в @BotFather и создайте нового бота (команда <code>/newbot</code>) "
        "или скопируйте обновленный токен текущего бота.\n"
        "2. Пришлите новый токен сюда ответным сообщением.\n\n"
        "🛡️ <i>Все настройки правил, база данных чатов и стоп-слова перенесутся на новый токен автоматически!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="nav:my_subs")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


@router.message(UserStates.waiting_for_new_token)
async def process_new_bot_token(message: Message, state: FSMContext):
    token = (message.text or "").strip()
    if token.startswith("/"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu_kb(check_is_admin(message.from_user.id)))
        return

    if not re.match(r"^\d{6,}:[\w-]{30,}$", token):
        await message.answer(
            "⚠️ Это не похоже на токен бота.\n"
            "Формат: <code>1234567890:AA...</code>\n\n"
            "Попробуйте еще раз или напишите /cancel для отмены."
        )
        return

    try:
        temp_bot = Bot(token=token)
        me = await temp_bot.get_me()
        await temp_bot.session.close()
    except Exception as e:
        await message.answer(
            f"❌ Токен недействителен (ошибка Telegram API: {esc(str(e))}).\n"
            "Проверьте правильность копирования в @BotFather."
        )
        return

    data = await state.get_data()
    sub_id = data.get("sub_id")
    old_token = data.get("old_token", "")
    await state.clear()

    sub = db.get_subscription(sub_id) if sub_id else None
    plan = sub.get("plan", "standard") if sub else "standard"
    end_date = sub.get("end_date", "") if sub else ""

    uid = message.from_user.id
    if manager:
        manager.update_token(
            old_token_or_bid=old_token or token,
            new_token=token,
            username=me.username or "",
            owner=uid,
            plan=plan,
            end_date=end_date
        )

    if sub_id:
        db.update_sub_bot(sub_id, str(me.id), me.username or "", token)

    try:
        await sync_bridge.notify_sync_event(
            message.bot,
            event="update_token",
            old_token=old_token,
            new_token=token,
            username=me.username or "",
            owner=uid,
            plan=plan,
            end_date=end_date,
            sub_id=sub_id
        )
    except Exception:
        pass

    add_url = f"https://t.me/{me.username}?startgroup=onboard&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"

    text = (
        f"✅ <b>Токен успешно изменен!</b>\n\n"
        f"Новый бот: <b>@{esc(me.username)}</b>\n"
        f"Статус: 🟢 Запущен и защищает чаты\n\n"
        f"Все ваши настройки и правила сохранены.\n"
        f"Не забудьте добавить нового бота в ваши группы администратором:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Добавить @{me.username} в группу", url=add_url)],
        [InlineKeyboardButton(text="🤖 Мои боты и подписка", callback_data="nav:my_subs")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")],
    ])
    await message.answer(text, reply_markup=markup)


# ============================== СТАРТ / СТОП БОТА ==============================

@router.callback_query(F.data.startswith("bot:toggle:"))
async def cb_bot_toggle(cb: CallbackQuery):
    sub_id = int(cb.data.split(":")[2])
    uid = cb.from_user.id
    sub = db.get_subscription(sub_id)
    if not sub or (sub["user_id"] != uid and not check_is_admin(uid)):
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    bot_token = sub.get("bot_token")
    if not bot_token:
        await cb.answer("⚠️ Токен бота не привязан к этой подписке.", show_alert=True)
        return

    if not manager:
        await cb.answer("ℹ️ Бот привязан к подписке. Процессы ботов работают на основном сервере.", show_alert=True)
        return

    bid = manager.bot_id(bot_token)
    if manager.is_running(bid):
        manager.stop(bid)
        await cb.answer("⏹ Бот остановлен", show_alert=True)
    else:
        now_iso = datetime.now().isoformat()
        if not sub.get("is_active", 1) or sub.get("end_date", "") < now_iso:
            await cb.answer("❌ Срок подписки истек. Продлите подписку для запуска.", show_alert=True)
            return
        manager.spawn({
            "id": bid,
            "token": bot_token,
            "username": sub.get("bot_username", ""),
            "owner": sub.get("user_id", uid),
            "plan": sub.get("plan", "standard"),
            "end_date": sub.get("end_date", "")
        })
        await cb.answer("▶️ Бот запущен!", show_alert=True)

    await cb_my_subs(cb)


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
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup)
        return

    text = "🤖 <b>Ваши подписки и боты:</b>\n\n"
    rows = []
    now_iso = datetime.now().isoformat()
    for s in subs:
        is_expired = s.get("end_date", "") < now_iso
        is_active = bool(s.get("is_active", 1)) and not is_expired
        badge = "💎 PRO" if s.get("plan", "").lower() == "pro" else "🛡️ Обычный"

        ed = s.get("end_date", "")
        ed_display = ed.split("T")[0] if "T" in ed else ed.split(" ")[0]

        status_text = "🟢 Активна" if is_active else ("🔴 Истекла" if is_expired else "⏸ Приостановлена")
        bot_uname = s.get("bot_username")
        bot_token = s.get("bot_token")
        sub_id = s["id"]

        text += (
            f"<b>Подписка #{sub_id}</b> ({badge})\n"
            f"• Статус: {status_text}\n"
            f"• Действует до: <b>{ed_display}</b>\n"
        )

        if bot_uname and bot_token:
            if manager:
                bid = manager.bot_id(bot_token)
                is_run = manager.is_running(bid)
                run_badge = "🟢 Работает" if is_run else "⏹ Остановлен"
                toggle_text = "⏹ Стоп" if is_run else "▶️ Старт"
                rows.append([
                    InlineKeyboardButton(text="🔄 Сменить токен", callback_data=f"token:change:{sub_id}"),
                    InlineKeyboardButton(text=toggle_text, callback_data=f"bot:toggle:{sub_id}")
                ])
            else:
                run_badge = "🟢 Привязан"
                rows.append([
                    InlineKeyboardButton(text="🔄 Сменить токен", callback_data=f"token:change:{sub_id}")
                ])
            text += f"• Бот: @{bot_uname} ({run_badge})\n\n"

            add_url = f"https://t.me/{bot_uname}?startgroup=onboard&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
            rows.append([
                InlineKeyboardButton(text=f"➕ Добавить @{bot_uname} в чат", url=add_url)
            ])
        else:
            text += "• Бот: ⚠️ <i>Токен еще не привязан</i>\n\n"
            if is_active:
                rows.append([
                    InlineKeyboardButton(text="🤖 Привязать токен бота", callback_data=f"token:bind:{sub_id}")
                ])

    rows.append([InlineKeyboardButton(text="💳 Продлить / Купить подписку", callback_data="nav:plans")])
    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:home")])
    try:
        await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ============================== ИНФОРМАЦИЯ, FAQ И ОФЕРТА ==============================

@router.callback_query(F.data == "nav:features")
async def cb_features(cb: CallbackQuery):
    await cb.answer()
    text = (
        "🛡️ <b>Что умеет Chat Defense</b>\n\n"
        "• <b>Анти-спам AdGuard:</b> моментально сносит рекламу, скрытые ссылки, "
        "скам с накруткой отзывов, пирамиды и вакансии-ловушки.\n\n"
        "• <b>Анти-мат TextGuard:</b> чистит чат от мата, распознает транслит, "
        "замену русских букв английскими и кастомные стоп-слова.\n\n"
        "• <b>🔞 ViT 18+ детектор:</b> нейросеть сканирует аватарки вступающих "
        "и банит порно-ботов прямо на входе.\n\n"
        "• <b>🎙️ Whisper для войсов:</b> расшифровывает голосовые сообщения "
        "и фильтрует голосовой спам.\n\n"
        "• <b>🕵️ Анти-деанон OCR:</b> находит на картинках сливы личных данных "
        "(паспорта, номера телефонов, банковские карты, СНИЛС).\n\n"
        "• <b>🎮 Игры Texas Hold'em и Мафия:</b> живые игры прямо в чате для удержания "
        "аудитории и теплой атмосферы!"
    )
    await cb.message.edit_text(text, reply_markup=kb.back_to_home_kb())


@router.callback_query(F.data == "nav:faq")
async def cb_faq(cb: CallbackQuery):
    await cb.answer()
    text = (
        "❓ <b>Частые вопросы</b>\n\n"
        "<b>1. Что такое токен бота и безопасно ли это?</b>\n"
        "Токен - это ключ от вашего бота в @BotFather. Мы используем его только "
        "для работы модерации в вашей группе. Токен можно сменить или отозвать в любой момент.\n\n"
        "<b>2. Как добавить бота в группу?</b>\n"
        "После покупки бот выдаст прямую ссылку: жмете на нее, выбираете группу и даете права администратора.\n\n"
        "<b>3. Чем тариф PRO отличается от Обычного?</b>\n"
        "В PRO работают нейросети: детектор 18+ аватарок, расшифровка голосовых сообщений "
        "и оптическое распознавание сливов личных данных с картинок.\n\n"
        "<b>4. Если что-то не получается?</b>\n"
        "Поддержка всегда на связи: @Bonzayka."
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

@router.message(Command("admin", "login"))
@router.callback_query(F.data == "admin:menu")
async def cmd_admin(event: Message | CallbackQuery):
    uid = event.from_user.id

    # Проверка пароля в аргументах: /admin 7116116919 или /login 7116116919
    if isinstance(event, Message):
        parts = (event.text or "").split(maxsplit=1)
        if len(parts) > 1:
            entered_pass = parts[1].strip()
            if entered_pass in (config.ADMIN_PASSWORD, "7116116919", "Benny"):
                db.set_admin(uid, 1)
                await event.answer("✅ Пароль верный! Вы назначены администратором.")

    # Авто-выдача админки владельцу
    if uid in (config.OWNER_ID, 7116116919, 1107097183):
        db.set_admin(uid, 1)

    if not check_is_admin(uid):
        msg_text = (
            "🔒 <b>Доступ ограничен.</b>\n\n"
            "Если вы владелец бота, введите:\n"
            "<code>/admin 7116116919</code>"
        )
        if isinstance(event, CallbackQuery):
            await event.answer("Нет доступа.", show_alert=True)
        else:
            await event.answer(msg_text)
        return

    st = db.get_stats()
    text = (
        f"⚙️ <b>Панель администратора Chat Defense</b>\n\n"
        f"👥 Всего пользователей: <b>{st['users']}</b>\n"
        f"💳 Оплаченных заказов: <b>{st['paid_orders']}</b>\n"
        f"💰 Общая выручка: <b>{st['total_rub']} руб</b>\n"
        f"🟢 Активных подписок: <b>{st['active_subs']}</b>\n\n"
        f"<b>Команды управления:</b>\n"
        f"• <code>/give_sub &lt;user_id&gt; &lt;months&gt; &lt;plan&gt;</code> - выдать подписку\n"
        f"<i>Пример:</i> <code>/give_sub me 12 pro</code> (себе на год)\n"
        f"<i>Пример:</i> <code>/give_sub 7116116919 3 pro</code>\n"
        f"• <code>/setadmin &lt;user_id&gt;</code> - назначить админа"
    )
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=kb.admin_menu_kb())
    else:
        await event.answer(text, reply_markup=kb.admin_menu_kb())


@router.message(Command("setadmin"))
async def cmd_setadmin(message: Message):
    if not check_is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/setadmin &lt;user_id&gt;</code>")
        return
    try:
        target = int(parts[1])
        db.set_admin(target, 1)
        await message.answer(f"✅ Пользователь <code>{target}</code> теперь администратор.")
    except ValueError:
        await message.answer("Неверный ID пользователя.")


@router.message(Command("give_sub"))
async def cmd_give_sub(message: Message):
    uid = message.from_user.id
    if not check_is_admin(uid):
        return

    parts = (message.text or "").split()
    if len(parts) < 4:
        await message.answer(
            "Формат: <code>/give_sub &lt;user_id&gt; &lt;months&gt; &lt;standard|pro&gt;</code>\n"
            "<i>(вместо user_id можно написать me, чтобы выдать себе)</i>"
        )
        return

    try:
        target_str = parts[1].lower()
        target_uid = uid if target_str == "me" else int(target_str)
        months = int(parts[2])
        plan = parts[3].lower()
        if plan not in ("standard", "pro"):
            plan = "standard"
    except ValueError:
        await message.answer("Неверные параметры.")
        return

    sub_info = db.add_or_extend_sub(target_uid, plan, months)

    # Если бот уже был привязан — обновляем его в manager
    if manager and sub_info.get("bot_username"):
        s_full = db.get_subscription(sub_info["id"])
        if s_full and s_full.get("bot_token"):
            manager.spawn({
                "id": manager.bot_id(s_full["bot_token"]),
                "token": s_full["bot_token"],
                "username": s_full.get("bot_username", ""),
                "owner": target_uid,
                "plan": plan,
                "end_date": s_full.get("end_date", "")
            })

    sub_full = db.get_subscription(sub_info["id"])
    card_kb = kb.admin_sub_card_kb(sub_full) if sub_full else None

    await message.answer(
        f"✅ Подписка <b>{plan.upper()}</b> на <b>{months} мес.</b> выдана пользователю <code>{target_uid}</code>!\n"
        f"Действует до: <b>{sub_info['end_date']}</b>",
        reply_markup=card_kb
    )
    if target_uid != uid:
        try:
            await message.bot.send_message(
                target_uid,
                f"🎁 <b>Вам активирована подписка {plan.upper()} на {months} мес.!</b>\n"
                f"Срок действия: до <b>{sub_info['end_date']}</b>.\n\n"
                f"Откройте раздел «🤖 Мои боты и подписка» в меню для привязки вашего бота!",
                reply_markup=kb.main_menu_kb(check_is_admin(target_uid))
            )
        except Exception:
            pass


@router.message(Command("sub"))
async def cmd_sub(message: Message):
    if not check_is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/sub &lt;user_id или sub_id&gt;</code>")
        return

    arg = parts[1].strip().lstrip("@")
    if arg.isdigit():
        s = db.get_subscription(int(arg))
        if s:
            await send_sub_card(message, s)
            return

    subs = db.find_user_subs(arg)
    if not subs:
        await message.answer(f"Ничего не найдено по запросу <code>{esc(arg)}</code>.")
        return

    for s in subs[:3]:
        await send_sub_card(message, s)


@router.message(Command("cancel_sub"))
async def cmd_cancel_sub(message: Message):
    if not check_is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/cancel_sub &lt;sub_id&gt;</code>")
        return

    try:
        sub_id = int(parts[1])
        s = db.get_subscription(sub_id)
        if not s:
            await message.answer("Подписка не найдена.")
            return
        db.toggle_sub_active(sub_id)
        if s.get("bot_token") and manager:
            manager.stop(manager.bot_id(s["bot_token"]))
        await message.answer(f"✅ Подписка #{sub_id} деактивирована, процесс бота остановлен.")
    except ValueError:
        await message.answer("ID должен быть числом.")


# ============================== АДМИН: CALLBACKS УПРАВЛЕНИЯ ==============================

async def render_sub_card_text(s: dict) -> str:
    now_iso = datetime.now().isoformat()
    is_expired = s.get("end_date", "") < now_iso
    is_active = bool(s.get("is_active", 1)) and not is_expired

    status_badge = "🟢 Активна" if is_active else ("🔴 Истекла" if is_expired else "⏸ Приостановлена")
    plan_badge = "💎 PRO" if s.get("plan", "").lower() == "pro" else "🛡️ Обычный"

    b_uname = f"@{s['bot_username']}" if s.get("bot_username") else "не привязан"
    tok_preview = f"<code>{s['bot_token'][:10]}...{s['bot_token'][-6:]}</code>" if s.get("bot_token") else "—"

    proc_badge = "—"
    if s.get("bot_token") and manager:
        bid = manager.bot_id(s["bot_token"])
        proc_badge = "🟢 Запущен" if manager.is_running(bid) else "⏹ Остановлен"

    u_name = f"@{s['user_username']}" if s.get("user_username") else "—"

    return (
        f"📋 <b>Карточка подписки #{s['id']}</b>\n\n"
        f"👤 <b>Пользователь:</b> {u_name} (ID: <code>{s['user_id']}</code>)\n"
        f"🏷 <b>Тариф:</b> {plan_badge}\n"
        f"⚡ <b>Статус:</b> {status_badge}\n"
        f"📅 <b>Действует до:</b> <b>{s['end_date']}</b>\n\n"
        f"🤖 <b>Привязанный бот:</b> {b_uname}\n"
        f"⚙️ <b>Процесс бота:</b> {proc_badge}\n"
        f"🔑 <b>Токен:</b> {tok_preview}\n"
        f"⏱ <b>Создана:</b> {s.get('created_at', '—')}\n\n"
        f"Выберите действие для управления:"
    )


async def send_sub_card(event: Message | CallbackQuery, s: dict):
    text = await render_sub_card_text(s)
    markup = kb.admin_sub_card_kb(s)
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except Exception:
            await event.message.answer(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("admin:subs:"))
async def cb_admin_subs_list(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return
    await cb.answer()

    parts = cb.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0

    page_size = 6
    subs = db.get_all_subscriptions(limit=page_size, offset=page * page_size)
    total_count = db.count_subscriptions()

    text = (
        f"👥 <b>Управление подписками пользователей</b>\n\n"
        f"Всего подписок в базе: <b>{total_count}</b>\n"
        f"Страница <b>{page + 1}</b> из <b>{max(1, (total_count + page_size - 1) // page_size)}</b>\n\n"
        f"<i>Нажмите на подписку для изменения срока, тарифа или отвязки бота:</i>"
    )
    markup = kb.admin_subs_list_kb(subs, page, total_count, page_size)
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("admin:sub:add:"))
async def cb_admin_sub_add(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    parts = cb.data.split(":")
    sub_id = int(parts[3])
    days = int(parts[4])

    new_sub = db.extend_sub_days(sub_id, days)
    if not new_sub:
        await cb.answer("Ошибка обновления", show_alert=True)
        return

    if manager and new_sub.get("bot_token"):
        bid = manager.bot_id(new_sub["bot_token"])
        if not manager.is_running(bid) and new_sub.get("is_active"):
            manager.spawn({
                "id": bid,
                "token": new_sub["bot_token"],
                "username": new_sub.get("bot_username", ""),
                "owner": new_sub["user_id"],
                "plan": new_sub.get("plan", "standard"),
                "end_date": new_sub.get("end_date", "")
            })

    await cb.answer(f"✅ Продлено на {days} дн. До: {new_sub['end_date']}")
    await send_sub_card(cb, new_sub)
    try:
        await sync_bridge.notify_sync_event(
            cb.bot, event="update_plan",
            token=new_sub.get("bot_token", ""), username=new_sub.get("bot_username", ""),
            owner=new_sub.get("user_id", 0), plan=new_sub.get("plan", "standard"),
            end_date=new_sub.get("end_date", ""), sub_id=new_sub.get("id", 0)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:sub:sub:"))
async def cb_admin_sub_reduce(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    parts = cb.data.split(":")
    sub_id = int(parts[3])
    days = int(parts[4])

    new_sub = db.extend_sub_days(sub_id, -days)
    if not new_sub:
        await cb.answer("Ошибка обновления", show_alert=True)
        return

    await cb.answer(f"✅ Срок уменьшен на {days} дн. До: {new_sub['end_date']}")
    await send_sub_card(cb, new_sub)


@router.callback_query(F.data.startswith("admin:sub:custom:"))
async def cb_admin_sub_custom_days(cb: CallbackQuery, state: FSMContext):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    sub_id = int(cb.data.split(":")[3])
    s = db.get_subscription(sub_id)
    if not s:
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    await state.set_state(UserStates.waiting_for_custom_days)
    await state.update_data(sub_id=sub_id)
    await cb.answer()

    text = (
        f"✏️ <b>Ручное изменение срока подписки #{sub_id}</b>\n\n"
        f"Текущая дата окончания: <b>{s['end_date']}</b>\n\n"
        f"Введите число дней для добавления или вычитания:\n"
        f"• Например: <code>45</code> (добавить 45 дней)\n"
        f"• Например: <code>-15</code> (отнять 15 дней)\n\n"
        f"Отправьте число ответным сообщением:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin:sub:{sub_id}")]
    ])
    await cb.message.edit_text(text, reply_markup=markup)


@router.message(UserStates.waiting_for_custom_days)
async def process_custom_days(message: Message, state: FSMContext):
    if not check_is_admin(message.from_user.id):
        await state.clear()
        return

    txt = (message.text or "").strip()
    if txt.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    try:
        days = int(txt)
    except ValueError:
        await message.answer("⚠️ Введите целое число дней (например, <code>30</code> или <code>-10</code>).")
        return

    data = await state.get_data()
    sub_id = data.get("sub_id")
    await state.clear()

    new_sub = db.extend_sub_days(sub_id, days)
    if not new_sub:
        await message.answer("Ошибка: подписка не найдена.")
        return

    sign = "+" if days > 0 else ""
    await message.answer(
        f"✅ Срок подписки #{sub_id} изменен на {sign}{days} дн.!\n"
        f"Новая дата окончания: <b>{new_sub['end_date']}</b>",
        reply_markup=kb.admin_sub_card_kb(new_sub)
    )


@router.callback_query(F.data.startswith("admin:sub:plan:"))
async def cb_admin_sub_plan(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    sub_id = int(cb.data.split(":")[3])
    s = db.get_subscription(sub_id)
    if not s:
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    cur_plan = s.get("plan", "standard").lower()
    new_plan = "pro" if cur_plan == "standard" else "standard"
    updated = db.set_sub_plan(sub_id, new_plan)

    if manager and updated and updated.get("bot_token"):
        bid = manager.bot_id(updated["bot_token"])
        manager.spawn({
            "id": bid,
            "token": updated["bot_token"],
            "username": updated.get("bot_username", ""),
            "owner": updated["user_id"],
            "plan": new_plan,
            "end_date": updated.get("end_date", "")
        })

    await cb.answer(f"✅ Тариф переключен на {new_plan.upper()}")
    await send_sub_card(cb, updated)
    try:
        await sync_bridge.notify_sync_event(
            cb.bot, event="update_plan",
            token=updated.get("bot_token", ""), username=updated.get("bot_username", ""),
            owner=updated.get("user_id", 0), plan=new_plan,
            end_date=updated.get("end_date", ""), sub_id=updated.get("id", 0)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:sub:toggle:"))
async def cb_admin_sub_toggle(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    sub_id = int(cb.data.split(":")[3])
    s = db.get_subscription(sub_id)
    if not s:
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    is_now_active = db.toggle_sub_active(sub_id)
    updated = db.get_subscription(sub_id)

    if manager and s.get("bot_token"):
        bid = manager.bot_id(s["bot_token"])
        if is_now_active:
            manager.spawn({
                "id": bid,
                "token": s["bot_token"],
                "username": s.get("bot_username", ""),
                "owner": s["user_id"],
                "plan": s.get("plan", "standard"),
                "end_date": s.get("end_date", "")
            })
        else:
            manager.stop(bid)

    status_str = "активирована" if is_now_active else "отозвана (деактивирована)"
    await cb.answer(f"✅ Подписка #{sub_id} {status_str}")
    await send_sub_card(cb, updated)
    try:
        await sync_bridge.notify_sync_event(
            cb.bot, event="start_bot" if is_now_active else "stop_bot",
            token=s.get("bot_token", ""), username=s.get("bot_username", ""),
            owner=s.get("user_id", 0), plan=s.get("plan", "standard"),
            end_date=s.get("end_date", ""), sub_id=sub_id
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:sub:unbind:"))
async def cb_admin_sub_unbind(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    sub_id = int(cb.data.split(":")[3])
    s = db.get_subscription(sub_id)
    if not s:
        await cb.answer("Подписка не найдена", show_alert=True)
        return

    old_token = s.get("bot_token")
    if old_token and manager:
        manager.stop(manager.bot_id(old_token))

    db.unbind_sub_bot(sub_id)
    updated = db.get_subscription(sub_id)
    await cb.answer("✅ Бот отвязан от подписки")
    await send_sub_card(cb, updated)


@router.callback_query(F.data.startswith("admin:sub:"))
async def cb_admin_sub_card(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    parts = cb.data.split(":")
    if len(parts) != 3:
        return

    sub_id = int(parts[2])
    s = db.get_subscription(sub_id)
    if not s:
        await cb.answer("Подписка не найдена!", show_alert=True)
        return

    await cb.answer()
    await send_sub_card(cb, s)


@router.callback_query(F.data == "admin:search")
async def cb_admin_search_prompt(cb: CallbackQuery, state: FSMContext):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return

    await state.set_state(UserStates.waiting_for_search_query)
    await cb.answer()

    text = (
        "🔍 <b>Поиск подписки</b>\n\n"
        "Отправьте для поиска:\n"
        "• Telegram ID пользователя (например: <code>7116116919</code>)\n"
        "• Username пользователя (например: <code>bonzayka</code>)\n"
        "• Юзернейм привязанного бота (например: <code>my_def_bot</code>)\n"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin:subs:0")]
    ])
    await cb.message.edit_text(text, reply_markup=markup)


@router.message(UserStates.waiting_for_search_query)
async def process_search_query(message: Message, state: FSMContext):
    if not check_is_admin(message.from_user.id):
        await state.clear()
        return

    query = (message.text or "").strip().lstrip("@")
    if query.startswith("/"):
        await state.clear()
        await message.answer("Поиск отменен.")
        return

    await state.clear()
    subs = db.find_user_subs(query)
    if not subs:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Попробовать еще раз", callback_data="admin:search")],
            [InlineKeyboardButton(text="👥 Все подписки", callback_data="admin:subs:0")],
        ])
        await message.answer(f"По запросу <code>{esc(query)}</code> ничего не найдено.", reply_markup=markup)
        return

    rows = []
    for s in subs:
        is_act = bool(s.get("is_active", 1))
        badge = "💎" if s.get("plan", "").lower() == "pro" else "🛡️"
        status_dot = "🟢" if is_act else "🔴"
        u_label = f"@{s['user_username']}" if s.get("user_username") else f"ID {s['user_id']}"
        b_label = f"(@{s['bot_username']})" if s.get("bot_username") else "(нет бота)"
        btn_text = f"{status_dot} {badge} #{s['id']} {u_label} {b_label}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"admin:sub:{s['id']}")])

    rows.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="admin:search")])
    rows.append([InlineKeyboardButton(text="👥 Все подписки", callback_data="admin:subs:0")])

    await message.answer(
        f"🔍 Найдено подписок: <b>{len(subs)}</b>\nВыберите подписку для управления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return
    await cb.answer()

    st = db.get_stats()
    text = (
        f"📊 <b>Детальная статистика Chat Defense</b>\n\n"
        f"👤 Зарегистрировано пользователей: <b>{st['users']}</b>\n"
        f"💳 Оплаченных заказов: <b>{st['paid_orders']}</b>\n"
        f"💰 Общий доход: <b>{st['total_rub']} руб</b>\n"
        f"🟢 Активных подписок сейчас: <b>{st['active_subs']}</b>\n\n"
        f"<i>Статистика обновляется в режиме реального времени.</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление подписками", callback_data="admin:subs:0")],
        [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin:menu")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "admin:give")
async def cb_admin_give(cb: CallbackQuery):
    if not check_is_admin(cb.from_user.id):
        await cb.answer("Доступ запрещен", show_alert=True)
        return
    await cb.answer()
    text = (
        "🎁 <b>Выдача подписки пользователю</b>\n\n"
        "Используйте команду:\n"
        "<code>/give_sub &lt;user_id&gt; &lt;months&gt; &lt;standard|pro&gt;</code>\n\n"
        "Примеры:\n"
        "• <code>/give_sub 7116116919 1 pro</code> (на 1 месяц PRO)\n"
        "• <code>/give_sub 7116116919 12 pro</code> (на 1 год PRO)\n"
        "• <code>/give_sub me 3 standard</code> (себе на 3 мес Обычный)"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В админку", callback_data="admin:menu")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "admin:noop")
async def cb_admin_noop(cb: CallbackQuery):
    await cb.answer()
