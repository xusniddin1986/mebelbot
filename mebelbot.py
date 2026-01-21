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
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- SOZLAMALAR ---
# O'zingizning Telegram ID raqamingizni bu yerga aniq yozing
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
SUPER_ADMIN = 5767267885 
WEBHOOK_HOST = "https://mebelbot.onrender.com"
WEBHOOK_URL = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    conn = sqlite3.connect('mebel.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, url TEXT, title TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)')
    conn.commit()
    conn.close()

class AdminState(StatesGroup):
    waiting_ad = State()
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()
    add_chan_id = State()
    add_chan_url = State()
    add_chan_title = State()

# --- KLAVIATURALAR ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="📍 Manzilimiz"), KeyboardButton(text="ℹ️ Biz haqimizda")]
    ], resize_keyboard=True)

def admin_inline_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
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
            InlineKeyboardButton(text="🗑 Katalog Tozalash", callback_query_data="clear_cat")
        ]
    ])

# --- YORDAMCHI FUNKSIYALAR ---
async def is_subscribed(user_id):
    if user_id == SUPER_ADMIN: return True
    conn = get_db_connection()
    channels = conn.cursor().execute("SELECT id FROM channels").fetchall()
    conn.close()
    
    if not channels: return True 

    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except Exception:
            continue
    return True

# --- HANDLERLAR ---

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear() # Har safar start bosilganda holatni tozalaymiz
    conn = get_db_connection()
    conn.cursor().execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)", 
                          (message.from_user.id, message.from_user.username, message.from_user.full_name))
    conn.commit()
    conn.close()

    if await is_subscribed(message.from_user.id):
        await message.answer("Xush kelibsiz! Tanlang:", reply_markup=main_menu())
    else:
        conn = get_db_connection()
        chans = conn.cursor().execute("SELECT id, url, title FROM channels").fetchall()
        conn.close()
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['title'], url=c['url'])] for c in chans])
        markup.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_query_data="check_sub")])
        await message.answer("Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=markup)

@dp.callback_query(F.data == "check_sub")
async def sub_checker(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi!", reply_markup=main_menu())
    else:
        await call.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)

# --- ADMIN PANEL (MUHIM) ---
@dp.message(F.text == "/admin")
async def admin_panel(message: Message, state: FSMContext):
    # Bu yerda foydalanuvchi ID sini logda ko'rsatadi, agar kirmasa logni tekshiring
    logging.info(f"Admin panelga urinish: {message.from_user.id}")
    if int(message.from_user.id) == int(SUPER_ADMIN):
        await state.clear()
        await message.answer("🛠 Admin boshqaruv markazi:", reply_markup=admin_inline_menu())
    else:
        await message.answer(f"Siz admin emassiz. Sizning ID: {message.from_user.id}")

@dp.callback_query(F.data == "stats")
async def stats_call(call: CallbackQuery):
    conn = get_db_connection()
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
    await message.answer("ℹ️ Ma'lumot va narx?")
    await state.set_state(AdminState.add_mebel_info)

@dp.message(AdminState.add_mebel_info)
async def mebel_add_step3(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("🖼 Rasm yuboring:")
    await state.set_state(AdminState.add_mebel_photo)

@dp.message(AdminState.add_mebel_photo)
async def mebel_add_final(message: Message, state: FSMContext):
    if not message.photo: return await message.answer("Rasm yuboring!")
    data = await state.get_data()
    conn = get_db_connection()
    conn.cursor().execute("INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)", 
                          (data['cat'], data['info'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Katalogga qo'shildi!")
    await state.clear()

@dp.callback_query(F.data == "add_chan")
async def add_chan_s1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📢 Kanal ID sini yuboring (Masalan: -100...):")
    await state.set_state(AdminState.add_chan_id)
    await call.answer()

@dp.message(AdminState.add_chan_id)
async def add_chan_s2(message: Message, state: FSMContext):
    await state.update_data(cid=message.text)
    await message.answer("🔗 Link?")
    await state.set_state(AdminState.add_chan_url)

@dp.message(AdminState.add_chan_url)
async def add_chan_s3(message: Message, state: FSMContext):
    await state.update_data(curl=message.text)
    await message.answer("📝 Nomi?")
    await state.set_state(AdminState.add_chan_title)

@dp.message(AdminState.add_chan_title)
async def add_chan_final(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = get_db_connection()
    conn.cursor().execute("INSERT INTO channels (id, url, title) VALUES (?, ?, ?)", 
                          (data['cid'], data['curl'], message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Kanal qo'shildi!")
    await state.clear()

@dp.message(F.text == "🪑 Katalog")
async def catalog_show(message: Message):
    conn = get_db_connection()
    items = conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    conn.close()
    if not items: return await message.answer("Katalog bo'sh.")
    
    for item in items[:10]:
        await message.answer_photo(photo=item['photo'], caption=f"📁 {item['cat']}\nℹ️ {item['info']}")

@dp.callback_query(F.data == "send_ad")
async def ad_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✉️ Reklamani yuboring:")
    await state.set_state(AdminState.waiting_ad)
    await call.answer()

@dp.message(AdminState.waiting_ad)
async def ad_final(message: Message, state: FSMContext):
    conn = get_db_connection()
    users = conn.cursor().execute("SELECT id FROM users").fetchall()
    conn.close()
    count = 0
    for user in users:
        try:
            await message.copy_to(chat_id=user['id'])
            count += 1
            await asyncio.sleep(0.05)
        except Exception: continue
    await message.answer(f"✅ {count} kishiga yuborildi.")
    await state.clear()

@dp.callback_query(F.data == "del_chan")
async def del_chan(call: CallbackQuery):
    conn = get_db_connection(); conn.execute("DELETE FROM channels"); conn.commit(); conn.close()
    await call.message.answer("❌ Kanallar o'chirildi."); await call.answer()

@dp.callback_query(F.data == "clear_cat")
async def clear_cat(call: CallbackQuery):
    conn = get_db_connection(); conn.execute("DELETE FROM furniture"); conn.commit(); conn.close()
    await call.message.answer("🗑 Katalog tozalandi."); await call.answer()

@dp.message(F.text == "📞 Aloqa")
async def contact(message: Message):
    await message.answer("📞 Admin: @AdminUser")

@dp.message(F.text == "📍 Manzilimiz")
async def loc(message: Message):
    await message.answer("📍 Toshkent shahri.")

@dp.message(F.text == "ℹ️ Biz haqimizda")
async def about(message: Message):
    await message.answer("Mebel do'koni boti.")

async def on_startup(bot: Bot):
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=f"/webhook/{BOT_TOKEN}")
    setup_application(app, dp, bot=bot)
    app.on_startup.append(lambda _: on_startup(bot))
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    main()