import asyncio
import logging
import sqlite3
import os
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, CommandStart, StateFilter
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
# 1. ASOSIY KONFIGURATSIYA (TOKEN VA LINKLAR)
# ==========================================================
BOT_TOKEN = "8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE"
ADMIN_ID = 5767267885
WEBHOOK_URL = "https://mebelbot.onrender.com"
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8080))

# ==========================================================
# 2. BAZA BILAN ISHLASH (SQLITE3)
# ==========================================================
def db_start():
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    # Foydalanuvchilar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined_date TEXT
    )""")
    # Kanallar jadvali
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, channel_id TEXT)")
    # Kategoriyalar jadvali
    cursor.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    # Mahsulotlar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        photo_id TEXT,
        name TEXT,
        size TEXT,
        quantity TEXT,
        price TEXT,
        description TEXT
    )""")
    conn.commit()
    conn.close()

# ==========================================================
# 3. STATE (HOLATLAR) BOSHQARUVI
# ==========================================================
class AdminState(StatesGroup):
    # Kategoriya qo'shish
    add_category_name = State()
    # Mahsulot qo'shish bosqichlari
    prod_category_select = State()
    prod_photo = State()
    prod_name = State()
    prod_size = State()
    prod_quantity = State()
    prod_price = State()
    prod_description = State()
    # Majburiy obuna
    add_channel_id = State()
    add_channel_link = State()
    # Xabar yuborish
    broadcast_msg = State()

# ==========================================================
# 4. KLAVIATURALAR
# ==========================================================
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗂 Bo'limlar"), KeyboardButton(text="📞 Bog'lanish")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_admin_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stat"))
    builder.row(InlineKeyboardButton(text="✉️ Xabar Yuborish", callback_data="admin_send_all"))
    builder.row(InlineKeyboardButton(text="📂 Bo'lim Qo'shish", callback_data="admin_add_cat"))
    builder.row(InlineKeyboardButton(text="🛋 Mahsulot Qo'shish", callback_data="admin_add_product"))
    builder.row(InlineKeyboardButton(text="📢 Kanal Qo'shish", callback_data="admin_add_chan"))
    builder.row(InlineKeyboardButton(text="🗑 Kanallarni Tozalash", callback_data="admin_clear_chan"))
    return builder.as_markup()

# ==========================================================
# 5. BOTNI SOZLASH
# ==========================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ==========================================================
# 6. OBUNANI TEKSHIRISH FUNKSIYASI
# ==========================================================
async def is_user_subscribed(user_id: int):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, link FROM channels")
    channels = cursor.fetchall()
    conn.close()
    
    not_subscribed_links = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                not_subscribed_links.append(link)
        except Exception:
            # Agar bot kanalda admin bo'lmasa yoki kanal topilmasa
            continue
    return not_subscribed_links

