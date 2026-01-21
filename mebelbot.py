import os
import sqlite3
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ===================== SOZLAMALAR =====================
BOT_TOKEN = os.getenv("8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE")
SUPER_ADMIN = 5767267885

WEBHOOK_HOST = "https://mebelbot.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ===================== DATABASE =====================
def db():
    conn = sqlite3.connect("db.sqlite")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            fullname TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            photo TEXT
        )
    """)

    con.commit()
    con.close()

# ===================== STATES =====================
class AddItem(StatesGroup):
    title = State()
    description = State()
    photo = State()

# ===================== KEYBOARDS =====================
def user_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🪑 Katalog")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="ℹ️ Biz haqimizda")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="➕ Mebel qo‘shish", callback_data="add_item")],
        [InlineKeyboardButton(text="🗑 Katalogni tozalash", callback_data="clear")]
    ])

# ===================== START =====================
@dp.message(Command("start"))
async def start(message: Message):
    con = db()
    con.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.username, message.from_user.full_name)
    )
    con.commit()
    con.close()

    await message.answer("Xush kelibsiz 👋", reply_markup=user_menu())

# ===================== ADMIN =====================
@dp.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN:
        return await message.answer("❌ Siz admin emassiz")

    await state.clear()
    await message.answer("🛠 Admin panel", reply_markup=admin_menu())

# ===================== ADMIN CALLBACKS =====================
async def admin_only(call: CallbackQuery):
    if call.from_user.id != SUPER_ADMIN:
        await call.answer("❌ Ruxsat yo‘q", show_alert=True)
        return False
    return True

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if not await admin_only(call): return

    con = db()
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    items = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    con.close()

    await call.message.answer(f"👤 Userlar: {users}\n📦 Mebellar: {items}")
    await call.answer()

@dp.callback_query(F.data == "add_item")
async def add_item(call: CallbackQuery, state: FSMContext):
    if not await admin_only(call): return
    await call.message.answer("Mebel nomini yozing:")
    await state.set_state(AddItem.title)
    await call.answer()

@dp.message(AddItem.title)
async def item_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Tavsifini yozing:")
    await state.set_state(AddItem.description)

@dp.message(AddItem.description)
async def item_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Rasm yuboring:")
    await state.set_state(AddItem.photo)

@dp.message(AddItem.photo)
async def item_photo(message: Message, state: FSMContext):
    if not message.photo:
        return await message.answer("❌ Rasm yuboring")

    data = await state.get_data()

    con = db()
    con.execute(
        "INSERT INTO items (title, description, photo) VALUES (?, ?, ?)",
        (data["title"], data["description"], message.photo[-1].file_id)
    )
    con.commit()
    con.close()

    await message.answer("✅ Mebel qo‘shildi")
    await state.clear()

@dp.callback_query(F.data == "clear")
async def clear(call: CallbackQuery):
    if not await admin_only(call): return
    con = db()
    con.execute("DELETE FROM items")
    con.commit()
    con.close()
    await call.message.answer("🗑 Katalog tozalandi")
    await call.answer()

# ===================== USER =====================
@dp.message(F.text == "🪑 Katalog")
async def katalog(message: Message):
    con = db()
    items = con.execute("SELECT * FROM items").fetchall()
    con.close()

    if not items:
        return await message.answer("Katalog bo‘sh")

    for i in items:
        await message.answer_photo(
            photo=i["photo"],
            caption=f"📦 {i['title']}\n{i['description']}"
        )

@dp.message(F.text == "📞 Aloqa")
async def aloqa(message: Message):
    await message.answer("📞 Admin: @AdminUser")

@dp.message(F.text == "ℹ️ Biz haqimizda")
async def about(message: Message):
    await message.answer("Biz mebel sotuvchi do‘konmiz")

# ===================== STARTUP =====================
async def on_startup(bot: Bot):
    init_db()
    await bot.set_webhook(WEBHOOK_URL)

def main():
    app = web.Application()

    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.on_startup.append(lambda _: on_startup(bot))

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
