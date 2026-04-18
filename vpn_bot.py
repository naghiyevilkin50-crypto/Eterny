import asyncio
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
# Токен бота — его лучше брать из переменных окружения, но для простоты вставим прямо
BOT_TOKEN = "8671810898:AAELwd5oEBhV5PwgSNq8bYaTP7SAX1Mvpdg"  # ← твой токен
ADMIN_ID = 8115647701

PRICE_30_DAYS = 300
PRICE_60_DAYS = 500
PRICE_90_DAYS = 800
REFERRAL_BONUS_DAYS = 7

# ========== ИНИЦИАЛИЗАЦИЯ ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== БАЗА ДАННЫХ ==========
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
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                date TEXT,
                has_paid BOOLEAN DEFAULT 0,
                bonus_given BOOLEAN DEFAULT 0
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

def generate_vpn_key() -> str:
    return f"vless://{secrets.token_hex(16)}@eternyvpn.com:443?security=tls#Eterny_VPN"

def get_user(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_user(user_id: int, username: str = None, first_name: str = None, referrer_id: int = None):
    vpn_key = generate_vpn_key()
    join_date = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, vpn_key, join_date, referrer_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, vpn_key, join_date, referrer_id))
        conn.commit()
        if referrer_id:
            cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, date)
                VALUES (?, ?, ?)
            ''', (referrer_id, user_id, join_date))
            conn.commit()

def activate_subscription(user_id: int, days: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT subscription_end, referral_bonus_days FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        current_end = datetime.fromisoformat(row[0]) if row and row[0] else datetime.now()
        bonus_days = row[1] if row else 0
        new_end = max(current_end, datetime.now()) + timedelta(days=days + bonus_days)
        cursor.execute('''
            UPDATE users 
            SET subscription_end = ?, is_active = 1, referral_bonus_days = 0
            WHERE user_id = ?
        ''', (new_end.isoformat(), user_id))
        conn.commit()

def add_referral_bonus(referrer_id: int, referred_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT bonus_given FROM referrals 
            WHERE referrer_id = ? AND referred_id = ?
        ''', (referrer_id, referred_id))
        row = cursor.fetchone()
        if row and not row[0]:
            cursor.execute('''
                UPDATE users 
                SET referral_count = referral_count + 1,
                    referral_paid_count = referral_paid_count + 1,
                    referral_bonus_days = referral_bonus_days + ?
                WHERE user_id = ?
            ''', (REFERRAL_BONUS_DAYS, referrer_id))
            cursor.execute('''
                UPDATE users SET referral_bonus_days = referral_bonus_days + ?
                WHERE user_id = ?
            ''', (REFERRAL_BONUS_DAYS, referred_id))
            cursor.execute('''
                UPDATE referrals SET bonus_given = 1, has_paid = 1
                WHERE referrer_id = ? AND referred_id = ?
            ''', (referrer_id, referred_id))
            conn.commit()
            return True
        return False

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(is_active: bool = False) -> ReplyKeyboardMarkup:
    if is_active:
        buttons = [
            [KeyboardButton(text="🔌 Подключиться")],
            [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="🎁 Бонусы")],
            [KeyboardButton(text="📖 Инструкции и поддержка")]
        ]
    else:
        buttons = [
            [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="🎁 Бонусы")],
            [KeyboardButton(text="📖 Инструкции и поддержка")]
        ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_payment_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Банковская карта РФ", callback_data="pay_card")],
        [InlineKeyboardButton(text="⭐️ Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton(text="₿ Криптовалюта", callback_data="pay_crypto")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_tariffs_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"30 дней - {PRICE_30_DAYS}₽", callback_data="buy_30days")],
        [InlineKeyboardButton(text=f"60 дней - {PRICE_60_DAYS}₽", callback_data="buy_60days")],
        [InlineKeyboardButton(text=f"90 дней - {PRICE_90_DAYS}₽", callback_data="buy_90days")],
        [InlineKeyboardButton(text="🌍 Список серверов", callback_data="servers")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_bonus_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🎫 Ввести промокод")],
        [KeyboardButton(text="👥 Пригласить друга")],
        [KeyboardButton(text="🤝 Партнёрская программа")],
        [KeyboardButton(text="◀️ Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_to_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="◀️ Главное меню")]]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ОБРАБОТЧИКИ ==========
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
    
    if is_active:
        text = f"Привет!\n\nПодписка: Активна\nДо: {expires_str}\n\n👇 Выберите действие:"
    else:
        text = "Привет!\n\nПодписка: Не активна\n\n👇 Выберите действие:"
    
    await message.answer(text, reply_markup=get_main_keyboard(is_active))

@dp.message(lambda message: message.text == "🔌 Подключиться")
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

@dp.message(lambda message: message.text == "💳 Оплата")
async def payment_handler(message: types.Message):
    await message.answer("Оплата\n\nВыберите способ оплаты:", reply_markup=get_payment_keyboard())

@dp.message(lambda message: message.text == "🎁 Бонусы")
async def bonus_handler(message: types.Message):
    user = get_user(message.from_user.id)
    if user and user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            text = f"# Бонусное меню\nактивируйте бонусы\n\n**Привет!**\n\n- Подписка: Активна\n\n**До:** {end_date.strftime('%d.%m.%Y %H:%M:%S')}\n\n👇 Выберите действие:"
        else:
            text = "# Бонусное меню\nактивируйте бонусы\n\n**Привет!**\n\n- Подписка: Не активна\n\n👇 Выберите действие:"
    else:
        text = "# Бонусное меню\nактивируйте бонусы\n\n**Привет!**\n\n- Подписка: Не активна\n\n👇 Выберите действие:"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_bonus_keyboard())

@dp.message(lambda message: message.text == "👥 Пригласить друга")
async def invite_handler(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    user = get_user(user_id)
    referral_count = user.get("referral_count", 0) if user else 0
    referral_paid_count = user.get("referral_paid_count", 0) if user else 0
    await message.answer(
        f"# Реферальная система\n\n"
        f"Получайте бонусные дни за приглашённых друзей.\n\n"
        f"Когда пользователь, открывший вашу реферальную ссылку, оформит подписку сроком на 1 месяц или больше, "
        f"вы оба получите по {REFERRAL_BONUS_DAYS} дней подписки.\n\n"
        f"Приглашенных пользователей: {referral_count}\n"
        f"Оплативших: {referral_paid_count}\n\n"
        f"Ваша реферальная ссылка:\n`{referral_link}`",
        parse_mode="Markdown",
        reply_markup=get_back_to_menu_keyboard()
    )

@dp.message(lambda message: message.text == "🎫 Ввести промокод")
async def promo_handler(message: types.Message):
    await message.answer("🎫 Введите промокод:\n\nОтправьте код одним сообщением.", reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda message: message.text == "🤝 Партнёрская программа")
async def partner_handler(message: types.Message):
    await message.answer("🤝 Партнёрская программа\n\nСкоро здесь появится информация о партнёрской программе.\nСледите за обновлениями!", reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda message: message.text == "📖 Инструкции и поддержка")
async def instructions_handler(message: types.Message):
    await message.answer(
        "# Инструкции\n\n"
        "**📱 Инструкция Android/Android TV**\n"
        "**💻 Инструкция Windows/MacOS/Linux**\n\n"
        "**🔄 Как обновить подписку:**\n"
        "Инструкция\n\n"
        "**📱 Как подключить второе устройство:**\n"
        "Инструкция\n\n"
        "Все инструкции тут: [Ссылка]\n\n"
        "Перед обращением в поддержку ознакомьтесь с часто задаваемыми вопросами.\n\n"
        "📞 **Поддержка:** @eterny_support",
        parse_mode="Markdown",
        reply_markup=get_back_to_menu_keyboard()
    )

@dp.message(lambda message: message.text == "◀️ Главное меню")
async def back_to_main_handler(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    is_active = False
    expires_str = ""
    if user and user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            is_active = True
            expires_str = end_date.strftime("%d.%m.%Y %H:%M:%S")
    if is_active:
        text = f"Привет!\n\nПодписка: Активна\nДо: {expires_str}\n\n👇 Выберите действие:"
    else:
        text = "Привет!\n\nПодписка: Не активна\n\n👇 Выберите действие:"
    await message.answer(text, reply_markup=get_main_keyboard(is_active))

# ========== INLINE-КНОПКИ ==========
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    user_id = callback.from_user.id
    user = get_user(user_id)
    is_active = False
    if user and user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            is_active = True
    await callback.message.answer("Главное меню", reply_markup=get_main_keyboard(is_active))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_payment")
async def back_to_payment_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Оплата\n\nВыберите способ оплаты:", reply_markup=get_payment_keyboard())
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
    await callback.message.edit_text(
        "🌍 Список серверов\n\n"
        "• 🇳🇱 Нидерланды\n"
        "• 🇸🇬 Сингапур\n"
        "• 🇺🇸 США (Лос-Анджелес)\n"
        "• 🇺🇸 США (Нью-Йорк)\n"
        "• 🇩🇪 Германия\n"
        "• 🇬🇧 Великобритания\n"
        "• 🇫🇷 Франция\n"
        "• 🇯🇵 Япония",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_callback(callback: types.CallbackQuery):
    if "30" in callback.data:
        days = 30
        price = PRICE_30_DAYS
    elif "60" in callback.data:
        days = 60
        price = PRICE_60_DAYS
    else:
        days = 90
        price = PRICE_90_DAYS
    await callback.message.edit_text(
        f"💳 Оплата\n\nТариф: {days} дней - {price}₽\n\n"
        f"🔗 Ссылка для оплаты (заглушка):\n`https://eternyvpn.com/pay/{callback.from_user.id}/{days}`\n\n"
        f"⚠️ После оплаты нажмите «Проверить оплату»",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment_{days}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_payment_"))
async def check_payment_callback(callback: types.CallbackQuery):
    days = int(callback.data.replace("check_payment_", ""))
    user_id = callback.from_user.id
    activate_subscription(user_id, days)
    user = get_user(user_id)
    if user and user.get("referrer_id"):
        add_referral_bonus(user["referrer_id"], user_id)
    await callback.message.edit_text(
        f"✅ Оплата подтверждена!\n\nПодписка на {days} дней активирована.\n\n🔌 Нажмите «Подключиться», чтобы получить ключ."
    )
    await callback.answer("Подписка активирована!")

# ========== АДМИН-КОМАНДЫ ==========
@dp.message(lambda message: message.text == "/stats" and message.from_user.id == ADMIN_ID)
async def stats_command(message: types.Message):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE bonus_given = 1")
        total_refs = cursor.fetchone()[0]
    await message.answer(
        f"📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Активных подписок: {active_users}\n"
        f"👥 Рефералов оплативших: {total_refs}"
    )

# ========== ЗАПУСК ==========
async def main():
    init_db()
    print("🤖 Бот Eterny VPN запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())