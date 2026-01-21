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
from aiogram.exceptions import TelegramBadRequest

# --- SOZLAMALAR ---
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
SUPER_ADMIN = 5767267885
WEBHOOK_HOST = "https://mebelbot.onrender.com"
WEBHOOK_URL = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA ---
def init_db():
    conn = sqlite3.connect('mebel.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, url TEXT, title TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)')
    conn.commit()
    conn.close()

class AdminState(StatesGroup):
    waiting_ad = State()
    add_chan_id = State()
    add_chan_url = State()
    add_chan_title = State()
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()

# --- TUGMALAR (DIQQAT: Inline menyuda faqat InlineKeyboardButton bo'lishi shart!) ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="📍 Manzilimiz"), KeyboardButton(text="ℹ️ Biz haqimizda")]
    ], resize_keyboard=True)

def admin_inline_menu():
    # Bu yerda FAQAT InlineKeyboardButton ishlatilganiga ishonch hosil qilamiz
    kb = [
        [
            InlineKeyboardButton(text="📊 Statistika", callback_query_data="stats"),
            InlineKeyboardButton(text="✉️ Reklama", callback_query_data="send_ad")
        ],
        [
            InlineKeyboardButton(text="📢 Kanal +", callback_query_data="add_chan"),
            InlineKeyboardButton(text="❌ Kanal -", callback_query_data="del_chan")
        ],
        [
            InlineKeyboardButton(text="📦 Mebel +", callback_query_data="add_mebel"),
            InlineKeyboardButton(text="🗑 Tozalash", callback_query_data="clear_cat")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- MAJBURIY OBUNA ---
async def is_subscribed(user_id):
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
async def start_cmd(message: Message):
    init_db()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)", 
                         (message.from_user.id, message.from_user.username, message.from_user.full_name))
    conn.commit()
    conn.close()

    if not await is_subscribed(message.from_user.id):
        conn = sqlite3.connect('mebel.db')
        chans = conn.cursor().execute("SELECT id, url, title FROM channels").fetchall()
        conn.close()
        if chans:
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c[2], url=c[1])] for c in chans])
            markup.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_query_data="check_sub")])
            return await message.answer("Avval kanallarga a'zo bo'ling:", reply_markup=markup)

    await message.answer("Xush kelibsiz!", reply_markup=main_menu())

@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        # Xatoni oldini olish uchun klaviaturani tekshirib chiqamiz
        await message.answer("🛠 Admin boshqaruv markazi:", reply_markup=admin_inline_menu())
    else:
        await message.answer(f"Siz admin emassiz! ID: {message.from_user.id}")

@dp.callback_query(F.data == "stats")
async def stats_call(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db')
    u_count = conn.cursor().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    m_count = conn.cursor().execute("SELECT COUNT(*) FROM furniture").fetchone()[0]
    conn.close()
    await call.message.answer(f"📊 Statistika:\n👤 Userlar: {u_count}\n📦 Mebellar: {m_count}")
    await call.answer()

@dp.callback_query(F.data == "add_mebel")
async def mebel_add_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📦 Kategoriya nomi?")
    await state.set_state(AdminState.add_mebel_cat)
    await call.answer()

@dp.message(AdminState.add_mebel_cat)
async def mebel_add_step2(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("ℹ️ Ma'lumot?")
    await state.set_state(AdminState.add_mebel_info)

@dp.message(AdminState.add_mebel_info)
async def mebel_add_step3(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("🖼 Rasm yuboring:")
    await state.set_state(AdminState.add_mebel_photo)

@dp.message(AdminState.add_mebel_photo)
async def mebel_add_final(message: Message, state: FSMContext):
    if not message.photo: return await message.answer("Faqat rasm yuboring!")
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)", 
                         (data['cat'], data['info'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Katalogga qo'shildi!", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🪑 Katalog")
async def catalog_show(message: Message):
    conn = sqlite3.connect('mebel.db')
    items = conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    conn.close()
    if not items: return await message.answer("Hozircha bo'sh.")
    for item in items:
        await message.answer_photo(photo=item[2], caption=f"📁 {item[0]}\n\nℹ️ {item[1]}")

@dp.callback_query(F.data == "send_ad")
async def ad_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✉️ Reklamani yuboring (Rasm, tekst, video):")
    await state.set_state(AdminState.waiting_ad)
    await call.answer()

@dp.message(AdminState.waiting_ad)
async def ad_final(message: Message, state: FSMContext):
    conn = sqlite3.connect('mebel.db')
    users = conn.cursor().execute("SELECT id FROM users").fetchall()
    conn.close()
    count = 0
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ {count} kishiga yuborildi.")
    await state.clear()

# --- QOLGAN FUNKSIYALAR ---
@dp.callback_query(F.data == "del_chan")
async def del_chan(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db'); conn.execute("DELETE FROM channels"); conn.commit(); conn.close()
    await call.message.answer("❌ Kanallar o'chirildi."); await call.answer()

@dp.callback_query(F.data == "clear_cat")
async def clear_cat(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db'); conn.execute("DELETE FROM furniture"); conn.commit(); conn.close()
    await call.message.answer("🗑 Katalog tozalandi."); await call.answer()

@dp.message(F.text == "📞 Aloqa")
async def contact(message: Message):
    await message.answer("📞 Admin: @mebel_admin")

@dp.message(F.text == "📍 Manzilimiz")
async def loc(message: Message):
    await message.answer("📍 Toshkent shahri.")

async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

def main():
    init_db()
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=f"/webhook/{BOT_TOKEN}")
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()