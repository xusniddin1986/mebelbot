import asyncio
import logging
import sqlite3
import os
import sys
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- CONFIG ---
# Renderda Environment Variable orqali olinadi yoki shu yerga yozing
TOKEN = os.getenv("8564481489:AAG3DMZO7rdUm-J0Ux-5Dleg3PVHvmRDbXE")
ADMIN_ID = int(os.getenv("5767267885"))  # Raqam bo'lishi shart

# Web server port (Render uchun)
PORT = int(os.getenv("PORT", 8080))

# --- DATABASE SETUP ---
conn = sqlite3.connect('mebel.db')
cursor = conn.cursor()

def db_start():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined_date TEXT
    )""")
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (link TEXT, channel_id TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        photo_id TEXT,
        name TEXT,
        size TEXT,
        quantity INTEGER,
        price TEXT,
        description TEXT
    )""")
    conn.commit()

# --- STATES ---
class AdminState(StatesGroup):
    add_channel_id = State()
    add_channel_link = State()
    add_category = State()
    # Mahsulot qo'shish
    prod_category = State()
    prod_photo = State()
    prod_name = State()
    prod_size = State()
    prod_qty = State()
    prod_price = State()
    # Xabar yuborish
    broadcast = State()

# --- BOT SETUP ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- HELPER FUNCTIONS ---

# Obunani tekshirish
async def check_sub(user_id):
    cursor.execute("SELECT channel_id, link FROM channels")
    channels = cursor.fetchall()
    not_subbed = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subbed.append(link)
        except:
            continue # Bot admin emas yoki xato
    return not_subbed

# Asosiy menyu (User)
def main_menu_kb():
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🗂 Bo'limlar"), KeyboardButton(text="📞 Bog'lanish")]
    ], resize_keyboard=True)
    return kb

# Admin Panel (Rasmga o'xshash)
def admin_panel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="adm_stats")
    builder.button(text="✉️ Xabar Yuborish", callback_data="adm_broadcast")
    builder.button(text="📂 Bo'limlar (+/-)", callback_data="adm_cats")
    builder.button(text="🛋 Mahsulot (+/-)", callback_data="adm_prods")
    builder.button(text="📢 Majburiy Obuna", callback_data="adm_subs")
    builder.button(text="👥 Adminlar", callback_data="adm_admins")
    builder.adjust(2)
    return builder.as_markup()

# --- USER HANDLERS ---

