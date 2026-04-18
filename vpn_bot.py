import asyncio
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
import os
import random
import string
import csv
from io import StringIO

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8671810898:AAELwd5oEBhV5PwgSNq8bYaTP7SAX1Mvpdg"

ADMIN_IDS = [8115647701]
SUPPORT_USERNAME = "eterny_support"

PRICE_30_DAYS = 159
PRICE_90_DAYS = 419
PRICE_180_DAYS = 799
REFERRAL_BONUS_DAYS = 7
MAX_REFERRAL_BONUS_DAYS = 30
TRIAL_DAYS = 1

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- FSM ----------
class PromoState(StatesGroup):
    waiting_for_code = State()

class MailingState(StatesGroup):
    waiting_for_text = State()

# ---------- ЯЗЫКИ ----------
LANGUAGES = {
    'ru': {
        'welcome_inactive': "✨ *Добро пожаловать в EternyVPN!* ✨\n\n🔒 Твой личный доступ к свободному интернету\n🔹 Без логов\n🔹 Без блокировок\n🔹 Без лимитов\n\n⚡️ Протокол: *VLESS + XTLS (Reality)*\n🚀 Скорость: *-*\n\n❌ *Подписка не активна.*\n👉 Купи ключ в разделе «💳 Оплата» и наслаждайся свободой!",
        'welcome_active': "✨ *Добро пожаловать в EternyVPN!* ✨\n\n🔒 Твой личный доступ к свободному интернету\n🔹 Без логов\n🔹 Без блокировок\n🔹 Без лимитов\n\n⚡️ Протокол: *VLESS + XTLS (Reality)*\n🚀 Скорость: *-*\n\n✅ *Подписка активна до:* {expires}\n\n👇 Выберите действие:",
        'help': "📖 Как пользоваться ботом:\n\n1. Купите ключ через раздел «💳 Оплата»\n2. Установите VPN-клиент: Hiddify, v2rayNG или V2Box\n3. Импортируйте полученный ключ в приложение\n4. Подключайтесь!\n\n🔗 Подробная инструкция:\nhttps://telegra.ph/Kak-nastroit-VPN-Gajd-za-2-minuty-03-27\n\n📞 Поддержка: @eterny_support",
        'trial_active': "🎁 *Пробный период активирован!*\n\nВы получили {days} день подписки.\nВаш ключ:\n`{key}`\n\nНажмите «🔌 Подключиться», чтобы скопировать.",
        'trial_already': "❌ Вы уже использовали пробный период.",
        'promo_success': "✅ Промокод активирован! +{days} бонусных дней.",
        'promo_invalid': "❌ Промокод недействителен или истёк.",
        'promo_used': "❌ Вы уже использовали этот промокод.",
        'referral_link': "👥 *Реферальная программа*\n\nПриглашено: {total}\nОплатило: {paid}\n\n➕ За каждого приглашённого, который купит подписку, вы получите +{bonus} дней.\n\nВаша ссылка:\n{link}",
        'referral_list': "👥 *Ваши рефералы:*\n{list}",
        'no_referrals': "❌ У вас пока нет приглашённых.",
        'key_resent': "🔑 Ваш ключ:\n`{key}`",
        'key_reset': "✅ Ключ успешно сброшен и заменён на новый.",
        'blacklisted': "⛔ Вы заблокированы. Обратитесь к администратору.",
        'main_menu': "Главное меню",
        'not_admin': "❌ У вас нет прав администратора.",
        'reminder': "⚠️ Ваша подписка истекает через 3 дня. Продлите, чтобы не потерять доступ.",
    },
    'en': {
        'welcome_inactive': "✨ *Welcome to EternyVPN!* ✨\n\n🔒 Your personal access to a free internet\n🔹 No logs\n🔹 No blocks\n🔹 No limits\n\n⚡️ Protocol: *VLESS + XTLS (Reality)*\n🚀 Speed: *-*\n\n❌ *Subscription inactive.*\n👉 Buy a key in the «💳 Payment» section and enjoy freedom!",
        'welcome_active': "✨ *Welcome to EternyVPN!* ✨\n\n🔒 Your personal access to a free internet\n🔹 No logs\n🔹 No blocks\n🔹 No limits\n\n⚡️ Protocol: *VLESS + XTLS (Reality)*\n🚀 Speed: *-*\n\n✅ *Subscription active until:* {expires}\n\n👇 Choose an action:",
        'help': "📖 How to use the bot:\n\n1. Buy a key in the «💳 Payment» section\n2. Install a VPN client: Hiddify, v2rayNG or V2Box\n3. Import the received key into the app\n4. Connect!\n\n🔗 Detailed instructions:\nhttps://telegra.ph/Kak-nastroit-VPN-Gajd-za-2-minuty-03-27\n\n📞 Support: @eterny_support",
        'trial_active': "🎁 *Trial period activated!*\n\nYou received {days} day(s) of subscription.\nYour key:\n`{key}`\n\nClick «🔌 Подключиться» to copy.",
        'trial_already': "❌ You have already used the trial period.",
        'promo_success': "✅ Promocode activated! +{days} bonus days.",
        'promo_invalid': "❌ Promocode invalid or expired.",
        'promo_used': "❌ You have already used this promocode.",
        'referral_link': "👥 *Referral program*\n\nInvited: {total}\nPaid: {paid}\n\n➕ For each invited friend who buys a subscription, you get +{bonus} days.\n\nYour link:\n{link}",
        'referral_list': "👥 *Your referrals:*\n{list}",
        'no_referrals': "❌ You have no referrals yet.",
        'key_resent': "🔑 Your key:\n`{key}`",
        'key_reset': "✅ Key successfully reset and replaced with a new one.",
        'blacklisted': "⛔ You are blocked. Contact the administrator.",
        'main_menu': "Main menu",
        'not_admin': "❌ You are not an administrator.",
        'reminder': "⚠️ Your subscription expires in 3 days. Renew to keep access.",
    }
}

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
                join_date TEXT,
                language TEXT DEFAULT 'ru',
                trial_used BOOLEAN DEFAULT 0
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                days INTEGER,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY
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

