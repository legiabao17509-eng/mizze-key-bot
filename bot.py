import os
import asyncio
import sqlite3
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Đọc cấu hình từ file .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# 🌐 Đường dẫn Mini App trên Vercel của bạn
WEBAPP_URL = "https://mizze-key-store-vn.vercel.app/" 

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

def init_db():
    with sqlite3.connect("keys.db") as conn:
        c = conn.cursor()
        
        # Bảng danh sách các gói (Miễn phí & Trả phí)
        c.execute('''CREATE TABLE IF NOT EXISTS key_prices (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        duration_hours INTEGER,
                        price_vnd INTEGER,
                        active BOOLEAN DEFAULT 1)''')
        
        # Bảng kho key nhập sẵn (chưa dùng)
        c.execute('''CREATE TABLE IF NOT EXISTS key_stock (
                        id INTEGER PRIMARY KEY,
                        key_code TEXT UNIQUE,
                        plan_id INTEGER,
                        is_used BOOLEAN DEFAULT 0)''')
        
        # Bảng lịch sử key đã cấp cho người chơi
        c.execute('''CREATE TABLE IF NOT EXISTS keys (
                        id INTEGER PRIMARY KEY,
                        key_code TEXT UNIQUE,
                        user_id INTEGER,
                        plan_id INTEGER,
                        expires_at TIMESTAMP)''')
        
        # Khởi tạo các gói chuẩn (Key 6 Giờ, Key 3 Giờ, v.v.)
        c.execute("INSERT OR REPLACE INTO key_prices (id, name, duration_hours, price_vnd) VALUES (1, 'Key 6 Giờ', 6, 0)")
        c.execute("INSERT OR REPLACE INTO key_prices (id, name, duration_hours, price_vnd) VALUES (2, 'Key 3 Giờ', 3, 0)")
        c.execute("INSERT OR REPLACE INTO key_prices (id, name, duration_hours, price_vnd) VALUES (3, 'Key 1 Ngày', 24, 20000)")
        c.execute("INSERT OR REPLACE INTO key_prices (id, name, duration_hours, price_vnd) VALUES (4, 'Key 7 Ngày', 168, 70000)")
        c.execute("INSERT OR REPLACE INTO key_prices (id, name, duration_hours, price_vnd) VALUES (5, 'Key 30 Ngày', 720, 150000)")
        conn.commit()

# Hàm lấy 1 key từ kho theo gói tương ứng
def get_key_from_stock(user_id, plan_name):
    with sqlite3.connect("keys.db") as conn:
        plan = conn.execute("SELECT id, name, duration_hours FROM key_prices WHERE name=?", (plan_name,)).fetchone()
        if not plan:
            return None, "Gói không tồn tại trong hệ thống."
        
        plan_id, name_p, duration_h = plan
        
        # Lấy 1 key chưa dùng trong kho ứng với gói đó
        stock_item = conn.execute("SELECT id, key_code FROM key_stock WHERE plan_id=? AND is_used=0 LIMIT 1", (plan_id,)).fetchone()
        
        if not stock_item:
            return None, f"⚠️ Kho key cho gói **{name_p}** hiện tại đã hết! Vui lòng báo Admin nạp thêm."
        
        stock_id, code = stock_item
        
        # Đánh dấu key đã được sử dụng
        conn.execute("UPDATE key_stock SET is_used=1 WHERE id=?", (stock_id,))
        
        # Lưu vào bảng lịch sử cấp key
        expires = datetime.now() + timedelta(hours=duration_h)
        conn.execute("INSERT INTO keys (key_code, user_id, plan_id, expires_at) VALUES (?, ?, ?, ?)", (code, user_id, plan_id, expires))
        conn.commit()
        
        return code, expires

# Lệnh /start mở Mini App
@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mở Mizze Store (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"👋 Chào {message.from_user.first_name}!\n"
        f"Chào mừng bạn đến với **Mizze Key Store**.\n\n"
        f"👇 Bấm nút bên dưới để mở cửa hàng cày link nhận Key tự động 24/7.",
        reply_markup=kb
    )

