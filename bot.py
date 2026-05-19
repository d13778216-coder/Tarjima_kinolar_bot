import asyncio
import logging
import sqlite3
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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
                caption   TEXT    DEFAULT '',
                name      TEXT    DEFAULT '',
                views     INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    UNIQUE NOT NULL
            )
        """)
        try:
            self.conn.execute(
                "INSERT INTO channels (username) VALUES (?)",
                ("@Tarjima_top_kinolar",)
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass

    # ── Channels ───────────────────────────────────

    def get_channels(self) -> list:
        rows = self.conn.execute("SELECT username FROM channels").fetchall()
        return [r["username"] for r in rows]

    def add_channel(self, username: str) -> bool:
        try:
            self.conn.execute("INSERT INTO channels (username) VALUES (?)", (username,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_channel(self, username: str) -> bool:
        cur = self.conn.execute("DELETE FROM channels WHERE username = ?", (username,))
        self.conn.commit()
        return cur.rowcount > 0

    # ── Movies ─────────────────────────────────────

    def add_movie(self, code: str, file_id: str, file_type: str, name: str = "", caption: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT INTO movies (code, file_id, file_type, name, caption) VALUES (?, ?, ?, ?, ?)",
                (code, file_id, file_type, name, caption)
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

    def increment_views(self, code: str):
        self.conn.execute("UPDATE movies SET views = views + 1 WHERE code = ?", (code,))
        self.conn.commit()

    def get_all_movies(self) -> list:
        rows = self.conn.execute(
            "SELECT code, file_type, name, caption, views FROM movies ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


db = Database()


# ─── Bot & Dispatcher ─────────────────────────────

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ─── States ───────────────────────────────────────

class AdminStates(StatesGroup):
    waiting_for_movie   = State()
    waiting_for_name    = State()
    waiting_for_code    = State()
    waiting_for_channel = State()

class UserStates(StatesGroup):
    waiting_for_code = State()


# ─── Keyboards ────────────────────────────────────

def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Pastki menyu (□ belgisi yonida turadi)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo'shish"),   KeyboardButton(text="📋 Kinolar ro'yxati")],
            [KeyboardButton(text="📢 Kanallar"),         KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True
    )


def admin_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Kino qo'shish",       callback_data="admin_add_movie")],
        [InlineKeyboardButton(text="📋 Kinolar ro'yxati",    callback_data="admin_list_movies")],
        [InlineKeyboardButton(text="📢 Kanallar boshqaruvi", callback_data="admin_channels")],
        [InlineKeyboardButton(text="📊 Statistika",          callback_data="admin_stats")],
    ])


def channels_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for ch in db.get_channels():
        buttons.append([
            InlineKeyboardButton(text=f"❌ {ch}", callback_data=f"del_channel:{ch}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscription_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for channel in db.get_channels():
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


# ─── Helpers ──────────────────────────────────────

async def check_subscription(user_id: int) -> bool:
    for channel in db.get_channels():
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True


# ─── /start ───────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=subscription_keyboard()
        )
        return

    if user_id == ADMIN_ID:
        await message.answer(
            "👑 Xush kelibsiz, Admin!\nQuyidagi menyudan foydalaning:",
            reply_markup=admin_reply_keyboard()
        )
        return

    await message.answer(
        "🎬 Assalomu alaykum! Kino kodini kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(UserStates.waiting_for_code)


# ─── /admin ───────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q.")
        return
    await state.clear()
    await message.answer(
        "👑 Admin panel:",
        reply_markup=admin_reply_keyboard()
    )


# ─── Obuna tekshirish ─────────────────────────────

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    if await check_subscription(user_id):
        if user_id == ADMIN_ID:
            await call.message.edit_text("✅ Obuna tasdiqlandi!")
            await bot.send_message(
                user_id,
                "👑 Xush kelibsiz, Admin!",
                reply_markup=admin_reply_keyboard()
            )
        else:
            await call.message.edit_text("✅ Obuna tasdiqlandi!\n\n🎬 Kino kodini kiriting:")
            await state.set_state(UserStates.waiting_for_code)
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)


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

    db.increment_views(code)
    await message.answer("✅ Mana kino!\n\n🎬 Boshqa kino kodini kiriting:")


# ─── Admin reply keyboard handlerlari ────────────

@dp.message(F.text == "🎬 Kino qo'shish")
async def admin_add_movie_btn(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🎬 Kino faylini yuboring (video yoki dokument):")
    await state.set_state(AdminStates.waiting_for_movie)


@dp.message(F.text == "📋 Kinolar ro'yxati")
async def admin_list_movies_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    movies = db.get_all_movies()
    if not movies:
        await message.answer("📭 Hozircha kino yo'q.")
        return
    text = "🎬 <b>Kinolar ro'yxati:</b>\n\n"
    for i, m in enumerate(movies, 1):
        name = m['name'] if m['name'] else "Nomsiz"
        text += f"{i}. 🎞 {name}\n    📦 Kod: <code>{m['code']}</code> | 👁 {m['views']} marta\n\n"
    await message.answer(text, parse_mode="HTML")


@dp.message(F.text == "📢 Kanallar")
async def admin_channels_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    channels = db.get_channels()
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for ch in channels:
        text += f"• {ch}\n"
    if not channels:
        text += "Hozircha kanal yo'q.\n"
    text += "\nO'chirish uchun kanal nomini bosing:"
    await message.answer(text, parse_mode="HTML", reply_markup=channels_keyboard())


@dp.message(F.text == "📊 Statistika")
async def admin_stats_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    movies = db.get_all_movies()
    total_movies = len(movies)
    total_views  = sum(m['views'] for m in movies)
    channels     = db.get_channels()
    text = (
        f"📊 <b>Statistika:</b>\n\n"
        f"🎬 Kinolar soni: <b>{total_movies}</b>\n"
        f"👁 Umumiy ko'rishlar: <b>{total_views}</b>\n"
        f"📢 Kanallar soni: <b>{len(channels)}</b>"
    )
    await message.answer(text, parse_mode="HTML")


# ─── Admin: Kino qo'shish (inline) ───────────────

@dp.callback_query(F.data == "admin_add_movie")
async def admin_add_movie_inline(call: CallbackQuery, state: FSMContext):
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
    await message.answer("✅ Qabul qilindi!\n\n🎞 Kino nomini kiriting (masalan: Avatar 2):")
    await state.set_state(AdminStates.waiting_for_name)


@dp.message(AdminStates.waiting_for_name)
async def admin_set_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(name=message.text.strip())
    await message.answer("✅ Nom saqlandi!\n\n📦 Endi kino KODini kiriting (masalan: 001):")
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
    db.add_movie(code, data["file_id"], data["file_type"], data.get("name", ""), data["caption"])

    await state.clear()
    await message.answer(
        f"✅ Kino qo'shildi!\n🎞 Nom: <b>{data.get('name', '-')}</b>\n📦 Kod: <code>{code}</code>",
        parse_mode="HTML",
        reply_markup=admin_reply_keyboard()
    )


# ─── Admin: Kanallar (inline) ─────────────────────

@dp.callback_query(F.data == "admin_channels")
async def admin_channels_inline(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    channels = db.get_channels()
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for ch in channels:
        text += f"• {ch}\n"
    if not channels:
        text += "Hozircha kanal yo'q.\n"
    text += "\nO'chirish uchun kanal nomini bosing:"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=channels_keyboard())


@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📢 Kanal username ini kiriting:\n\nMasalan: <code>@mening_kanalim</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_channel)


@dp.message(AdminStates.waiting_for_channel)
async def admin_add_channel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    username = message.text.strip()
    if not username.startswith("@"):
        username = "@" + username

    if db.add_channel(username):
        await message.answer(
            f"✅ <code>{username}</code> kanali qo'shildi!",
            parse_mode="HTML",
            reply_markup=admin_reply_keyboard()
        )
    else:
        await message.answer(
            f"⚠️ <code>{username}</code> allaqachon mavjud!",
            parse_mode="HTML",
            reply_markup=admin_reply_keyboard()
        )
    await state.clear()


@dp.callback_query(F.data.startswith("del_channel:"))
async def delete_channel(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    username = call.data.split(":", 1)[1]
    db.delete_channel(username)
    await call.answer(f"✅ {username} o'chirildi!")
    channels = db.get_channels()
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for ch in channels:
        text += f"• {ch}\n"
    if not channels:
        text += "Hozircha kanal yo'q.\n"
    text += "\nO'chirish uchun kanal nomini bosing:"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=channels_keyboard())


# ─── Admin: Orqaga ────────────────────────────────

@dp.callback_query(F.data == "back_admin")
async def back_admin(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await call.message.edit_text("👑 Admin panel:", reply_markup=admin_inline_keyboard())


# ─── Admin: Statistika (inline) ───────────────────

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_inline(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    movies = db.get_all_movies()
    total_views = sum(m['views'] for m in movies)
    channels = db.get_channels()
    text = (
        f"📊 <b>Statistika:</b>\n\n"
        f"🎬 Kinolar soni: <b>{len(movies)}</b>\n"
        f"👁 Umumiy ko'rishlar: <b>{total_views}</b>\n"
        f"📢 Kanallar soni: <b>{len(channels)}</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())


# ─── Admin: Kinolar ro'yxati (inline) ────────────

@dp.callback_query(F.data == "admin_list_movies")
async def admin_list_movies_inline(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    movies = db.get_all_movies()
    if not movies:
        await call.message.edit_text("📭 Hozircha kino yo'q.", reply_markup=admin_inline_keyboard())
        return
    text = "🎬 <b>Kinolar ro'yxati:</b>\n\n"
    for i, m in enumerate(movies, 1):
        name = m['name'] if m['name'] else "Nomsiz"
        text += f"{i}. 🎞 {name}\n    📦 Kod: <code>{m['code']}</code> | 👁 {m['views']} marta\n\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())


# ─── Run ──────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