def activate_subscription(user_id, days, record_payment=True, amount=0):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT subscription_end, referral_bonus_days FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        current_end = datetime.fromisoformat(row[0]) if row and row[0] else datetime.now()
        bonus_days = row[1] if row else 0
        new_end = max(current_end, datetime.now()) + timedelta(days=days + bonus_days)
        cur.execute('''
            UPDATE users SET subscription_end = ?, is_active = 1, referral_bonus_days = 0 WHERE user_id = ?
        ''', (new_end.isoformat(), user_id))
        conn.commit()
        if record_payment:
            cur.execute('''
                INSERT INTO payments (user_id, amount, days, created_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount, days, datetime.now().isoformat()))
            conn.commit()

def add_referral_bonus(referrer_id, referred_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT referral_bonus_days FROM users WHERE user_id = ?", (referrer_id,))
        row = cur.fetchone()
        current_bonus = row[0] if row else 0
        if current_bonus + REFERRAL_BONUS_DAYS > MAX_REFERRAL_BONUS_DAYS:
            return False
        cur.execute("UPDATE users SET referral_paid_count = referral_paid_count + 1, referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (REFERRAL_BONUS_DAYS, referrer_id))
        cur.execute("UPDATE users SET referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (REFERRAL_BONUS_DAYS, referred_id))
        conn.commit()
        return True

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
            return False, "promo_invalid"
        promo = dict(promo)
        cur.execute("SELECT * FROM user_promocodes WHERE user_id = ? AND promo_code = ?", (user_id, code))
        if cur.fetchone():
            return False, "promo_used"
        if promo['bonus_days'] > 0:
            cur.execute("UPDATE users SET referral_bonus_days = referral_bonus_days + ? WHERE user_id = ?", (promo['bonus_days'], user_id))
        cur.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,))
        cur.execute("INSERT INTO user_promocodes (user_id, promo_code, used_at) VALUES (?, ?, ?)", (user_id, code, datetime.now().isoformat()))
        conn.commit()
        return True, promo['bonus_days']

def get_referral_stats(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND is_active = 1", (user_id,))
        paid = cur.fetchone()[0]
        return total, paid

def get_referral_list(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, first_name, username, is_active FROM users WHERE referrer_id = ?", (user_id,))
        return cur.fetchall()

def get_top_referrers(limit=3):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT user_id, username, first_name, referral_count 
            FROM users WHERE referral_count > 0 ORDER BY referral_count DESC LIMIT ?
        ''', (limit,))
        return cur.fetchall()

def get_active_users():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, subscription_end FROM users WHERE is_active = 1")
        return cur.fetchall()

def get_payment_history(user_id=None):
    with get_db() as conn:
        cur = conn.cursor()
        if user_id:
            cur.execute("SELECT amount, days, created_at FROM payments WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        else:
            cur.execute("SELECT user_id, amount, days, created_at FROM payments ORDER BY created_at DESC")
        return cur.fetchall()

def export_users_to_csv():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, subscription_end, is_active, referrer_id, referral_count, join_date FROM users")
        rows = cur.fetchall()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['user_id', 'username', 'first_name', 'subscription_end', 'is_active', 'referrer_id', 'referral_count', 'join_date'])
        for row in rows:
            writer.writerow(list(row))
        return output.getvalue()