# 🤖 LẮNG NGHE TÍN HIỆU TỪ MINI APP KHI KHÁCH HOÀN THÀNH VƯỢT LINK
@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        if data.get("action") == "claim_free_key":
            plan_name = data.get("plan_name", "Key 6 Giờ")
            code, expires = get_key_from_stock(message.from_user.id, plan_name)
            
            if code:
                await message.answer(
                    f"🎉 **CHÚC MỪNG BẠN ĐÃ NHẬN KEY THÀNH CÔNG!**\n\n"
                    f"📦 Gói: **{plan_name}**\n"
                    f"🔑 Key của bạn: `{code}`\n"
                    f"⏳ Thời hạn đến: {expires.strftime('%d/%m/%Y %H:%M')}\n\n"
                    f"Cảm ơn bạn đã ủng hộ hệ thống!"
                )
            else:
                await message.answer(f"❌ {expires}")
    except Exception as e:
        await message.answer(f"❌ Lỗi xử lý dữ liệu: `{e}`")

# ================= QUẢN LÝ DÀNH CHO ADMIN =================

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID: return 
    
    with sqlite3.connect("keys.db") as conn:
        prices = conn.execute("SELECT id, name, duration_hours FROM key_prices WHERE active=1").fetchall()
        stock_counts = conn.execute("SELECT plan_id, COUNT(*) FROM key_stock WHERE is_used=0 GROUP BY plan_id").fetchall()
        stock_map = {row[0]: row[1] for row in stock_counts}

    text = "🛠 **BẢNG QUẢN LÝ KHO KEY (ADMIN)**\n\n**Tình trạng kho hiện tại:**\n"
    for p in prices:
        remaining = stock_map.get(p[0], 0)
        text += f"- ID `{p[0]}` ({p[1]}): **{remaining}** key chưa dùng\n"
    
    text += (
        "\n**Lệnh quản lý:**\n"
        "📥 Nạp key hàng loạt: `/addkey <ID_gói> <key1,key2,key3...>`\n"
        "🎁 Tặng key thủ công: `/givekey <user_id> <ID_gói>`"
    )
    await message.answer(text)

@dp.message(Command("addkey"))
async def cmd_addkey(message: Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split(maxsplit=2)
        pid = int(parts[1])
        keys_input = parts[2]
        
        key_list = [k.strip() for k in keys_input.replace("\n", ",").split(",") if k.strip()]
        
        added_count = 0
        with sqlite3.connect("keys.db") as conn:
            for k in key_list:
                try:
                    conn.execute("INSERT INTO key_stock (key_code, plan_id, is_used) VALUES (?, ?, 0)", (k, pid))
                    added_count += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
            
        await message.answer(f"✅ Đã nạp thành công **{added_count}** key vào kho cho gói ID `{pid}`!")
    except Exception as e:
        await message.answer(f"❌ Sai cú pháp!\nVD: `/addkey 1 KEY-111,KEY-222`\nLỗi: `{e}`")

@dp.message(Command("givekey"))
async def cmd_givekey(message: Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, uid, pid = message.text.split()
        with sqlite3.connect("keys.db") as conn:
            p_info = conn.execute("SELECT name FROM key_prices WHERE id=?", (int(pid),)).fetchone()
        if not p_info:
            await message.answer("❌ ID gói không tồn tại!")
            return
            
        code, expires = get_key_from_stock(int(uid), p_info[0])
        if not code:
            await message.answer(f"❌ {expires}")
            return
            
        await bot.send_message(
            int(uid),
            f"🎁 **BẠN ĐÃ NHẬN ĐƯỢC KEY TỪ ADMIN!**\n\n"
            f"🔑 Key: `{code}`\n"
            f"⏳ Hết hạn: {expires.strftime('%d/%m/%Y %H:%M')}"
        )
        await message.answer(f"✅ Đã trích xuất key `{code}` gửi cho user `{uid}` thành công!")
    except Exception as e:
        await message.answer(f"❌ Sai cú pháp! VD: `/givekey 123456789 1`\nLỗi: `{e}`")

async def main():
    init_db()
    print("🤖 Bot Telegram đang chạy mượt mà...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())