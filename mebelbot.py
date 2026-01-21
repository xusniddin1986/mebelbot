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

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('mebel.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, url TEXT, title TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS furniture (id INTEGER PRIMARY KEY AUTOINCREMENT, cat TEXT, info TEXT, photo TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

class AdminState(StatesGroup):
    # Reklama uchun
    waiting_ad = State()
    # Kanallar uchun
    add_chan_id = State()
    add_chan_url = State()
    add_chan_title = State()
    # Mebel uchun
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()

# --- TUGMALAR ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🪑 Katalog"), KeyboardButton(text="📞 Aloqa")],
        [KeyboardButton(text="📍 Manzilimiz"), KeyboardButton(text="ℹ️ Biz haqimizda")]
    ], resize_keyboard=True)

def admin_inline_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_query_data="stats"),
         InlineKeyboardButton(text="✉️ Reklama tarqatish", callback_query_data="send_ad")],
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_query_data="add_chan"),
         InlineKeyboardButton(text="❌ Kanalni o'chirish", callback_query_data="del_chan")],
        [InlineKeyboardButton(text="📦 Mebel qo'shish", callback_query_data="add_mebel"),
         InlineKeyboardButton(text="🗑 Katalogni tozalash", callback_query_data="clear_cat")]
    ])

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def is_subscribed(user_id):
    conn = sqlite3.connect('mebel.db')
    channels = conn.cursor().execute("SELECT id FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            continue
    return True

# --- ASOSIY HANDLERLAR ---
@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    init_db()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", 
                         (message.from_user.id, message.from_user.username, message.from_user.full_name))
    conn.commit()
    conn.close()

    if not await is_subscribed(message.from_user.id):
        conn = sqlite3.connect('mebel.db')
        chans = conn.cursor().execute("SELECT id, url, title FROM channels").fetchall()
        conn.close()
        
        if chans:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=c[2], url=c[1])] for c in chans
            ])
            markup.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_query_data="check_sub")])
            return await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=markup)

    await message.answer("Mebel botiga xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu())

@dp.callback_query(F.data == "check_sub")
async def check_callback(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("Obuna tasdiqlandi! Marhamat:", reply_markup=main_menu())
    else:
        await call.answer("Hamma kanallarga obuna bo'lmagansiz!", show_alert=True)

# --- ADMIN PANEL ---
@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        await message.answer("🛠 Admin boshqaruv markazi:", reply_markup=admin_inline_menu())

# --- ADMIN: STATISTIKA ---
@dp.callback_query(F.data == "stats")
async def stats_call(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db')
    u_count = conn.cursor().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    m_count = conn.cursor().execute("SELECT COUNT(*) FROM furniture").fetchone()[0]
    conn.close()
    await call.message.answer(f"📊 **Statistika:**\n\n👤 Foydalanuvchilar: {u_count}\n📦 Katalogdagi mahsulotlar: {m_count}")
    await call.answer()

# --- ADMIN: MEBEL QO'SHISH ---
@dp.callback_query(F.data == "add_mebel")
async def mebel_add_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📦 Mebel kategoriyasini kiriting (masalan: Oshxona):")
    await state.set_state(AdminState.add_mebel_cat)
    await call.answer()

@dp.message(AdminState.add_mebel_cat)
async def mebel_add_step2(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("ℹ️ Mebel haqida ma'lumot (narxi, materiali):")
    await state.set_state(AdminState.add_mebel_info)

@dp.message(AdminState.add_mebel_info)
async def mebel_add_step3(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("🖼 Mebel rasmini yuboring:")
    await state.set_state(AdminState.add_mebel_photo)

@dp.message(AdminState.add_mebel_photo)
async def mebel_add_final(message: Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Iltimos, rasm yuboring!")
    
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)", 
                         (data['cat'], data['info'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Mahsulot katalogga qo'shildi!", reply_markup=main_menu())
    await state.clear()

# --- FOYDALANUVCHI: KATALOG ---
@dp.message(F.text == "🪑 Katalog")
async def catalog_show(message: Message):
    conn = sqlite3.connect('mebel.db')
    items = conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    conn.close()
    
    if not items:
        return await message.answer("Hozircha katalog bo'sh.")
    
    for item in items:
        await message.answer_photo(photo=item[2], caption=f"📁 **Kategoriya:** {item[0]}\n\nℹ️ **Ma'lumot:** {item[1]}")

# --- ADMIN: KANAL QO'SHISH ---
@dp.callback_query(F.data == "add_chan")
async def chan_add_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📢 Kanal ID sini kiriting (masalan: -10012345678):")
    await state.set_state(AdminState.add_chan_id)
    await call.answer()

@dp.message(AdminState.add_chan_id)
async def chan_add_step2(message: Message, state: FSMContext):
    await state.update_data(id=message.text)
    await message.answer("🔗 Kanal linkini kiriting (masalan: https://t.me/...):")
    await state.set_state(AdminState.add_chan_url)

@dp.message(AdminState.add_chan_url)
async def chan_add_step3(message: Message, state: FSMContext):
    await state.update_data(url=message.text)
    await message.answer("📝 Kanal nomini kiriting:")
    await state.set_state(AdminState.add_chan_title)

@dp.message(AdminState.add_chan_title)
async def chan_add_final(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    conn.cursor().execute("INSERT INTO channels VALUES (?, ?, ?)", (data['id'], data['url'], message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Kanal majburiy obuna ro'yxatiga qo'shildi!")
    await state.clear()

# --- ADMIN: REKLAMA ---
@dp.callback_query(F.data == "send_ad")
async def ad_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✉️ Reklama xabarini yuboring (Rasm, video yoki matn):")
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
        except Exception:
            continue
    
    await message.answer(f"✅ Reklama {count} ta foydalanuvchiga yetkazildi.")
    await state.clear()

# --- BOSHQALAR ---
@dp.message(F.text == "📞 Aloqa")
async def contact(message: Message):
    await message.answer("📞 Biz bilan bog'lanish:\n\nAdmin: @mebel_admin\nTelefon: +998 90 123 45 67")

@dp.message(F.text == "📍 Manzilimiz")
async def loc_cmd(message: Message):
    await message.answer("📍 Toshkent shahri, Chilonzor tumani, 5-mavze.\nMo'ljal: Korzinka yaqinida.")

# --- WEBHOOK & STARTUP ---
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