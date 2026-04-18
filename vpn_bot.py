import asyncio
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
import os
import random
import string

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8671810898:AAELwd5oEBhV5PwgSNq8bYaTP7SAX1Mvpdg"

ADMIN_IDS = [8115647701]   # твой ID

PRICE_30_DAYS = 159
PRICE_90_DAYS = 419
PRICE_180_DAYS = 799
REFERRAL_BONUS_DAYS = 7

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- БАЗА ДАННЫХ ----------
def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                vpn_key TEXT UNIQUE,
                subscription_end TEXT,
                is_active BOOLEAN DEFAULT 0,
                referrer_id INTEGER,
                referral_count INTEGER DEFAULT 0,
                referral_paid_count INTEGER DEFAULT 0,
                referral_bonus_days INTEGER DEFAULT 0,
                join_date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                bonus_days INTEGER DEFAULT 0,
                expires_at TEXT,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                promo_code TEXT,
                used_at TEXT
            )
        ''')
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect('vpn_bot.db')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def generate_vpn_key():
    return f"vless://{secrets.token_hex(16)}@eternyvpn.com:443?security=tls#Eterny_VPN"

def get_user(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def create_user(user_id, username=None, first_name=None, referrer_id=None):
    vpn_key = generate_vpn_key()
    join_date = datetime.now().isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO users (user_id, username, first_name, vpn_key, join_date, referrer_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, vpn_key, join_date, referrer_id))
        conn.commit()
        if referrer_id:
            cur.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()

def activate_subscription(user_id, days):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        current_end = datetime.fromisoformat(row[0]) if row and row[0] else datetime.now()
        new_end = max(current_end, datetime.now()) + timedelta(days=days)
        cur.execute("UPDATE users SET subscription_end = ?, is_active = 1 WHERE user_id = ?", (new_end.isoformat(), user_id))
        conn.commit()

def generate_promo_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def create_promo_code(code, bonus_days, max_uses, expires_days):
    expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO promocodes (code, bonus_days, expires_at, max_uses, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (code, bonus_days, expires_at, max_uses, datetime.now().isoformat()))
        conn.commit()

def apply_promo_code(user_id, code):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM promocodes WHERE code = ? 
            AND (expires_at > ? OR expires_at IS NULL)
            AND (max_uses > used_count OR max_uses = 0)
        ''', (code, datetime.now().isoformat()))
        promo = cur.fetchone()
        if not promo:
            return False, "Промокод недействителен или истёк"
        promo = dict(promo)
        cur.execute("SELECT * FROM user_promocodes WHERE user_id = ? AND promo_code = ?", (user_id, code))
        if cur.fetchone():
            return False, "Вы уже использовали этот промокод"
        if promo['bonus_days'] > 0:
            cur.execute("UPDATE users SET referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (promo['bonus_days'], user_id))
        cur.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,))
        cur.execute("INSERT INTO user_promocodes (user_id, promo_code, used_at) VALUES (?, ?, ?)", (user_id, code, datetime.now().isoformat()))
        conn.commit()
        return True, f"Промокод активирован! +{promo['bonus_days']} бонусных дней"

