import asyncio
import logging
import sqlite3
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

# ═══════════════════════════════════════════════════
#   ⚙️  CONFIG
# ═══════════════════════════════════════════════════

BOT_TOKEN = "8680594111:AAHUMV6toDVKWYrGTiZhKX-qvLTPdsfye7o"
ADMIN_ID  = 6953139141
CHANNELS  = [
    "@Tarjima_top_kinolar",
]

# ═══════════════════════════════════════════════════


# ─── Database ─────────────────────────────────────

DB_PATH = "movies.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                code      TEXT    UNIQUE NOT NULL,
                file_id   TEXT    NOT NULL,
                file_type TEXT    NOT NULL,
                caption   TEXT    DEFAULT ''
            )
        """)
        self.conn.commit()

    def add_movie(self, code: str, file_id: str, file_type: str, caption: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT INTO movies (code, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
                (code, file_id, file_type, caption)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_movie(self, code: str) -> bool:
        cur = self.conn.execute("DELETE FROM movies WHERE code = ?", (code,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_movie_by_code(self, code: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM movies WHERE code = ?", (code,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_movies(self) -> list:
        rows = self.conn.execute(
            "SELECT code, file_type, caption FROM movies ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


db = Database()


# ─── Bot & Dispatcher ─────────────────────────────

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ─── States ───────────────────────────────────────

class AdminStates(StatesGroup):
    waiting_for_movie = State()
    waiting_for_code  = State()

class UserStates(StatesGroup):
    waiting_for_code = State()


# ─── Helpers ──────────────────────────────────────

async def check_subscription(user_id: int) -> bool:
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True


def subscription_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for channel in CHANNELS:
        buttons.append([
            InlineKeyboardButton(
                text=f"➕ {channel}",
                url=f"https://t.me/{channel.lstrip('@')}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Kino qo'shish",    callback_data="admin_add_movie")],
        [InlineKeyboardButton(text="📋 Kinolar ro'yxati", callback_data="admin_list_movies")],
    ])


# ─── /start ───────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        await message.answer("👑 Xush kelibsiz, Admin!", reply_markup=admin_keyboard())
        return

    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
            reply_markup=subscription_keyboard()
        )
        return

    await message.answer("🎬 Kino kodini kiriting:")
    await state.set_state(UserStates.waiting_for_code)


# ─── Obuna tekshirish ─────────────────────────────

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, state: FSMContext):
    if await check_subscription(call.from_user.id):
        await call.message.edit_text("✅ Obuna tasdiqlandi!\n\n🎬 Kino kodini kiriting:")
        await state.set_state(UserStates.waiting_for_code)
    else:
        await call.answer("❌ Hali kanalga obuna bo'lmadingiz!", show_alert=True)


# ─── Foydalanuvchi: kod kiritish ──────────────────

@dp.message(UserStates.waiting_for_code)
async def user_enter_code(message: Message):
    code  = message.text.strip()
    movie = db.get_movie_by_code(code)

    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi. Qaytadan kiriting:")
        return

    caption = movie.get("caption", "")
    try:
        if movie["file_type"] == "video":
            await bot.send_video(message.chat.id, movie["file_id"], caption=caption)
        else:
            await bot.send_document(message.chat.id, movie["file_id"], caption=caption)
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
        return

    await message.answer("✅ Mana kino!\n\n🎬 Boshqa kino kodini kiriting:")


# ─── Admin: Kino qo'shish ─────────────────────────

@dp.callback_query(F.data == "admin_add_movie")
async def admin_add_movie(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🎬 Kino faylini yuboring (video yoki dokument):")
    await state.set_state(AdminStates.waiting_for_movie)


@dp.message(AdminStates.waiting_for_movie)
async def admin_receive_movie(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.document:
        file_id, file_type = message.document.file_id, "document"
    else:
        await message.answer("❌ Iltimos, video yoki dokument yuboring.")
        return

    await state.update_data(file_id=file_id, file_type=file_type, caption=message.caption or "")
    await message.answer("✅ Qabul qilindi!\n\nEndi kinoga KOD kiriting (masalan: 001):")
    await state.set_state(AdminStates.waiting_for_code)


@dp.message(AdminStates.waiting_for_code)
async def admin_set_code(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    code = message.text.strip()

    if db.get_movie_by_code(code):
        await message.answer("⚠️ Bu kod allaqachon mavjud! Boshqa kod kiriting:")
        return

    data = await state.get_data()
    db.add_movie(code, data["file_id"], data["file_type"], data["caption"])

    await state.clear()
    await message.answer(
        f"✅ Kino qo'shildi!\n📦 Kod: <code>{code}</code>",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# ─── Admin: Kinolar ro'yxati ──────────────────────

@dp.callback_query(F.data == "admin_list_movies")
async def admin_list_movies(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    movies = db.get_all_movies()
    if not movies:
        await call.message.edit_text("📭 Hozircha kino yo'q.", reply_markup=admin_keyboard())
        return

    text = "🎬 <b>Kinolar ro'yxati:</b>\n\n"
    for i, m in enumerate(movies, 1):
        text += f"{i}. Kod: <code>{m['code']}</code> — {m['file_type']}\n"

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_keyboard())


# ─── /panel (admin buyrug'i) ──────────────────────

@dp.message(Command("panel"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q.")
        return
    await state.clear()
    await message.answer("👑 Admin panel:", reply_markup=admin_keyboard())


# ─── Run ──────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