# ==========================================================
# 7. FOYDALANUVCHI HANDLERLARI (USER INTERFACE)
# ==========================================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Foydalanuvchini bazaga saqlash
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined_date) VALUES (?, ?, ?)", (user_id, username, now))
    conn.commit()
    conn.close()

    # Obunani tekshirish
    not_subbed = await is_user_subscribed(user_id)
    if not_subbed:
        builder = InlineKeyboardBuilder()
        for link in not_subbed:
            builder.row(InlineKeyboardButton(text="Obuna bo'lish", url=link))
        builder.row(InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription"))
        await message.answer("Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=builder.as_markup())
    else:
        await message.answer(f"Assalomu alaykum {message.from_user.full_name}!\nMebel katalogi botiga xush kelibsiz.", reply_markup=get_main_menu())

@router.callback_query(F.data == "check_subscription")
async def check_sub_cb(call: CallbackQuery):
    not_subbed = await is_user_subscribed(call.from_user.id)
    if not_subbed:
        await call.answer("Siz hali barcha kanallarga obuna bo'lmagansiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("Obuna tasdiqlandi. Marhamat, bo'limlarni tanlang:", reply_markup=get_main_menu())

@router.message(F.text == "📞 Bog'lanish")
async def contact_us(message: Message):
    text = "📍 Bizning manzil: Toshkent shahri\n📞 Aloqa: +998901234567\n👤 Admin: @admin_username"
    await message.answer(text)

@router.message(F.text == "🗂 Bo'limlar")
async def show_categories(message: Message):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()

    if not cats:
        await message.answer("Hozircha bo'limlar mavjud emas.")
        return

    builder = InlineKeyboardBuilder()
    for cat_id, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}"))
    
    await message.answer("Kerakli bo'limni tanlang:", reply_markup=builder.as_markup())

# --- MAHSULOTLARNI KO'RISH VA NAVIGATSIYA ---
@router.callback_query(F.data.startswith("cat_"))
async def open_category(call: CallbackQuery):
    cat_id = int(call.data.split("_")[1])
    await send_product_page(call.message, cat_id, 0)
    await call.message.delete()

async def send_product_page(message: Message, cat_id: int, index: int):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT photo_id, name, size, quantity, price, description FROM products WHERE category_id = ?", (cat_id,))
    all_products = cursor.fetchall()
    conn.close()

    if not all_products:
        await message.answer("Ushbu bo'limda mahsulotlar topilmadi.")
        return

    if index >= len(all_products): index = 0
    if index < 0: index = len(all_products) - 1

    p = all_products[index]
    caption = (
        f"🏷 <b>Nomi:</b> {p[1]}\n"
        f"📏 <b>O'lchami:</b> {p[2]}\n"
        f"🔢 <b>Soni:</b> {p[3]}\n"
        f"💰 <b>Narxi:</b> {p[4]}\n\n"
        f"📝 <b>Tavsif:</b> {p[5]}\n\n"
        f"👨‍💻 Buyurtma uchun: @admin_username"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"page_{cat_id}_{index-1}"),
        InlineKeyboardButton(text="❌", callback_data="close_view"),
        InlineKeyboardButton(text="➡️", callback_data=f"page_{cat_id}_{index+1}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Bo'limlarga qaytish", callback_data="back_to_categories"))

    await message.answer_photo(
        photo=p[0],
        caption=caption,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("page_"))
async def paginate_products(call: CallbackQuery):
    _, cat_id, index = call.data.split("_")
    await call.message.delete()
    await send_product_page(call.message, int(cat_id), int(index))

@router.callback_query(F.data == "close_view")
async def delete_msg(call: CallbackQuery):
    await call.message.delete()

@router.callback_query(F.data == "back_to_categories")
async def back_to_cats(call: CallbackQuery):
    await call.message.delete()
    # categories_handler funksiyasi o'rniga to'g'ridan to'g'ri chaqiramiz
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    builder = InlineKeyboardBuilder()
    for cat_id, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"cat_{cat_id}"))
    await call.message.answer("Kerakli bo'limni tanlang:", reply_markup=builder.as_markup())

# ==========================================================
# 8. ADMIN HANDLERLARI (BOSHQRUV)
# ==========================================================
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👨‍💻 Admin panelga xush kelibsiz!", reply_markup=get_admin_menu())

