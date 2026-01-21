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
# DIQQAT: Tokeningizni xavfsiz joyda saqlashni unutmang!
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
SUPER_ADMIN = 5767267885
WEBHOOK_HOST = "https://mebelbot.onrender.com"
WEBHOOK_URL = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return sqlite3.connect('mebel.db')

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
    # Mebel qo'shish
    add_mebel_cat = State()
    add_mebel_info = State()
    add_mebel_photo = State()
    # Kanal qo'shish
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
    conn = get_db_connection()
    channels = conn.cursor().execute("SELECT id FROM channels").fetchall()
    conn.close()
    
    if not channels: return True # Agar kanallar bo'lmasa, o'tkazib yuboramiz

    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[0], user_id=user_id)
            if member.status in ['left', 'kicked']: return False
        except Exception as e:
            logging.error(f"Kanal tekshirishda xatolik: {e}")
            continue
    return True

async def check_sub_logic(message: Message):
    conn = get_db_connection()
    chans = conn.cursor().execute("SELECT id, url, title FROM channels").fetchall()
    conn.close()
    
    if chans:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=c[2], url=c[1])] for c in chans
        ])
        markup.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_query_data="check_sub")])
        await message.answer("Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=markup)
        return False
    return True

# --- HANDLERLAR ---

@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    conn = get_db_connection()
    conn.cursor().execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?, ?, ?)", 
                          (message.from_user.id, message.from_user.username, message.from_user.full_name))
    conn.commit()
    conn.close()

    if await is_subscribed(message.from_user.id):
        await message.answer("Xush kelibsiz! Bizning mebel do'konimizga marhabo.", reply_markup=main_menu())
    else:
        await check_sub_logic(message)

# ✅ OBUNA TEKSHIRISH TUGMASI UCHUN HANDLER
@dp.callback_query(F.data == "check_sub")
async def sub_checker(call: CallbackQuery):
    await call.answer()
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi! Xizmatlardan foydalanishingiz mumkin.", reply_markup=main_menu())
    else:
        await call.message.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- ADMIN PANEL ---
@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if message.from_user.id == SUPER_ADMIN:
        await message.answer("🛠 Admin boshqaruv markazi:", reply_markup=admin_inline_menu())
    else:
        await message.answer("Siz admin emassiz.")

@dp.callback_query(F.data == "stats")
async def stats_call(call: CallbackQuery):
    conn = get_db_connection()
    u_count = conn.cursor().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    m_count = conn.cursor().execute("SELECT COUNT(*) FROM furniture").fetchone()[0]
    conn.close()
    await call.message.answer(f"📊 Statistika:\n👤 Userlar: {u_count}\n📦 Mebellar: {m_count}")
    await call.answer()

# --- MEBEL QO'SHISH ---
@dp.callback_query(F.data == "add_mebel")
async def mebel_add_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📦 Kategoriya nomi? (Masalan: Divanlar)")
    await state.set_state(AdminState.add_mebel_cat)
    await call.answer()

@dp.message(AdminState.add_mebel_cat)
async def mebel_add_step2(message: Message, state: FSMContext):
    await state.update_data(cat=message.text)
    await message.answer("ℹ️ Mebel haqida ma'lumot va narxini yozing:")
    await state.set_state(AdminState.add_mebel_info)

@dp.message(AdminState.add_mebel_info)
async def mebel_add_step3(message: Message, state: FSMContext):
    await state.update_data(info=message.text)
    await message.answer("🖼 Mebel rasmini yuboring:")
    await state.set_state(AdminState.add_mebel_photo)

