import asyncio
import os
import sqlite3
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ================== SOZLAMALAR ==================
BOT_TOKEN = os.getenv("8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE")  # ❗ token ENV da bo‘lishi shart
SUPER_ADMIN = 5767267885

WEBHOOK_HOST = "https://mebelbot.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================== DATABASE ==================
def get_db():
    conn = sqlite3.connect("mebel.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY,
            url TEXT,
            title TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS furniture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat TEXT,
            info TEXT,
            photo TEXT
        )
    """)

    conn.commit()
    conn.close()

# ================== STATES ==================
class AdminState(StatesGroup):
    waiting_ad = State()
    add_cat = State()
    add_info = State()
    add_photo = State()
    chan_id = State()
    chan_url = State()
    chan_title = State()

# ================== KEYBOARDS ==================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
            [KeyboardButton(text="📍 Manzilimiz"), KeyboardButton(text="ℹ️ Biz haqimizda")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="stats"),
            InlineKeyboardButton(text="✉️ Reklama", callback_data="send_ad")
        ],
        [
            InlineKeyboardButton(text="📢 Kanal +", callback_data="add_chan"),
            InlineKeyboardButton(text="❌ Kanal -", callback_data="del_chan")
        ],
        [
            InlineKeyboardButton(text="📦 Mebel +", callback_data="add_mebel"),
            InlineKeyboardButton(text="🗑 Katalog Tozalash", callback_data="clear_cat")
        ]
    ])

# ================== YORDAMCHI ==================
async def is_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN

async def is_subscribed(user_id: int) -> bool:
    if await is_admin(user_id):
        return True

    conn = get_db()
    chans = conn.execute("SELECT id FROM channels").fetchall()
    conn.close()

    if not chans:
        return True

    for ch in chans:
        try:
            member = await bot.get_chat_member(int(ch["id"]), user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            continue

    return True

# ================== START ==================
@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()

    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.username, message.from_user.full_name)
    )
    conn.commit()
    conn.close()

    if await is_subscribed(message.from_user.id):
        await message.answer("Xush kelibsiz!", reply_markup=main_menu())
    else:
        conn = get_db()
        chans = conn.execute("SELECT * FROM channels").fetchall()
        conn.close()

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=c["title"], url=c["url"])] for c in chans
            ] + [[InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]]
        )

        await message.answer("Kanallarga a'zo bo‘ling:", reply_markup=kb)

@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi", reply_markup=main_menu())
    else:
        await call.answer("❌ Obuna yo‘q", show_alert=True)

# ================== ADMIN PANEL ==================
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    logging.info(f"/admin urinish: {message.from_user.id}")

    if not await is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz")

    await state.clear()
    await message.answer("🛠 Admin panel:", reply_markup=admin_menu())

# ================== ADMIN CALLBACK PROTECT ==================
async def admin_only(call: CallbackQuery) -> bool:
    if call.from_user.id != SUPER_ADMIN:
        await call.answer("❌ Ruxsat yo‘q", show_alert=True)
        return False
    return True

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if not await admin_only(call): return

    conn = get_db()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    mebel = conn.execute("SELECT COUNT(*) FROM furniture").fetchone()[0]
    conn.close()

    await call.message.answer(f"👤 Userlar: {users}\n📦 Mebel: {mebel}")
    await call.answer()

# ================== MEBEL QO‘SHISH ==================
@dp.callback_query(F.data == "add_mebel")
async def add_mebel(call: CallbackQuery, state: FSMContext):
    if not await admin_only(call): return
    await call.message.answer("Kategoriya nomi:")
    await state.set_state(AdminState.add_cat)
    await call.answer()

@dp.message(AdminState.add_cat)
async def mebel_cat(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("Ma'lumot va narx:")
    await state.set_state(AdminState.add_info)

@dp.message(AdminState.add_info)
async def mebel_info(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("Rasm yuboring:")
    await state.set_state(AdminState.add_photo)

@dp.message(AdminState.add_photo)
async def mebel_photo(message: Message, state: FSMContext):
    if not message.photo:
        return await message.answer("❌ Rasm yuboring")

    data = await state.get_data()

    conn = get_db()
    conn.execute(
        "INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)",
        (data["cat"], data["info"], message.photo[-1].file_id)
    )
    conn.commit()
    conn.close()

    await message.answer("✅ Qo‘shildi")
    await state.clear()

# ================== USER MENULAR ==================
@dp.message(F.text == "🪑 Katalog")
async def katalog(message: Message):
    conn = get_db()
    items = conn.execute("SELECT * FROM furniture").fetchall()
    conn.close()

    if not items:
        return await message.answer("Katalog bo‘sh")

    for i in items[:10]:
        await message.answer_photo(
            photo=i["photo"],
            caption=f"📁 {i['cat']}\nℹ️ {i['info']}"
        )

@dp.message(F.text == "📞 Aloqa")
async def aloqa(message: Message):
    await message.answer("📞 Admin: @AdminUser")

@dp.message(F.text == "📍 Manzilimiz")
async def manzil(message: Message):
    await message.answer("📍 Toshkent shahri")

@dp.message(F.text == "ℹ️ Biz haqimizda")
async def about(message: Message):
    await message.answer("Mebel do‘koni rasmiy boti")

# ================== STARTUP ==================
async def on_startup(bot: Bot):
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

def main():
    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    async def startup(app):
        await on_startup(bot)

    app.on_startup.append(startup)

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