@router.callback_query(F.data == "admin_stat")
async def admin_stat(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(id) FROM products")
    prod_count = cursor.fetchone()[0]
    conn.close()
    await call.message.answer(f"📊 Statistika:\n\n👥 Foydalanuvchilar: {user_count}\n🛋 Mahsulotlar: {prod_count}")

# --- KATEGORIYA QO'SHISH ---
@router.callback_query(F.data == "admin_add_cat")
async def admin_add_cat(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim (kategoriya) nomini yuboring:")
    await state.set_state(AdminState.add_category_name)

@router.message(AdminState.add_category_name)
async def process_add_cat(message: Message, state: FSMContext):
    cat_name = message.text
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ {cat_name} bo'limi muvaffaqiyatli qo'shildi!", reply_markup=get_admin_menu())
    await state.clear()

# --- MAHSULOT QO'SHISH BOSQICHLARI ---
@router.callback_query(F.data == "admin_add_product")
async def admin_add_prod_step1(call: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    if not cats:
        await call.answer("Avval bo'lim qo'shishingiz kerak!", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"selcat_{cid}"))
    await call.message.answer("Mahsulot qaysi bo'limga qo'shilsin?", reply_markup=builder.as_markup())
    await state.set_state(AdminState.prod_category_select)

@router.callback_query(AdminState.prod_category_select, F.data.startswith("selcat_"))
async def admin_add_prod_step2(call: CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[1]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Mahsulot rasmini yuboring:")
    await state.set_state(AdminState.prod_photo)

@router.message(AdminState.prod_photo, F.photo)
async def admin_add_prod_step3(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("Mahsulot nomini kiriting:")
    await state.set_state(AdminState.prod_name)

@router.message(AdminState.prod_name)
async def admin_add_prod_step4(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Mahsulot o'lchamini kiriting (masalan: 200x150):")
    await state.set_state(AdminState.prod_size)

@router.message(AdminState.prod_size)
async def admin_add_prod_step5(message: Message, state: FSMContext):
    await state.update_data(size=message.text)
    await message.answer("Mahsulot sonini kiriting (masalan: 5 ta):")
    await state.set_state(AdminState.prod_quantity)

@router.message(AdminState.prod_quantity)
async def admin_add_prod_step6(message: Message, state: FSMContext):
    await state.update_data(quantity=message.text)
    await message.answer("Mahsulot narxini kiriting (masalan: 1,500,000 so'm):")
    await state.set_state(AdminState.prod_price)

@router.message(AdminState.prod_price)
async def admin_add_prod_step7(message: Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Mahsulot uchun batafsil tavsif (description) yuboring:")
    await state.set_state(AdminState.prod_description)

@router.message(AdminState.prod_description)
async def admin_add_prod_final(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO products (category_id, photo_id, name, size, quantity, price, description)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data['cat_id'], data['photo_id'], data['name'], data['size'], data['quantity'], data['price'], message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Mahsulot muvaffaqiyatli saqlandi!", reply_markup=get_admin_menu())
    await state.clear()

# --- REKLAMA TARQATISH ---
@router.callback_query(F.data == "admin_send_all")
async def admin_send_all(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Hamma foydalanuvchilarga yuboriladigan xabarni (rasm, matn, video) yuboring:")
    await state.set_state(AdminState.broadcast_msg)

@router.message(AdminState.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    count = 0
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.", reply_markup=get_admin_menu())
    await state.clear()

# --- MAJBURIY OBUNA (KANAL QO'SHISH) ---
@router.callback_query(F.data == "admin_add_chan")
async def admin_add_chan(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID raqamini yuboring (masalan: -100123456789):")
    await state.set_state(AdminState.add_channel_id)

@router.message(AdminState.add_channel_id)
async def process_chan_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text)
    await message.answer("Kanal linkini yuboring (masalan: https://t.me/kanal_linki):")
    await state.set_state(AdminState.add_channel_link)

@router.message(AdminState.add_channel_link)
async def process_chan_link(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO channels (link, channel_id) VALUES (?, ?)", (message.text, data['ch_id']))
    conn.commit()
    conn.close()
    await message.answer("✅ Kanal majburiy obuna ro'yxatiga qo'shildi!", reply_markup=get_admin_menu())
    await state.clear()

@router.callback_query(F.data == "admin_clear_chan")
async def clear_channels(call: CallbackQuery):
    conn = sqlite3.connect('mebel.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels")
    conn.commit()
    conn.close()
    await call.answer("Barcha kanallar o'chirildi!", show_alert=True)

# ==========================================================
# 9. SERVER VA WEBHOOK ISHGA TUSHIRISH
# ==========================================================
async def on_startup(bot: Bot):
    db_start()
    # Webhookni o'rnatish
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
    logging.info(f"Webhook set to: {WEBHOOK_URL}{WEBHOOK_PATH}")

def main():
    dp.include_router(router)
    dp.startup.register(on_startup)
    
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running live!"))
    
    # Webhook so'rovlarini qabul qilish
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()