def reset_user_key(user_id):
    new_key = generate_vpn_key()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET vpn_key = ? WHERE user_id = ?", (new_key, user_id))
        conn.commit()
        return new_key

def grant_trial(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT trial_used FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            return False
        cur.execute("UPDATE users SET trial_used = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        activate_subscription(user_id, TRIAL_DAYS, record_payment=False)
        user = get_user(user_id)
        return user['vpn_key']

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard(is_active=False, is_admin=False, lang='ru'):
    buttons = []
    if is_active:
        buttons.append([KeyboardButton(text="🔌 Подключиться")])
    buttons.append([KeyboardButton(text="💳 Оплата"), KeyboardButton(text="🎁 Бонусы")])
    buttons.append([KeyboardButton(text="❓ Справка"), KeyboardButton(text="🎁 Пробный период")])
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

def get_bonus_keyboard(lang='ru'):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎫 Ввести промокод")],
        [KeyboardButton(text="👥 Пригласить друга")],
        [KeyboardButton(text="📊 Мои рефералы")],
        [KeyboardButton(text="🔄 Сбросить ключ")],
        [KeyboardButton(text="◀️ Главное меню")]
    ], resize_keyboard=True)

def get_back_to_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="◀️ Главное меню")]], resize_keyboard=True)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎫 Промокоды (статистика)", callback_data="admin_promo_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton(text="👥 Активные пользователи", callback_data="admin_active_users")],
        [InlineKeyboardButton(text="📜 История платежей", callback_data="admin_payments")],
        [InlineKeyboardButton(text="📈 График нагрузки", callback_data="admin_load")],
        [InlineKeyboardButton(text="📤 Экспорт базы (CSV)", callback_data="admin_export")],
        [InlineKeyboardButton(text="🎫 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🏆 Топ рефералов", callback_data="admin_top_ref")],
        [InlineKeyboardButton(text="◀️ Выход", callback_data="back_to_menu")]
    ])

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
async def get_user_lang(user_id):
    user = get_user(user_id)
    if user and user.get('language'):
        return user['language']
    return 'ru'

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(CommandStart())
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Проверка чёрного списка
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            await message.answer("⛔ Вы заблокированы.")
            return

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
        # Уведомление админу о новом пользователе
        for admin in ADMIN_IDS:
            await bot.send_message(admin, f"🆕 Новый пользователь!\nID: {user_id}\nUsername: @{username}\nИмя: {first_name}")

    lang = user.get('language', 'ru')
    is_active = False
    expires_str = ""
    if user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            is_active = True
            expires_str = end_date.strftime("%d.%m.%Y %H:%M:%S")

    if is_active:
        text = LANGUAGES[lang]['welcome_active'].format(expires=expires_str)
    else:
        text = LANGUAGES[lang]['welcome_inactive']

    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(is_active, user_id in ADMIN_IDS, lang))

@dp.message(lambda m: m.text == "❓ Справка")
async def help_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    text = LANGUAGES[lang]['help']
    await message.answer(text, reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "🔌 Подключиться")
