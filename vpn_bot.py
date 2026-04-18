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

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8671810898:AAELwd5oEBhV5PwgSNq8bYaTP7SAX1Mvpdg"
    print("⚠️ BOT_TOKEN взят из кода, лучше через .env")

ADMIN_IDS = [8115647701]  # ваш ID

PRICE_30_DAYS = 159
PRICE_90_DAYS = 419
PRICE_180_DAYS = 799
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
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                discount_type TEXT,
                discount_value INTEGER,
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
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message_text TEXT,
                created_at TEXT,
                sent_count INTEGER DEFAULT 0
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
        ''', (user_id, username, first_name, vpn