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
WEBHOOK_HOST = "https://mebelbot.onrender.com" 
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA ---
def init_db():
    conn = sqlite3.connect('mebel.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, url TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)')
    conn.commit()
    conn.close()

class AdminState(StatesGroup):
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()

# --- TUGMALAR (Xatolar tuzatildi) ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="📍 Manzilimiz")]
    ], resize_keyboard=True)

def admin_inline_menu():
    # FAQAT InlineKeyboardButton ishlatilishi shart!
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_query_data="add_chan"),
         InlineKeyboardButton(text="📊 Statistika", callback_query_data="stats")],
        [InlineKeyboardButton(text="📦 Mebel qo'shish", callback_query_data="add_mebel"),
         InlineKeyboardButton(text="✉️ Xabar yuborish", callback_query_data="send_ad")]
    ])

# --- HANDLERLAR ---
@dp.message(F.text == "/start")
async def start(message: Message):
    init_db()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    conn.commit()
    conn.close()
    await message.answer("Xush kelibsiz! Menyu tugmalaridan foydalaning.", reply_markup=main_menu())

@dp.message(F.text == "/admin")
async def admin_cmd(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        await message.answer("🛠 Admin panel:", reply_markup=admin_inline_menu())
    else:
        await message.answer(f"Siz admin emassiz. ID: {message.from_user.id}")

@dp.message(F.text == "🪑 Katalog")
async def show_catalog(message: Message):
    conn = sqlite3.connect('mebel.db')
    furniture = conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    conn.close()
    if not furniture:
        return await message.answer("Hozircha katalog bo'sh.")
    for f in furniture:
        await message.answer_photo(photo=f[2], caption=f"📁 Kategoriya: {f[0]}\nℹ️ Ma'lumot: {f[1]}")

@dp.callback_query(F.data == "add_mebel")
async def add_mebel_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kategoriya yozing:")
    await state.set_state(AdminState.add_mebel_cat)
    await call.answer()

@dp.message(AdminState.add_mebel_cat)
async def add_mebel_cat(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("Mebel haqida ma'lumot:")
    await state.set_state(AdminState.add_mebel_info)

@dp.message(AdminState.add_mebel_info)
async def add_mebel_info(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("Rasm yuboring:")
    await state.set_state(AdminState.add_mebel_photo)

@dp.message(AdminState.add_mebel_photo)
async def add_mebel_final(message: Message, state: FSMContext):
    if not message.photo: return await message.answer("Rasm yuboring!")
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)", 
                         (data['cat'], data['info'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Mebel qo'shildi!", reply_markup=main_menu())
    await state.clear()

# --- WEBHOOK ---
async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

def main():
    init_db()
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()