@router.message(CommandStart())
async def start_handler(message: types.Message):
    # Foydalanuvchini bazaga qo'shish
    user_id = message.from_user.id
    username = message.from_user.username
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined_date) VALUES (?, ?, datetime('now'))", (user_id, username))
    conn.commit()

    # Obuna tekshiruvi
    not_subbed = await check_sub(user_id)
    if not_subbed:
        builder = InlineKeyboardBuilder()
        for link in not_subbed:
            builder.button(text="Obuna bo'lish", url=link)
        builder.button(text="✅ Tekshirish", callback_data="check_subs")
        builder.adjust(1)
        await message.answer("Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=builder.as_markup())
    else:
        await message.answer(f"Assalomu alaykum, {message.from_user.full_name}! Mebel botiga xush kelibsiz.", reply_markup=main_menu_kb())

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
    # Bu yerda admin userini chiqarish
    await message.answer(f"📍 Manzil: Toshkent sh.\n📞 Tel: +998901234567\n👤 Admin: @admin (yoki user: {ADMIN_ID})")

@router.message(F.text == "🗂 Bo'limlar")
async def categories_handler(message: types.Message):
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    if not cats:
        await message.answer("Hozircha bo'limlar yo'q.")
        return
    
    builder = InlineKeyboardBuilder()
    for cat_id, name in cats:
        builder.button(text=name, callback_data=f"view_cat_{cat_id}")
    builder.adjust(2)
    await message.answer("Bo'limni tanlang:", reply_markup=builder.as_markup())

# --- MAHSULOT KO'RISH LOGIKASI (Previous/Next) ---
@router.callback_query(F.data.startswith("view_cat_"))
async def view_category(call: types.CallbackQuery):
    cat_id = int(call.data.split("_")[2])
    # Shu kategoriyadagi barcha mahsulot IDlarini olamiz
    cursor.execute("SELECT id FROM products WHERE category_id = ?", (cat_id,))
    products = cursor.fetchall() # [(1,), (5,), (6,)]
    
    if not products:
        await call.answer("Bu bo'limda mahsulot yo'q.", show_alert=True)
        return

    # Birinchi mahsulotni ko'rsatish
    await show_product(call.message, products, 0)
    await call.message.delete() # Eski menyuni o'chirish

async def show_product(message, all_products, index):
    # Indeks chegarasini tekshirish (Loop qilish uchun)
    if index >= len(all_products): index = 0
    if index < 0: index = len(all_products) - 1
    
    prod_id = all_products[index][0]
    cursor.execute("SELECT photo_id, name, size, quantity, price, description FROM products WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    
    caption = (
        f"🏷 <b>Nomi:</b> {prod[1]}\n"
        f"📏 <b>O'lchami:</b> {prod[2]}\n"
        f"🔢 <b>Soni:</b> {prod[3]}\n"
        f"💰 <b>Narxi:</b> {prod[4]}\n\n"
        f"✍️ {prod[5]}\n\n"
        f"👨‍💻 Buyurtma uchun: @admin"
    )
    
    # Navigatsiya tugmalari
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️", callback_data=f"nav_{index-1}_{all_products}") # Listni string qilib yuborish xavfli, lekin oddiy yechim uchun ishlatamiz.
    # Eslatma: Callback data limiti 64 bayt. Katta bazada bu usul o'rniga faqat index va cat_id yuborish kerak.
    # Keling, optimallashtiramiz: nav_{cat_id}_{current_index}
    
    # Hozirgi mahsulot qaysi kategoriyada ekanini bilish kerak
    cursor.execute("SELECT category_id FROM products WHERE id=?", (prod_id,))
    cat_id = cursor.fetchone()[0]
    
    builder.button(text="❌ O'chirish", callback_data="del_view")
    builder.button(text="➡️", callback_data=f"nav_{cat_id}_{index+1}")
    builder.adjust(3)
    
    try:
        await message.answer_photo(photo=prod[0], caption=caption, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        await message.answer("Rasm xatosi. \n" + caption, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("nav_"))
async def navigation_handler(call: types.CallbackQuery):
    _, cat_id, new_index = call.data.split("_")
    cat_id = int(cat_id)
    new_index = int(new_index)
    
    cursor.execute("SELECT id FROM products WHERE category_id = ?", (cat_id,))
    products = cursor.fetchall()
    
    await call.message.delete()
    await show_product(call.message, products, new_index)

@router.callback_query(F.data == "del_view")
async def close_view(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("Bo'limlar:", reply_markup=main_menu_kb())

# --- ADMIN PANEL HANDLERS ---

@router.message(Command("admin"))
async def admin_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👨‍💻 Admin Panelga xush kelibsiz!", reply_markup=admin_panel_kb())
    else:
        await message.answer("Siz admin emassiz.")

# 1. Statistika
@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM products")
    prod_count = cursor.fetchone()[0]
    await call.answer(f"👥 Foydalanuvchilar: {total} ta\n🛋 Mahsulotlar: {prod_count} ta", show_alert=True)

# 2. Majburiy Obuna Qo'shish
@router.callback_query(F.data == "adm_subs")
async def adm_subs(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal ID sini kiriting (masalan -100123456789): \nBot kanalga admin bo'lishi shart!")
    await state.set_state(AdminState.add_channel_id)

@router.message(AdminState.add_channel_id)
async def set_channel_id(message: types.Message, state: FSMContext):
    await state.update_data(chid=message.text)
    await message.answer("Kanal linkini yuboring (https://t.me/...):")
    await state.set_state(AdminState.add_channel_link)

@router.message(AdminState.add_channel_link)
async def set_channel_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("INSERT INTO channels (channel_id, link) VALUES (?, ?)", (data['chid'], message.text))
    conn.commit()
    await message.answer("Kanal qo'shildi!", reply_markup=admin_panel_kb())
    await state.clear()

# 3. Kategoriya Qo'shish
@router.callback_query(F.data == "adm_cats")
async def adm_cats(call: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yangi bo'lim qo'shish", callback_data="add_new_cat")
    builder.button(text="➖ Bo'limni o'chirish", callback_data="del_old_cat")
    await call.message.edit_reply_markup(reply_markup=builder.as_markup())

@router.callback_query(F.data == "add_new_cat")
async def add_cat_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yozing:")
    await state.set_state(AdminState.add_category)

@router.message(AdminState.add_category)
async def save_category(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO categories (name) VALUES (?)", (message.text,))
    conn.commit()
    await message.answer(f"{message.text} bo'limi qo'shildi.", reply_markup=admin_panel_kb())
    await state.clear()

# 4. Mahsulot Qo'shish
@router.callback_query(F.data == "adm_prods")
async def adm_prods(call: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Mahsulot qo'shish", callback_data="add_product")
    await call.message.edit_reply_markup(reply_markup=builder.as_markup())

@router.callback_query(F.data == "add_product")
async def start_add_prod(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    if not cats:
        await call.answer("Avval bo'lim yarating!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for cid, cname in cats:
        builder.button(text=cname, callback_data=f"sel_cat_{cid}")
    builder.adjust(2)
    await call.message.answer("Qaysi bo'limga qo'shamiz?", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("sel_cat_"))
async def set_prod_cat(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[2]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Mahsulot rasmini yuboring:")
    await state.set_state(AdminState.prod_photo)

@router.message(AdminState.prod_photo, F.photo)
async def set_prod_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("Mahsulot nomini kiriting:")
    await state.set_state(AdminState.prod_name)

@router.message(AdminState.prod_name)
async def set_prod_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Mahsulot o'lchamini kiriting:")
    await state.set_state(AdminState.prod_size)

@router.message(AdminState.prod_size)
async def set_prod_size(message: types.Message, state: FSMContext):
    await state.update_data(size=message.text)
    await message.answer("Nechta bor (soni)?")
    await state.set_state(AdminState.prod_qty)

@router.message(AdminState.prod_qty)
async def set_prod_qty(message: types.Message, state: FSMContext):
    await state.update_data(qty=message.text)
    await message.answer("Narxini kiriting:")
    await state.set_state(AdminState.prod_price)

@router.message(AdminState.prod_price)
async def set_prod_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    # Bazaga yozish
    cursor.execute("""
        INSERT INTO products (category_id, photo_id, name, size, quantity, price, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data['cat_id'], data['photo_id'], data['name'], data['size'], data['qty'], message.text, "Sifatli mebel"))
    conn.commit()
    await message.answer("✅ Mahsulot saqlandi!", reply_markup=admin_panel_kb())
    await state.clear()

# 5. Xabar yuborish (Broadcast)
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Foydalanuvchilarga yuboriladigan xabarni yuboring (Rasm, Video, Matn, Audio):")
    await state.set_state(AdminState.broadcast)

@router.message(AdminState.broadcast)
async def send_broadcast(message: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    await message.answer("Xabar yuborish boshlandi...")
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
        except:
            pass # Bloklagan bo'lsa o'tkazib yuboradi
    await message.answer(f"Xabar {count} ta foydalanuvchiga yuborildi.", reply_markup=admin_panel_kb())
    await state.clear()

# --- WEBHOOK CONFIG ---
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080)) # Render beradigan port
WEBHOOK_PATH = "/webhook"
BASE_WEBHOOK_URL = os.getenv("https://mebelbot.onrender.com") # Masalan: https://mebel-bot.onrender.com

async def on_startup(bot: Bot):
    db_start() # Bazani yaratish
    # Agar URL mavjud bo'lsa webhookni o'rnatamiz
    if BASE_WEBHOOK_URL:
        webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Webhook o'rnatildi: {webhook_url}")
    else:
        logging.error("WEBHOOK_URL topilmadi! Render Environment Variables ni tekshiring.")

def main():
    # Startup funksiyasini ro'yxatdan o'tkazish
    dp.startup.register(on_startup)

    # Web ilovani yaratish
    app = web.Application()
    
    # Asosiy sahifaga kirganda (Health Check uchun)
    async def handle_root(request):
        return web.Response(text="Bot ishlayapti!")
    
    app.router.add_get("/", handle_root)

    # Webhook handlerini sozlash
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Ilovani integratsiya qilish
    setup_application(app, dp, bot=bot)
    
    # Serverni ishga tushirish
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()