import asyncio
import logging
import sqlite3
import os
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    CallbackQuery, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ==========================================================
# 1. KONFIGURATSIYA
# ==========================================================
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
ADMIN_ID = 8553997595  # Asosiy admin
WEBHOOK_URL = "https://mebelbot.onrender.com"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

# ==========================================================
# 2. BAZA BILAN ISHLASH (SQLITE3)
# ==========================================================
def db_start():
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, channel_id TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, photo_id TEXT, name TEXT, size TEXT, quantity TEXT, price TEXT, description TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    # Asosiy adminni bazaga kiritish
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return admins

# ==========================================================
# 3. STATE (HOLATLAR)
# ==========================================================
class AdminState(StatesGroup):
    add_category_name = State()
    prod_category_select = State()
    prod_photo = State()
    prod_name = State()
    prod_size = State()
    prod_quantity = State()
    prod_price = State()
    prod_description = State()
    add_channel_id = State()
    add_channel_link = State()
    broadcast_msg = State()
    add_new_admin = State()

# ==========================================================
# 4. KLAVIATURALAR
# ==========================================================
def get_main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🗂 Bo'limlar"), KeyboardButton(text="📞 Bog'lanish")],
        [KeyboardButton(text="ℹ️ Bot haqida"), KeyboardButton(text="🆘 Yordam")]
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="✉️ Xabar yuborish")],
        [KeyboardButton(text="📂 Bo'lim qo'shish"), KeyboardButton(text="🗑 Bo'limni o'chirish")],
        [KeyboardButton(text="🛋 Mahsulot qo'shish"), KeyboardButton(text="❌ Mahsulotni o'chirish")],
        [KeyboardButton(text="📢 Kanal qo'shish"), KeyboardButton(text="🚫 Kanalni o'chirish")],
        [KeyboardButton(text="👤 Admin qo'shish"), KeyboardButton(text="➖ Adminni o'chirish")],
        [KeyboardButton(text="🏠 Asosiy Menyu")]
    ], resize_keyboard=True)

# ==========================================================
# 5. BOTNI SOZLASH
# ==========================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ==========================================================
# 6. OBUNANI TEKSHIRISH
# ==========================================================
async def is_user_subscribed(user_id: int):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, link FROM channels")
    channels = cursor.fetchall()
    conn.close()
    not_subbed = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subbed.append(link)
        except: continue
    return not_subbed

# ==========================================================
# 7. FOYDALANUVCHI HANDLERLARI
# ==========================================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", 
                   (message.from_user.id, message.from_user.username, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

    not_subbed = await is_user_subscribed(message.from_user.id)
    if not_subbed:
        builder = InlineKeyboardBuilder()
        for link in not_subbed:
            builder.row(InlineKeyboardButton(text="Obuna bo'lish", url=link))
        builder.row(InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub"))
        await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=builder.as_markup())
    else:
        await message.answer("Katalogga xush kelibsiz!", reply_markup=get_main_menu())

@router.callback_query(F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery):
    not_subbed = await is_user_subscribed(call.from_user.id)
    if not_subbed:
        await call.answer("Barcha kanallarga obuna bo'ling!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("Xush kelibsiz!", reply_markup=get_main_menu())

@router.message(F.text == "ℹ️ Bot haqida")
async def about_bot(message: Message):
    await message.answer("Assalomu alaykum! @mebelsotuvchibot ga xush kelibsiz.\n\n")

@router.message(F.text == "🆘 Yordam")
async def help_cmd(message: Message):
    await message.answer("Muammo yuzaga kelsa @saidaliyev_f adminiga murojaat qiling.")

@router.message(F.text == "📞 Bog'lanish")
async def contact(message: Message):
    await message.answer("📍 Andijon shahar\n📞 +998995381222\n👤 @saidaliyev_f")

@router.message(F.text == "🗂 Bo'limlar")
async def show_cats(message: Message):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    if not cats:
        await message.answer("Hozircha bo'limlar mavjud emas.")
        return
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"usercat_{cid}"))
    await message.answer("Bo'limni tanlang:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("usercat_"))
async def open_cat(call: CallbackQuery):
    cat_id = int(call.data.split("_")[1])
    await show_products_to_user(call.message, cat_id, 0)
    await call.message.delete()

async def show_products_to_user(message, cat_id, index):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT photo_id, name, size, quantity, price, description FROM products WHERE category_id = ?", (cat_id,))
    prods = cursor.fetchall()
    conn.close()
    if not prods:
        await message.answer("Bu bo'limda mahsulotlar yo'q.", reply_markup=get_main_menu())
        return
    if index >= len(prods): index = 0
    if index < 0: index = len(prods)-1
    p = prods[index]
    caption = f"🏷 <b>{p[1]}</b>\n📏 O'lcham: {p[2]}\n🔢 Soni: {p[3]}\n💰 Narx: {p[4]}\n\n📝 {p[5]}\n\n👨‍💻 @xamidovcore"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️", callback_data=f"unav_{cat_id}_{index-1}"),
                InlineKeyboardButton(text="➡️", callback_data=f"unav_{cat_id}_{index+1}"))
    builder.row(InlineKeyboardButton(text="🔙 Bo'limlarga qaytish", callback_data="back_user_cats"))
    await message.answer_photo(photo=p[0], caption=caption, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("unav_"))
