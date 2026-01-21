import asyncio
import os
import sqlite3
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- SOZLAMALAR ---
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
SUPER_ADMIN = 5767267885
# Render loyiha linkini shu yerga yozasiz (masalan: https://mebel-bot.onrender.com)
WEBHOOK_HOST = "https://mebelbot.onrender.com" 
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('mebel.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, title TEXT, url TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

# --- HOLATLAR ---
class AdminState(StatesGroup):
    waiting_ad = State()
    add_channel_id = State()
    add_channel_url = State()
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()
    add_new_admin = State()

# --- TUGMALAR ---
def main_menu(user_id):
    kb = [[KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")]]
    if user_id == SUPER_ADMIN:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_inline_menu():
    buttons = [
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_query_data="add_chan"),
         InlineKeyboardButton(text="📊 Statistika", callback_query_data="stats")],
        [InlineKeyboardButton(text="📦 Mebel qo'shish", callback_query_data="add_mebel"),
         InlineKeyboardButton(text="✉️ Xabar yuborish", callback_query_data="send_ad")],
        [InlineKeyboardButton(text="👥 Admin qo'shish", callback_query_data="add_adm"),
         InlineKeyboardButton(text="🤖 Bot holati", callback_query_data="status")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- MAJBURIY OBUNA TEKSHIRUV ---
async def check_sub(user_id):
    conn = sqlite3.connect('mebel.db')
    channels = conn.cursor().execute("SELECT id FROM channels").fetchall()
    conn.close()
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except: continue
    return True

# --- HANDLERLAR ---

@dp.message(F.text == "/start")
async def start(message: Message):
    init_db()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()
    
    if not await check_sub(message.from_user.id):
        conn = sqlite3.connect('mebel.db')
        chans = conn.cursor().execute("SELECT url FROM channels").fetchall()
        conn.close()
        btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Obuna bo'lish", url=c[0])] for c in chans])
        btn.inline_keyboard.append([InlineKeyboardButton(text="Tekshirish ✅", callback_query_data="check")])
        return await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=btn)

    await message.answer("Mebel botiga xush kelibsiz!", reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "check")
async def check_callback(call: CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await call.message.answer("Rahmat! Endi botdan foydalanishingiz mumkin.", reply_markup=main_menu(call.from_user.id))
    else:
        await call.answer("Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

@dp.message(F.text == "⚙️ Admin Panel")
async def open_admin(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        await message.answer("🛠 Admin boshqaruv paneli:", reply_markup=admin_inline_menu())

# --- ADMIN: KANAL QO'SHISH ---
@dp.callback_query(F.data == "add_chan")
async def add_chan_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID raqamini yuboring (masalan: -1001234567):")
    await state.set_state(AdminState.add_channel_id)

@dp.message(AdminState.add_channel_id)
async def add_chan_id(message: Message, state: FSMContext):
    await state.update_data(chan_id=message.text)
    await message.answer("Kanal linkini yuboring (https://t.me/...):")
    await state.set_state(AdminState.add_channel_url)

@dp.message(AdminState.add_channel_url)
async def add_chan_final(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT INTO channels VALUES (?, ?, ?)", (data['chan_id'], "Kanal", message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Kanal majburiy obunaga qo'shildi!")
    await state.clear()

# --- WEBHOOK SOZLAMALARI ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL)

def main():
    init_db()
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()