async def connect_handler(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    lang = await get_user_lang(user_id)
    if user and user.get("vpn_key"):
        await message.answer(
            f"🔗 Ваша ссылка для подключения:\n\n{user['vpn_key']}\n\n📱 Инструкция: нажми «Импорт» в приложении → «Вставить из буфера»",
            reply_markup=get_back_to_menu_keyboard()
        )
    else:
        await message.answer("❌ Ошибка: ключ не найден.", reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "💳 Оплата")
async def payment_handler(message: types.Message):
    await message.answer("Выберите способ оплаты:", reply_markup=get_payment_keyboard())

@dp.message(lambda m: m.text == "🎁 Бонусы")
async def bonus_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    await message.answer("🎁 Бонусное меню", reply_markup=get_bonus_keyboard(lang))

@dp.message(lambda m: m.text == "👥 Пригласить друга")
async def invite_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    total, paid = get_referral_stats(user_id)
    text = LANGUAGES[lang]['referral_link'].format(total=total, paid=paid, bonus=REFERRAL_BONUS_DAYS, link=link)
    await message.answer(text, parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "📊 Мои рефералы")
async def my_referrals_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    referrals = get_referral_list(user_id)
    if not referrals:
        await message.answer(LANGUAGES[lang]['no_referrals'], reply_markup=get_back_to_menu_keyboard())
        return
    lines = []
    for ref in referrals:
        name = ref['first_name'] or ref['username'] or str(ref['user_id'])
        status = "✅" if ref['is_active'] else "❌"
        lines.append(f"{status} {name} (ID: {ref['user_id']})")
    text = LANGUAGES[lang]['referral_list'].format(list="\n".join(lines))
    await message.answer(text, reply_markup=get_back_to_menu_keyboard())

@dp.message(lambda m: m.text == "🔄 Сбросить ключ")
async def reset_key_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    new_key = reset_user_key(user_id)
    await message.answer(LANGUAGES[lang]['key_reset'], reply_markup=get_bonus_keyboard(lang))
    await message.answer(LANGUAGES[lang]['key_resent'].format(key=new_key), parse_mode="Markdown")

@dp.message(lambda m: m.text == "🎁 Пробный период")
async def trial_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    key = grant_trial(user_id)
    if key:
        await message.answer(LANGUAGES[lang]['trial_active'].format(days=TRIAL_DAYS, key=key), parse_mode="Markdown", reply_markup=get_main_keyboard(True, user_id in ADMIN_IDS, lang))
        for admin in ADMIN_IDS:
            await bot.send_message(admin, f"🔑 Пользователь {user_id} получил пробный ключ.")
    else:
        await message.answer(LANGUAGES[lang]['trial_already'], reply_markup=get_main_keyboard(False, user_id in ADMIN_IDS, lang))

@dp.message(lambda m: m.text == "🎫 Ввести промокод")
async def promo_input_start(message: types.Message, state: FSMContext):
    await state.set_state(PromoState.waiting_for_code)
    await message.answer("Введите промокод:", reply_markup=get_back_to_menu_keyboard())

@dp.message(PromoState.waiting_for_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    code = message.text.strip().upper()
    success, result = apply_promo_code(user_id, code)
    if success:
        await message.answer(LANGUAGES[lang]['promo_success'].format(days=result), reply_markup=get_bonus_keyboard(lang))
    else:
        await message.answer(LANGUAGES[lang][result], reply_markup=get_bonus_keyboard(lang))
    await state.clear()

@dp.message(lambda m: m.text == "◀️ Главное меню")
async def back_to_main_handler(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    lang = await get_user_lang(user_id)
    is_active = False
    expires_str = ""
    if user and user.get("subscription_end"):
        end_date = datetime.fromisoformat(user["subscription_end"])
        if end_date > datetime.now():
            is_active = True
            expires_str = end_date.strftime("%d.%m.%Y %H:%M:%S")
    if is_active:
        text = LANGUAGES[lang]['welcome_active'].format(expires=expires_str)
    else:
        text = LANGUAGES[lang]['welcome_inactive']
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(is_active, user_id in ADMIN_IDS, lang))

# ---------- ОБРАБОТКА ЛЮБОГО ДРУГОГО ТЕКСТА (игнор) ----------
@dp.message()
async def ignore_all_other(message: types.Message):
    # Просто игнорируем всё, что не обработано выше
    pass

# ---------- ИНЛАЙН-КОЛБЭКИ ----------
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    user_id = callback.from_user.id
    user = get_user(user_id)
    lang = await get_user_lang(user_id)
    is_active = user and user.get("subscription_end") and datetime.fromisoformat(user["subscription_end"]) > datetime.now()
    if is_active:
        text = LANGUAGES[lang]['welcome_active'].format(expires=datetime.fromisoformat(user["subscription_end"]).strftime("%d.%m.%Y %H:%M:%S"))
    else:
        text = LANGUAGES[lang]['welcome_inactive']
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(is_active, user_id in ADMIN_IDS, lang))
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
        f"💳 Оплата\n\nТариф: {days} дней - {price}₽\n\n🔗 Ссылка для оплаты (заглушка):\nhttps://eternyvpn.com/pay/{callback.from_user.id}/{days}\n\n⚠️ После оплаты нажмите «Проверить оплату»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_{days}_{price}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_payment")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_"))
async def check_payment_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    days = int(parts[1])
    price = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id
    lang = await get_user_lang(user_id)
    activate_subscription(user_id, days, amount=price)
    user = get_user(user_id)
    if user and user.get("referrer_id"):
        add_referral_bonus(user["referrer_id"], user_id)
    await callback.message.edit_text(f"✅ Оплата подтверждена!\n\nПодписка на {days} дней активирована.\n\n🔌 Нажмите «Подключиться», чтобы получить ключ.")
    await callback.answer("Подписка активирована!")

# ---------- АДМИН-ПАНЕЛЬ ----------
@dp.message(lambda m: m.text == "👑 Админ панель" and m.from_user.id in ADMIN_IDS)
async def admin_panel(message: types.Message):
    await message.answer("👑 Админ-панель", reply_markup=get_admin_keyboard())

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

