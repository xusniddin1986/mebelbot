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
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
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


# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect("mebel.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, title TEXT, url TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)"
    )
    cur.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


class AdminState(StatesGroup):
    waiting_ad = State()
    add_channel_id = State()
    add_channel_url = State()
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()


# --- TUGMALAR ---
def main_menu():
    kb = [
        [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="📍 Manzilimiz")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def admin_inline_menu():
    buttons = [
        [
            InlineKeyboardButton(
                text="📢 Kanal qo'shish", callback_query_data="add_chan"
            ),
            InlineKeyboardButton(text="📊 Statistika", callback_query_data="stats"),
        ],
        [
            InlineKeyboardButton(
                text="📦 Mebel qo'shish", callback_query_data="add_mebel"
            ),
            InlineKeyboardButton(
                text="✉️ Xabar yuborish", callback_query_data="send_ad"
            ),
        ],
        [InlineKeyboardButton(text="🤖 Bot holati", callback_query_data="status")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- MAJBURIY OBUNA ---
async def check_sub(user_id):
    conn = sqlite3.connect("mebel.db")
    channels = conn.cursor().execute("SELECT id FROM channels").fetchall()
    conn.close()
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            continue
    return True


# --- HANDLERLAR ---


@dp.message(F.text == "/start")
async def start(message: Message):
    init_db()
    conn = sqlite3.connect("mebel.db")
    conn.cursor().execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?)",
        (message.from_user.id, message.from_user.username),
    )
    conn.commit()
    conn.close()

    if not await check_sub(message.from_user.id):
        conn = sqlite3.connect("mebel.db")
        chans = conn.cursor().execute("SELECT url FROM channels").fetchall()
        conn.close()
        btn = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Obuna bo'lish", url=c[0])] for c in chans
            ]
        )
        btn.inline_keyboard.append(
            [InlineKeyboardButton(text="Tekshirish ✅", callback_query_data="check")]
        )
        return await message.answer(
            "Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=btn
        )

    await message.answer("Mebel botiga xush kelibsiz!", reply_markup=main_menu())


@dp.message(F.text == "/admin")
async def admin_cmd(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        await message.answer(
            "🛠 Admin boshqaruv paneli:", reply_markup=admin_inline_menu()
        )
    else:
        # Agar ID xato bo'lsa, bot senga IDingni aytadi
        await message.answer(f"Siz admin emassiz! Sizning ID: {message.from_user.id}")


# --- FOYDALANUVCHI TUGMALARI UCHUN JAVOBLAR ---
@dp.message(F.text == "🪑 Katalog")
async def show_catalog(message: Message):
    conn = sqlite3.connect("mebel.db")
    furniture = (
        conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    )
    conn.close()

    if not furniture:
        await message.answer("Hozircha katalog bo'sh.")
    else:
        for f in furniture:
            await message.answer_photo(
                photo=f[2], caption=f"📁 Kategoriya: {f[0]}\nℹ️ Ma'lumot: {f[1]}"
            )


@dp.message(F.text == "📞 Aloqa")
async def contact_us(message: Message):
    await message.answer(
        "📞 Biz bilan bog'lanish:\nTel: +998 90 123 45 67\nTelegram: @admin_username"
    )


@dp.message(F.text == "📍 Manzilimiz")
async def location(message: Message):
    await message.answer("📍 Manzil: Toshkent sh., Chilonzor tumani, 5-mavze.")


# --- ADMIN FUNKSIYALARI ---
@dp.callback_query(F.data == "stats")
async def stats_callback(call: CallbackQuery):
    conn = sqlite3.connect("mebel.db")
    users_count = conn.cursor().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    await call.message.answer(
        f"📊 Statistika:\nJami foydalanuvchilar: {users_count} ta"
    )
    await call.answer()


@dp.callback_query(F.data == "add_mebel")
async def add_mebel_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Mebel kategoriyasini yozing:")
    await state.set_state(AdminState.add_mebel_cat)
    await call.answer()


@dp.message(AdminState.add_mebel_cat)
async def add_mebel_cat(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("Mebel haqida batafsil ma'lumot yozing:")
    await state.set_state(AdminState.add_mebel_info)


@dp.message(AdminState.add_mebel_info)
async def add_mebel_info(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("Mebel rasmini yuboring:")
    await state.set_state(AdminState.add_mebel_photo)


@dp.message(AdminState.add_mebel_photo)
async def add_mebel_final(message: Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Iltimos, rasm yuboring!")
    data = await state.get_data()
    conn = sqlite3.connect("mebel.db")
    conn.cursor().execute(
        "INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)",
        (data["cat"], data["info"], message.photo[-1].file_id),
    )
    conn.commit()
    conn.close()
    await message.answer("✅ Mebel muvaffaqiyatli qo'shildi!", reply_markup=main_menu())
    await state.clear()


# --- WEBHOOK QISMI ---
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
