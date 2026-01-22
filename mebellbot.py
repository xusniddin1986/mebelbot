import asyncio
import logging
import sqlite3
import os
import sys
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- CONFIG ---
BOT_TOKEN = os.getenv("8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5767267885"))
WEBHOOK_URL = os.getenv("https://mebelbot.onrender.com") 
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

# --- DATABASE SETUP ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

def db_start():
    db_query("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_date TEXT)""", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS channels (link TEXT, channel_id TEXT)""", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)""", commit=True)
    db_query("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, photo_id TEXT, 
        name TEXT, size TEXT, quantity TEXT, price TEXT, description TEXT)""", commit=True)

# --- STATES ---
class AdminState(StatesGroup):
    add_channel_id = State()
    add_channel_link = State()
    add_category = State()
    del_category = State()
    # Mahsulot qo'shish bosqichlari
    prod_cat_select = State()
    prod_photo = State()
    prod_name = State()
    prod_size = State()
    prod_qty = State()
    prod_price = State()
    prod_desc = State()
    # Xabar tarqatish
    broadcast = State()

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- UTILS ---
async def check_sub(user_id):
    channels = db_query("SELECT channel_id, link FROM channels", fetchall=True)
    not_subbed = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']: not_subbed.append(link)
        except: continue
    return not_subbed

def main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🗂 Bo'limlar"), KeyboardButton(text="📞 Bog'lanish")]
    ], resize_keyboard=True)

def admin_panel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="adm_stats")
    builder.button(text="✉️ Xabar Yuborish", callback_data="adm_broadcast")
    builder.button(text="📂 Bo'lim Qo'shish", callback_data="adm_add_cat")
    builder.button(text="🗑 Bo'lim O'chirish", callback_data="adm_del_cat")
    builder.button(text="🛋 Mahsulot Qo'shish", callback_data="adm_add_prod")
    builder.button(text="📢 Majburiy Obuna (+)", callback_data="adm_add_sub")
    builder.button(text="🚫 Obunani Tozalash", callback_data="adm_clear_sub")
    builder.adjust(2)
    return builder.as_markup()

# --- USER HANDLERS ---
@router.message(CommandStart())
async def start_handler(message: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id, username, joined_date) VALUES (?, ?, datetime('now'))", 
             (message.from_user.id, message.from_user.username), commit=True)
    
    not_subbed = await check_sub(message.from_user.id)
    if not_subbed:
        builder = InlineKeyboardBuilder()
        for link in not_subbed: builder.button(text="Obuna bo'lish", url=link)
        builder.button(text="✅ Tekshirish", callback_data="check_subs")
        builder.adjust(1)
        await message.answer("Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=builder.as_markup())
    else:
        await message.answer(f"Assalomu alaykum! Mebel botiga xush kelibsiz.", reply_markup=main_menu_kb())

@router.callback_query(F.data == "check_subs")
async def check_subs_callback(call: types.CallbackQuery):
    not_subbed = await check_sub(call.from_user.id)
    if not_subbed:
        await call.answer("Hali hamma kanalga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("Obuna tasdiqlandi! Bo'limlarni tanlang:", reply_markup=main_menu_kb())

@router.message(F.text == "📞 Bog'lanish")
async def contact_handler(message: types.Message):
    await message.answer(f"📍 Manzil: Toshkent sh.\n📞 Tel: +998901234567\n👤 Admin: @admin")

@router.message(F.text == "🗂 Bo'limlar")
async def categories_handler(message: types.Message):
    cats = db_query("SELECT id, name FROM categories", fetchall=True)
    if not cats:
        await message.answer("Hozircha bo'limlar yo'q.")
        return
    builder = InlineKeyboardBuilder()
    for cid, name in cats: builder.button(text=name, callback_data=f"view_cat_{cid}")
    builder.adjust(2)
    await message.answer("Bo'limni tanlang:", reply_markup=builder.as_markup())

# --- PRODUCT VIEW LOGIC ---
@router.callback_query(F.data.startswith("view_cat_"))
async def view_category(call: types.CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    await show_product(call.message, cat_id, 0)
    await call.message.delete()

async def show_product(message, cat_id, index):
    prods = db_query("SELECT photo_id, name, size, quantity, price, description FROM products WHERE category_id = ?", (cat_id,), fetchall=True)
    if not prods:
        await message.answer("Bu bo'limda mahsulot yo'q.", reply_markup=main_menu_kb())
        return

    if index >= len(prods): index = 0
    elif index < 0: index = len(prods) - 1
    
    p = prods[index]
    caption = (f"🏷 <b>Nomi:</b> {p[1]}\n📏 <b>O'lchami:</b> {p[2]}\n"
               f"🔢 <b>Soni:</b> {p[3]}\n💰 <b>Narxi:</b> {p[4]}\n\n"
               f"✍️ {p[5]}\n\n👨‍💻 Buyurtma: @admin")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️", callback_data=f"nav_{cat_id}_{index-1}")
    builder.button(text="❌ Bo'limlarga qaytish", callback_data="back_to_cats")
    builder.button(text="➡️", callback_data=f"nav_{cat_id}_{index+1}")
    builder.adjust(3)
    
    await message.answer_photo(photo=p[0], caption=caption, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("nav_"))
async def navigation_handler(call: types.CallbackQuery):
    _, cat_id, idx = call.data.split("_")
    await call.message.delete()
    await show_product(call.message, int(cat_id), int(idx))

@router.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: types.CallbackQuery):
    await call.message.delete()
    await categories_handler(call.message)

# --- ADMIN PANEL HANDLERS ---
@router.message(Command("admin"))
async def admin_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👨‍💻 Admin Panelga xush kelibsiz!", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: types.CallbackQuery):
    u = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    p = db_query("SELECT COUNT(*) FROM products", fetchone=True)[0]
    await call.answer(f"Foydalanuvchilar: {u}\nMahsulotlar: {p}", show_alert=True)

@router.callback_query(F.data == "adm_add_cat")
async def adm_add_cat(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yuboring:")
    await state.set_state(AdminState.add_category)

@router.message(AdminState.add_category)
async def save_category(message: types.Message, state: FSMContext):
    db_query("INSERT INTO categories (name) VALUES (?)", (message.text,), commit=True)
    await message.answer(f"✅ {message.text} bo'limi qo'shildi.", reply_markup=admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "adm_add_prod")
async def adm_add_prod(call: types.CallbackQuery, state: FSMContext):
    cats = db_query("SELECT id, name FROM categories", fetchall=True)
    if not cats:
        await call.answer("Avval bo'lim qo'shing!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for cid, name in cats: builder.button(text=name, callback_data=f"addp_cat_{cid}")
    builder.adjust(2)
    await call.message.answer("Mahsulot qaysi bo'limga qo'shilsin?", reply_markup=builder.as_markup())
    await state.set_state(AdminState.prod_cat_select)

@router.callback_query(AdminState.prod_cat_select, F.data.startswith("addp_cat_"))
async def addp_cat_sel(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=call.data.split("_")[2])
    await call.message.answer("Mahsulot rasmini yuboring:")
    await state.set_state(AdminState.prod_photo)

@router.message(AdminState.prod_photo, F.photo)
async def addp_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Mahsulot nomini kiriting:")
    await state.set_state(AdminState.prod_name)

@router.message(AdminState.prod_name)
async def addp_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("O'lchamini kiriting:")
    await state.set_state(AdminState.prod_size)

@router.message(AdminState.prod_size)
async def addp_size(message: types.Message, state: FSMContext):
    await state.update_data(size=message.text)
    await message.answer("Soni (masalan: 10 ta):")
    await state.set_state(AdminState.prod_qty)

@router.message(AdminState.prod_qty)
async def addp_qty(message: types.Message, state: FSMContext):
    await state.update_data(qty=message.text)
    await message.answer("Narxini kiriting:")
    await state.set_state(AdminState.prod_price)

@router.message(AdminState.prod_price)
async def addp_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Batafsil ma'lumot (tavsif) kiriting:")
    await state.set_state(AdminState.prod_desc)

@router.message(AdminState.prod_desc)
async def addp_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    db_query("INSERT INTO products (category_id, photo_id, name, size, quantity, price, description) VALUES (?,?,?,?,?,?,?)",
             (d['cat_id'], d['photo'], d['name'], d['size'], d['qty'], d['price'], message.text), commit=True)
    await message.answer("✅ Mahsulot muvaffaqiyatli qo'shildi!", reply_markup=admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "adm_broadcast")
async def adm_bc(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Reklama xabarini yuboring (Rasm, matn, video...):")
    await state.set_state(AdminState.broadcast)

@router.message(AdminState.broadcast)
async def start_bc(message: types.Message, state: FSMContext):
    users = db_query("SELECT user_id FROM users", fetchall=True)
    count = 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.", reply_markup=admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "adm_add_sub")
async def adm_add_sub(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID sini kiriting (masalan: -1001234567):")
    await state.set_state(AdminState.add_channel_id)

@router.message(AdminState.add_channel_id)
async def sub_id(message: types.Message, state: FSMContext):
    await state.update_data(cid=message.text)
    await message.answer("Kanal linkini kiriting (https://t.me/...):")
    await state.set_state(AdminState.add_channel_link)

@router.message(AdminState.add_channel_link)
async def sub_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    db_query("INSERT INTO channels (channel_id, link) VALUES (?,?)", (d['cid'], message.text), commit=True)
    await message.answer("✅ Majburiy obuna qo'shildi!", reply_markup=admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "adm_clear_sub")
async def clear_sub(call: types.CallbackQuery):
    db_query("DELETE FROM channels", commit=True)
    await call.answer("Majburiy obunalar tozalandi!", show_alert=True)

# --- WEBHOOK & STARTUP ---
async def on_startup(bot: Bot):
    db_start()
    if WEBHOOK_URL: await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()