async def user_nav(call: CallbackQuery):
    _, cid, idx = call.data.split("_")
    await call.message.delete()
    await show_products_to_user(call.message, int(cid), int(idx))

@router.callback_query(F.data == "back_user_cats")
async def back_u_cats(call: CallbackQuery):
    await call.message.delete()
    await show_cats(call.message)

# ==========================================================
# 8. ADMIN HANDLERLARI (TO'LIQ)
# ==========================================================
@router.message(Command("admin"))
async def admin_entry(message: Message):
    if message.from_user.id in get_admins():
        await message.answer("👨‍💻 Admin Panelga xush kelibsiz!", reply_markup=get_admin_keyboard())

@router.message(F.text == "🏠 Asosiy Menyu")
async def back_home(message: Message):
    await message.answer("Bosh menyu:", reply_markup=get_main_menu())

@router.message(F.text == "📊 Statistika")
async def admin_stat(message: Message):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    u = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    c = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    p = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()
    await message.answer(f"📊 <b>Bot Statistikasi:</b>\n\n👥 Foydalanuvchilar: {u}\n📂 Bo'limlar: {c}\n🛋 Mahsulotlar: {p}", parse_mode="HTML")

# --- KANAL BOSHQARUVI ---
@router.message(F.text == "📢 Kanal qo'shish")
async def add_chan_start(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins(): return
    await message.answer("Kanal ID raqamini yuboring (-100...):")
    await state.set_state(AdminState.add_channel_id)

@router.message(AdminState.add_channel_id)
async def add_chan_id(message: Message, state: FSMContext):
    await state.update_data(chid=message.text)
    await message.answer("Kanal linkini yuboring (https://t.me/...):")
    await state.set_state(AdminState.add_channel_link)

@router.message(AdminState.add_channel_link)
async def add_chan_link(message: Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO channels (link, channel_id) VALUES (?, ?)", (message.text, d['chid']))
    conn.commit()
    conn.close()
    await message.answer("✅ Kanal qo'shildi.", reply_markup=get_admin_keyboard())
    await state.clear()

@router.message(F.text == "🚫 Kanalni o'chirish")
async def del_chan_list(message: Message):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, link FROM channels")
    chans = cursor.fetchall()
    conn.close()
    if not chans:
        await message.answer("Kanallar yo'q.")
        return
    builder = InlineKeyboardBuilder()
    for cid, link in chans:
        builder.row(InlineKeyboardButton(text=f"❌ {link}", callback_data=f"delchan_{cid}"))
    await message.answer("O'chirish uchun kanalni tanlang:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("delchan_"))
async def del_chan_exec(call: CallbackQuery):
    cid = call.data.split("_")[1]
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    await call.answer("Kanal o'chirildi.")
    await call.message.delete()

# --- ADMIN BOSHQARUVI ---
@router.message(F.text == "👤 Admin qo'shish")
async def add_adm_start(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins(): return
    await message.answer("Yangi admin Telegram ID sini yuboring:")
    await state.set_state(AdminState.add_new_admin)

@router.message(AdminState.add_new_admin)
async def add_adm_final(message: Message, state: FSMContext):
    try:
        aid = int(message.text)
        conn = sqlite3.connect('mebel.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (aid,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ ID:{aid} admin qilindi.")
    except: await message.answer("Xato! Faqat raqam yuboring.")
    await state.clear()

@router.message(F.text == "➖ Adminni o'chirish")
async def del_adm_list(message: Message):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    adms = cursor.fetchall()
    conn.close()
    builder = InlineKeyboardBuilder()
    for (aid,) in adms:
        if aid != ADMIN_ID:
            builder.row(InlineKeyboardButton(text=f"👤 ID:{aid}", callback_data=f"deladm_{aid}"))
    await message.answer("O'chiriladigan adminni tanlang:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("deladm_"))
async def del_adm_exec(call: CallbackQuery):
    aid = call.data.split("_")[1]
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (aid,))
    conn.commit()
    conn.close()
    await call.answer("Admin o'chirildi.")
    await call.message.delete()

# --- BO'LIM VA MAHSULOT O'CHIRISH ---
@router.message(F.text == "🗑 Bo'limni o'chirish")
async def del_cat_list(message: Message):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(InlineKeyboardButton(text=f"🗑 {name}", callback_data=f"delcat_{cid}"))
    await message.answer("Bo'limni tanlang (Unga tegishli hamma mahsulotlar ham o'chadi!):", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("delcat_"))
async def del_cat_exec(call: CallbackQuery):
    cid = call.data.split("_")[1]
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE category_id = ?", (cid,))
    cursor.execute("DELETE FROM categories WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    await call.answer("Bo'lim o'chirildi.")
    await call.message.delete()

@router.message(F.text == "❌ Mahsulotni o'chirish")
async def del_prod_step1(message: Message):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"pdelcat_{cid}"))
    await message.answer("Qaysi bo'limdagi mahsulotni o'chirmoqchisiz?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("pdelcat_"))
async def del_prod_step2(call: CallbackQuery):
    cid = call.data.split("_")[1]
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products WHERE category_id = ?", (cid,))
    prods = cursor.fetchall()
    conn.close()
    if not prods:
        await call.answer("Bu bo'limda mahsulot yo'q.")
        return
    builder = InlineKeyboardBuilder()
    for pid, name in prods:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"pdelexec_{pid}"))
    await call.message.answer("O'chiriladigan mahsulotni tanlang:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("pdelexec_"))
async def del_prod_exec(call: CallbackQuery):
    pid = call.data.split("_")[1]
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    await call.answer("Mahsulot o'chirildi.")
    await call.message.delete()

# --- BO'LIM QO'SHISH ---
@router.message(F.text == "📂 Bo'lim qo'shish")
async def add_cat_start(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins(): return
    await message.answer("Yangi bo'lim nomini yuboring:")
    await state.set_state(AdminState.add_category_name)

@router.message(AdminState.add_category_name)
async def add_cat_final(message: Message, state: FSMContext):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (name) VALUES (?)", (message.text,))
    conn.commit()
    conn.close()
    await message.answer("✅ Bo'lim saqlandi.", reply_markup=get_admin_keyboard())
    await state.clear()

# --- MAHSULOT QO'SHISH ---
@router.message(F.text == "🛋 Mahsulot qo'shish")
async def add_p_step1(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins(): return
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    if not cats:
        await message.answer("Avval bo'lim qo'shing!")
        return
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"selc_{cid}"))
    await message.answer("Bo'limni tanlang:", reply_markup=builder.as_markup())
    await state.set_state(AdminState.prod_category_select)

@router.callback_query(AdminState.prod_category_select)
async def add_p_step2(call: CallbackQuery, state: FSMContext):
    cid = call.data.split("_")[1]
    await state.update_data(cid=cid)
    await call.message.answer("Rasm yuboring:")
    await state.set_state(AdminState.prod_photo)

@router.message(AdminState.prod_photo, F.photo)
async def add_p_step3(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Nomini yozing:")
    await state.set_state(AdminState.prod_name)

@router.message(AdminState.prod_name)
async def add_p_step4(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("O'lchami:")
    await state.set_state(AdminState.prod_size)

@router.message(AdminState.prod_size)
async def add_p_step5(message: Message, state: FSMContext):
    await state.update_data(size=message.text)
    await message.answer("Soni:")
    await state.set_state(AdminState.prod_quantity)

@router.message(AdminState.prod_quantity)
async def add_p_step6(message: Message, state: FSMContext):
    await state.update_data(qty=message.text)
    await message.answer("Narxi:")
    await state.set_state(AdminState.prod_price)

@router.message(AdminState.prod_price)
async def add_p_step7(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Tavsif (description):")
    await state.set_state(AdminState.prod_description)

@router.message(AdminState.prod_description)
async def add_p_final(message: Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (category_id, photo_id, name, size, quantity, price, description) VALUES (?,?,?,?,?,?,?)",
                   (d['cid'], d['photo'], d['name'], d['size'], d['qty'], d['price'], message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Mahsulot qo'shildi!", reply_markup=get_admin_keyboard())
    await state.clear()

# --- REKLAMA ---
@router.message(F.text == "✉️ Xabar yuborish")
async def broad_s(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins(): return
    await message.answer("Reklama xabarini (matn, rasm, video) yuboring:")
    await state.set_state(AdminState.broadcast_msg)

@router.message(AdminState.broadcast_msg)
async def broad_f(message: Message, state: FSMContext):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    count = 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ {count} ta foydalanuvchiga yuborildi.", reply_markup=get_admin_keyboard())
    await state.clear()

# ==========================================================
# 9. SERVER VA WEBHOOK
# ==========================================================
async def on_startup(bot: Bot):
    db_start()
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)

def main():
    dp.include_router(router)
    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is Live!"))
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()