# -*- coding: utf-8 -*-
"""
Обработчики сообщений и команд бота продаж Chat Defense.
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

    gen_pass = f"def_{secrets.token_hex(4)}"

    if manager:
        ok = manager.add(token, me.username or "", owner=uid, password=gen_pass)
        if not ok:
            manager.spawn({"id": manager.bot_id(token), "token": token, "username": me.username or "",
                           "owner": uid, "password": gen_pass})

    if sub_id:
        db.update_sub_bot(sub_id, str(me.id), me.username or "", token)

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
        b_name = f"@{s['bot_username']}" if s.get("bot_username") else "⚠️ Токен еще не привязан"
        text += (
            f"• <b>Тариф:</b> {s['plan'].upper()}\n"
            f"  <b>Бот:</b> {b_name}\n"
            f"  <b>Действует до:</b> {s['end_date']}\n\n"
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
    await message.answer(
        f"✅ Подписка <b>{plan.upper()}</b> на <b>{months} мес.</b> выдана пользователю <code>{target_uid}</code>!\n"
        f"Действует до: <b>{sub_info['end_date']}</b>"
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