@dp.callback_query(lambda c: c.data == "admin_active_users")
async def admin_active_users(callback: types.CallbackQuery):
    users = get_active_users()
    if not users:
        text = "Нет активных пользователей."
    else:
        text = "👥 Активные пользователи:\n"
        for u in users:
            name = u['first_name'] or u['username'] or str(u['user_id'])
            end = datetime.fromisoformat(u['subscription_end']).strftime("%d.%m.%Y")
            text += f"- {name} (ID: {u['user_id']}) до {end}\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_payments")
async def admin_payments(callback: types.CallbackQuery):
    payments = get_payment_history()
    if not payments:
        text = "История платежей пуста."
    else:
        text = "💳 История платежей (последние 20):\n"
        for p in payments[-20:]:
            text += f"- Пользователь {p['user_id']}: {p['amount']}₽ за {p['days']} дней ({p['created_at'][:10]})\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_promo_stats")
async def admin_promo_stats(callback: types.CallbackQuery):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT code, bonus_days, used_count, max_uses, expires_at FROM promocodes")
        promos = cur.fetchall()
    if not promos:
        text = "Промокодов нет."
    else:
        text = "🎫 Статистика по промокодам:\n"
        for p in promos:
            text += f"- {p['code']}: бонус {p['bonus_days']} дн, использований {p['used_count']}/{p['max_uses'] if p['max_uses'] else '∞'}, истекает {p['expires_at'][:10] if p['expires_at'] else 'никогда'}\n"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_create_promo")
async def admin_create_promo(callback: types.CallbackQuery):
    code = generate_promo_code()
    create_promo_code(code, bonus_days=7, max_uses=10, expires_days=30)
    await callback.message.edit_text(f"🎫 Создан промокод:\n{code}\nБонус: +7 дней\nДействует 30 дней, 10 использований.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
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

@dp.callback_query(lambda c: c.data == "admin_mailing")
async def admin_mailing_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Введите текст рассылки (можно с Markdown). Для отмены отправьте /cancel")
    await state.set_state(MailingState.waiting_for_text)
    await callback.answer()

@dp.message(MailingState.waiting_for_text)
async def mailing_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text
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
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_load")
async def admin_load(callback: types.CallbackQuery):
    text = "📈 График нагрузки на сервер:\n(заглушка) Активных подключений: 0\nДанные будут доступны после интеграции с API сервера."
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_export")
async def admin_export(callback: types.CallbackQuery):
    csv_data = export_users_to_csv()
    await callback.message.edit_text("📤 Экспорт базы пользователей в CSV:")
    await bot.send_document(callback.from_user.id, types.BufferedInputFile(csv_data.encode('utf-8'), filename='users_export.csv'))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await admin_panel(callback.message)
    await callback.answer()

# ---------- КОМАНДА /language ----------
@dp.message(Command("language"))
async def change_language(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) != 2 or args[1] not in ['ru', 'en']:
        await message.answer("Использование: /language ru или /language en")
        return
    lang = args[1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
    await message.answer(f"Язык изменён на {lang}")

@dp.message(Command("referrals"))
async def cmd_referrals(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)
    referrals = get_referral_list(user_id)
    if not referrals:
        await message.answer(LANGUAGES[lang]['no_referrals'])
        return
    lines = []
    for ref in referrals:
        name = ref['first_name'] or ref['username'] or str(ref['user_id'])
        status = "✅" if ref['is_active'] else "❌"
        lines.append(f"{status} {name} (ID: {ref['user_id']})")
    text = LANGUAGES[lang]['referral_list'].format(list="\n".join(lines))
    await message.answer(text)

# ---------- ФОНОВАЯ ЗАДАЧА НАПОМИНАНИЙ ----------
async def reminder_task():
    while True:
        now = datetime.now()
        three_days_later = now + timedelta(days=3)
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, subscription_end FROM users WHERE is_active = 1")
            users = cur.fetchall()
            for user in users:
                end_date = datetime.fromisoformat(user['subscription_end'])
                if now < end_date <= three_days_later:
                    u = get_user(user['user_id'])
                    lang = u['language'] if u else 'ru'
                    text = LANGUAGES[lang].get('reminder', "⚠️ Ваша подписка истекает через 3 дня.")
                    try:
                        await bot.send_message(user['user_id'], text)
                    except:
                        pass
        await asyncio.sleep(21600)

# ---------- ЗАПУСК ----------
async def main():
    init_db()
    asyncio.create_task(reminder_task())
    print("🤖 Бот Eterny VPN запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())