@dp.message(AdminState.add_mebel_photo)
async def mebel_add_final(message: Message, state: FSMContext):
    if not message.photo: return await message.answer("Iltimos, rasm yuboring!")
    
    data = await state.get_data()
    conn = get_db_connection()
    conn.cursor().execute("INSERT INTO furniture (cat, info, photo) VALUES (?, ?, ?)", 
                          (data['cat'], data['info'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Mebel katalogga qo'shildi!", reply_markup=main_menu())
    await state.clear()

# --- KANAL QO'SHISH (YANGI) ---
@dp.callback_query(F.data == "add_chan")
async def add_chan_s1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📢 Kanal ID sini yuboring (Masalan: -100123456789):")
    await state.set_state(AdminState.add_chan_id)
    await call.answer()

@dp.message(AdminState.add_chan_id)
async def add_chan_s2(message: Message, state: FSMContext):
    await state.update_data(cid=message.text)
    await message.answer("🔗 Kanal linkini yuboring (https://t.me/...):")
    await state.set_state(AdminState.add_chan_url)

@dp.message(AdminState.add_chan_url)
async def add_chan_s3(message: Message, state: FSMContext):
    await state.update_data(curl=message.text)
    await message.answer("📝 Kanal nomini yozing (Tugmada ko'rinadi):")
    await state.set_state(AdminState.add_chan_title)

@dp.message(AdminState.add_chan_title)
async def add_chan_final(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = get_db_connection()
    try:
        conn.cursor().execute("INSERT INTO channels (id, url, title) VALUES (?, ?, ?)", 
                             (data['cid'], data['curl'], message.text))
        conn.commit()
        await message.answer("✅ Kanal majburiy obunaga qo'shildi!")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")
    finally:
        conn.close()
        await state.clear()

# --- KATALOG KO'RISH (OPTIMALLASHTIRILGAN) ---
@dp.message(F.text == "🪑 Katalog")
async def catalog_show(message: Message):
    conn = get_db_connection()
    items = conn.cursor().execute("SELECT cat, info, photo FROM furniture").fetchall()
    conn.close()
    
    if not items: return await message.answer("Hozircha katalog bo'sh.")
    
    # 10 tagacha rasmni bitta albom qilib chiqaramiz (Spamni oldini olish uchun)
    media = []
    for item in items[:10]: 
        caption = f"📁 {item[0]}\nℹ️ {item[1]}"
        media.append(InputMediaPhoto(media=item[2], caption=caption))
    
    await message.answer_media_group(media=media)
    if len(items) > 10:
        await message.answer("<i>Ko'proq modellarni ko'rish uchun ofisimizga keling...</i>")

# --- REKLAMA YUBORISH ---
@dp.callback_query(F.data == "send_ad")
async def ad_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("✉️ Reklamani yuboring (Rasm, video yoki matn):")
    await state.set_state(AdminState.waiting_ad)
    await call.answer()

@dp.message(AdminState.waiting_ad)
async def ad_final(message: Message, state: FSMContext):
    conn = get_db_connection()
    users = conn.cursor().execute("SELECT id FROM users").fetchall()
    conn.close()
    
    count = 0
    await message.answer("⏳ Yuborish boshlandi...")
    
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05) # Telegram bloklamasligi uchun pauza
        except Exception:
            continue
            
    await message.answer(f"✅ Reklama {count} kishiga yuborildi.")
    await state.clear()

# --- QOLGAN TUGMALAR ---
@dp.callback_query(F.data == "del_chan")
async def del_chan(call: CallbackQuery):
    conn = get_db_connection(); conn.execute("DELETE FROM channels"); conn.commit(); conn.close()
    await call.message.answer("❌ Barcha kanallar o'chirildi."); await call.answer()

@dp.callback_query(F.data == "clear_cat")
async def clear_cat(call: CallbackQuery):
    conn = get_db_connection(); conn.execute("DELETE FROM furniture"); conn.commit(); conn.close()
    await call.message.answer("🗑 Katalog tozalandi."); await call.answer()

@dp.message(F.text == "📞 Aloqa")
async def contact(message: Message):
    await message.answer(f"📞 Murojaat uchun: @AdminUser") # O'zingizni useringizni yozing

@dp.message(F.text == "📍 Manzilimiz")
async def loc(message: Message):
    await message.answer("📍 Bizning manzil: Toshkent sh., Chilonzor tumani.") # Aniq manzil

@dp.message(F.text == "ℹ️ Biz haqimizda")
async def about(message: Message):
    await message.answer("Biz sifatli va hamyonbop mebellar ishlab chiqaruvchi kompaniyamiz.")

# --- ISHGA TUSHIRISH ---
async def on_startup(bot: Bot):
    init_db()
    # Webhookni tozalab yangisini o'rnatamiz
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