def get_referral_stats(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND is_active = 1", (user_id,))
        paid = cur.fetchone()[0]
        return total, paid

def get_top_referrers(limit=3):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT user_id, username, first_name, referral_count 
            FROM users WHERE referral_count > 0 ORDER BY referral_count DESC LIMIT ?
        ''', (limit,))
        return cur.fetchall()

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard(is_active=False, is_admin=False):
    buttons = []
    if is_active:
        buttons.append([KeyboardButton(text="🔌 Подключиться")])
    buttons.append([KeyboardButton(text="💳 Оплата"), KeyboardButton(text="🎁 Бонусы")])
    buttons.append([KeyboardButton(text="❓ Справка")])
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Админ панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_payment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Банковская карта РФ", callback_data="pay_card")],
        [InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton(text="₿ Криптовалюта", callback_data="pay_crypto")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")]
    ])

def get_tariffs_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"30 дней - {PRICE_30_DAYS}₽", callback_data="buy_30days")],
        [InlineKeyboardButton(text=f"90 дней - {PRICE_90_DAYS}₽", callback_data="buy_90days")],
        [InlineKeyboardButton(text=f"180 дней - {PRICE_180_DAYS}₽", callback_data="buy_180days")],
        [InlineKeyboardButton(text="🌍 Список серверов", callback_data="servers")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]
    ])

def get_bonus_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎫 Ввести промокод")],
        [KeyboardButton(text="👥 Пригласить друга")],
        [KeyboardButton(text="🤝 Партнёрская программа")],
        [KeyboardButton(text="◀️ Главное меню")]
    ], resize_keyboard=True)

def get_back_to_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="◀️ Главное меню")]], resize_keyboard=True)

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(CommandStart())
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id == user_id:
                referrer_id = None
        except ValueError:
            pass

    user = get_user(user_id)
    if not user:
        create_user(user_id, username, first_name, referrer_id)
        user = get_user(user_id)

    is_active = False
    expires_str = ""
    if user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            is_active = True
            expires_str = end_date.strftime("%d.%m.%Y %H:%M:%S")

    text = (f"Добро пожаловать в EternyVPN!\n\n"
            f"Твой личный доступ к свободному интернету\n"
            f"Без логов   Без блокировок   Без лимитов\n\n"
            f"Протокол: VLESS + XTLS (Reality)\n"
            f"Сервера: Нидерланды\n"
            f"Скорость: до 1 Гбит/с\n"
            f"Аптайм: 99.9%\n\n")
    if is_active:
        text += f"✅ Подписка активна до {expires_str}"
    else:
        text += "❌ Подписка не активна. Купите ключ в разделе «Оплата»."

    await message.answer(text, reply_markup=get_main_keyboard(is_active, user_id in ADMIN_IDS))

@dp.message(lambda m: m.text == "❓ Справка")
async def help_handler(message: types.Message):
    text = (
        "📖 Как пользоваться ботом:\n\n"
        "1. Купите ключ через раздел «💳 Оплата»\n"
        "2. Установите VPN-клиент: Hiddify, v2rayNG или V2Box\n"
        "3. Импортируйте полученный ключ в приложение\n"
        "4. Подключайтесь!\n\n"
        "🔗 Подробная инструкция:\n"
        "https://telegra.ph/Kak-nastroit-VPN-Gajd-za-2-minuty-03-27\n\n"
        "📞 Поддержка: @eterny_support"
    )
    await message.answer(text, reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "🔌 Подключиться")
async def connect_handler(message: types.Message):
    user = get_user(message.from_user.id)
    if user and user.get("vpn_key"):
        await message.answer(
            f"🔗 Ваша ссылка для подключения:\n\n`{user['vpn_key']}`\n\n📱 Инструкция: нажми «Импорт» в приложении → «Вставить из буфера»",
            parse_mode="Markdown",
            reply_markup=get_back_to_menu_keyboard()
        )
    else:
        await message.answer("❌ Ошибка: ключ не найден.", reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "💳 Оплата")
async def payment_handler(message: types.Message):
    await message.answer("Выберите способ оплаты:", reply_markup=get_payment_keyboard())

@dp.message(lambda m: m.text == "🎁 Бонусы")
async def bonus_handler(message: types.Message):
    user = get_user(message.from_user.id)
    status = "Активна" if user and user.get("subscription_end") and datetime.fromisoformat(user["subscription_end"]) > datetime.now() else "Не активна"
    text = f"🎁 Бонусное меню\n\nПодписка: {status}\n\nПриглашай друзей и получай бонусные дни!"
    await message.answer(text, reply_markup=get_bonus_keyboard())

@dp.message(lambda m: m.text == "👥 Пригласить друга")
async def invite_handler(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    total, paid = get_referral_stats(user_id)
    text = (f"👥 Реферальная программа\n\n"
            f"Приглашено: {total}\n"
            f"Оплатило: {paid}\n\n"
            f"➕ За каждого приглашённого, который купит подписку, вы получите +{REFERRAL_BONUS_DAYS} дней.\n\n"
            f"Ваша ссылка:\n{link}")
    await message.answer(text, reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "🎫 Ввести промокод")
async def promo_input_start(message: types.Message):
    await message.answer("Введите промокод одним сообщением:", reply_markup=get_back_to_menu_keyboard())

# Хэндлер для промокодов (только для обычных пользователей, НЕ админов)
@dp.message(lambda m: m.text and m.text not in ["🎫 Ввести промокод", "👥 Пригласить друга", "🤝 Партнёрская программа", "◀️ Главное меню", "💳 Оплата", "🎁 Бонусы", "❓ Справка", "🔌 Подключиться", "👑 Админ панель"] and m.from_user.id not in ADMIN_IDS)
async def check_promo(message: types.Message):
    code = message.text.strip().upper()
    success, msg = apply_promo_code(message.from_user.id, code)
    await message.answer(msg, reply_markup=get_bonus_keyboard())

@dp.message(lambda m: m.text == "🤝 Партнёрская программа")
async def partner_handler(message: types.Message):
    await message.answer("🤝 Партнёрская программа в разработке. Следите за новостями!", reply_markup=get_back_to_menu_keyboard())

# ---------- ИНЛАЙН КОЛБЭКИ ----------
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    user_id = callback.from_user.id
    user = get_user(user_id)
    is_active = user and user.get("subscription_end") and datetime.fromisoformat(user["subscription_end"]) > datetime.now()
    await callback.message.answer("Главное меню", reply_markup=get_main_keyboard(is_active, user_id in ADMIN_IDS))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_payment")
async def back_to_payment_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите способ оплаты:", reply_markup=get_payment_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "pay_card")
async def pay_card_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("💳 Банковская карта РФ\n\nВыберите тариф:", reply_markup=get_tariffs_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "pay_stars")
async def pay_stars_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("⭐️ Telegram Stars\n\nВыберите тариф:", reply_markup=get_tariffs_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "pay_crypto")
async def pay_crypto_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("₿ Криптовалюта\n\nВыберите тариф:", reply_markup=get_tariffs_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "servers")
async def servers_callback(callback: types.CallbackQuery):
    text = "🌍 Список серверов:\n• 🇳🇱 Нидерланды\n• 🇸🇬 Сингапур\n• 🇺🇸 США (Лос-Анджелес)\n• 🇺🇸 США (Нью-Йорк)\n• 🇩🇪 Германия\n• 🇬🇧 Великобритания\n• 🇫🇷 Франция\n• 🇯🇵 Япония"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_callback(callback: types.CallbackQuery):
    if "30" in callback.data:
        days, price = 30, PRICE_30_DAYS
    elif "90" in callback.data:
        days, price = 90, PRICE_90_DAYS
    else:
        days, price = 180, PRICE_180_DAYS
    await callback.message.edit_text(
        f"💳 Оплата\n\nТариф: {days} дней - {price}₽\n\n🔗 Ссылка для оплаты (заглушка):\n`https://eternyvpn.com/pay/{callback.from_user.id}/{days}`\n\n⚠️ После оплаты нажмите «Проверить оплату»",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_{days}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_"))
async def check_payment_callback(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    activate_subscription(user_id, days)
    user = get_user(user_id)
    if user and user.get("referrer_id"):
        referrer_id = user["referrer_id"]
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET referral_paid_count = referral_paid_count + 1 WHERE user_id = ?", (referrer_id,))
            cur.execute("UPDATE users SET referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (REFERRAL_BONUS_DAYS, referrer_id))
            cur.execute("UPDATE users SET referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (REFERRAL_BONUS_DAYS, user_id))
            conn.commit()
    await callback.message.edit_text(f"✅ Оплата подтверждена!\n\nПодписка на {days} дней активирована.\n\n🔌 Нажмите «Подключиться», чтобы получить ключ.")
    await callback.answer("Подписка активирована!")

# ---------- АДМИН-КОМАНДЫ ----------
@dp.message(Command("broadcast"))
async def broadcast_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await message.answer("Напишите текст после /broadcast, например:\n/broadcast Всем привет!")
        return
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
    count = 0
    for row in users:
        try:
            await bot.send_message(row[0], text)
            count += 1
        except:
            pass
    await message.answer(f"✅ Рассылка завершена. Отправлено {count} пользователям.")

@dp.message(lambda m: m.text == "👑 Админ панель" and m.from_user.id in ADMIN_IDS)
async def admin_panel(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎫 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="📢 Рассылка (через /broadcast)", callback_data="admin_mailing_info")],
        [InlineKeyboardButton(text="🏆 Топ рефералов", callback_data="admin_top_ref")],
        [InlineKeyboardButton(text="◀️ Выход", callback_data="back_to_menu")]
    ])
    await message.answer("👑 Админ-панель", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM promocodes")
        promo_count = cur.fetchone()[0]
    text = f"📊 Статистика:\n👥 Всего пользователей: {total}\n✅ Активных подписок: {active}\n🎫 Промокодов создано: {promo_count}"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_top_ref")
async def admin_top_ref(callback: types.CallbackQuery):
    top = get_top_referrers(3)
    if not top:
        text = "🏆 Пока нет рефералов."
    else:
        text = "🏆 Топ пользователей по приглашениям:\n"
        for idx, row in enumerate(top, 1):
            name = row['first_name'] or row['username'] or str(row['user_id'])
            text += f"{idx}. {name} — {row['referral_count']} приглашённых\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_create_promo")
async def admin_create_promo(callback: types.CallbackQuery):
    code = generate_promo_code()
    create_promo_code(code, bonus_days=7, max_uses=10, expires_days=30)
    await callback.message.edit_text(f"🎫 Создан промокод:\n{code}\nБонус: +7 дней\nДействует 30 дней, 10 использований.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_mailing_info")
async def admin_mailing_info(callback: types.CallbackQuery):
    await callback.message.edit_text("📢 Для рассылки используйте команду:\n/broadcast Ваше сообщение\n\nСообщение будет отправлено ВСЕМ пользователям бота.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await admin_panel(callback.message)
    await callback.answer()

# ---------- ЗАПУСК ----------
async def main():
    init_db()
    print("🤖 Бот Eterny VPN запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())