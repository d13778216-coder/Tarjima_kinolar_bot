import asyncio
import logging
import json
import os
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

BOT_TOKEN = "8844718008:AAGjlgAwq5ACpQkdfpUTmzZ8cYCEWc71a_w"
ADMIN_ID  = 6953139141

# ═══════════════════════════════════════════════════


# ─── JSON Database (o'chib ketmaydi) ──────────────

DATA_FILE = "data.json"


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "movies": {},
        "channels": [
            {"username": "@Tarjima_top_kinolar", "name": "Tarjima Top Kinolar"}
        ]
    }


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Bot & Dispatcher ─────────────────────────────

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ─── States ───────────────────────────────────────

class AdminStates(StatesGroup):
    waiting_for_movie        = State()
    waiting_for_name         = State()
    waiting_for_code         = State()
    waiting_for_channel      = State()
    waiting_for_channel_name = State()

class UserStates(StatesGroup):
    waiting_for_code = State()


# ─── Keyboards ────────────────────────────────────

def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo'shish"),  KeyboardButton(text="📋 Kinolar ro'yxati")],
            [KeyboardButton(text="📢 Kanallar"),        KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True
    )


def channels_keyboard(data: dict) -> InlineKeyboardMarkup:
    buttons = []
    for ch in data["channels"]:
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {ch['name']}",
                callback_data=f"del_channel:{ch['username']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscription_keyboard(data: dict) -> InlineKeyboardMarkup:
    buttons = []
    for ch in data["channels"]:
        buttons.append([
            InlineKeyboardButton(
                text=f"➕ {ch['name']}",
                url=f"https://t.me/{ch['username'].lstrip('@')}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Helpers ──────────────────────────────────────

async def check_subscription(user_id: int, data: dict) -> bool:
    for ch in data["channels"]:
        try:
            member = await bot.get_chat_member(ch["username"], user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True


# ─── /start ───────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    data = load_data()

    if not await check_subscription(message.from_user.id, data):
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=subscription_keyboard(data)
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
    await message.answer("👑 Admin panel:", reply_markup=admin_reply_keyboard())


# ─── Obuna tekshirish ─────────────────────────────

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, state: FSMContext):
    data = load_data()
    if await check_subscription(call.from_user.id, data):
        await call.message.edit_text("✅ Obuna tasdiqlandi!\n\n🎬 Kino kodini kiriting:")
        await state.set_state(UserStates.waiting_for_code)
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)


# ─── Foydalanuvchi: kod kiritish ──────────────────

@dp.message(UserStates.waiting_for_code)
async def user_enter_code(message: Message):
    data  = load_data()
    code  = message.text.strip()
    movie = data["movies"].get(code)

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

    data["movies"][code]["views"] = movie.get("views", 0) + 1
    save_data(data)
    await message.answer("✅ Mana kino!\n\n🎬 Boshqa kino kodini kiriting:")


# ─── Admin: Kino qo'shish ─────────────────────────

@dp.message(F.text == "🎬 Kino qo'shish")
async def admin_add_movie_btn(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🎬 Kino faylini yuboring (video yoki dokument):")
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
    await message.answer("🎞 Kino nomini kiriting (masalan: Avatar 2):")
    await state.set_state(AdminStates.waiting_for_name)


@dp.message(AdminStates.waiting_for_name)
async def admin_set_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(name=message.text.strip())
    await message.answer("📦 Kino kodini kiriting (masalan: 001):")
    await state.set_state(AdminStates.waiting_for_code)


@dp.message(AdminStates.waiting_for_code)
async def admin_set_code(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    code = message.text.strip()
    data = load_data()

    if code in data["movies"]:
        await message.answer("⚠️ Bu kod allaqachon mavjud! Boshqa kod kiriting:")
        return

    d = await state.get_data()
    data["movies"][code] = {
        "file_id":   d["file_id"],
        "file_type": d["file_type"],
        "name":      d.get("name", ""),
        "caption":   d["caption"],
        "views":     0
    }
    save_data(data)
    await state.clear()
    await message.answer(
        f"✅ Kino qo'shildi!\n🎞 Nom: <b>{d.get('name', '-')}</b>\n📦 Kod: <code>{code}</code>",
        parse_mode="HTML",
        reply_markup=admin_reply_keyboard()
    )


# ─── Admin: Kinolar ro'yxati ──────────────────────

@dp.message(F.text == "📋 Kinolar ro'yxati")
async def admin_list_movies_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    data   = load_data()
    movies = data["movies"]
    if not movies:
        await message.answer("📭 Hozircha kino yo'q.")
        return
    text = "🎬 <b>Kinolar ro'yxati:</b>\n\n"
    for i, (code, m) in enumerate(movies.items(), 1):
        name = m.get("name") or "Nomsiz"
        text += f"{i}. 🎞 {name}\n    📦 Kod: <code>{code}</code> | 👁 {m.get('views', 0)} marta\n\n"
    await message.answer(text, parse_mode="HTML")


# ─── Admin: Kanallar ──────────────────────────────

@dp.message(F.text == "📢 Kanallar")
async def admin_channels_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    data = load_data()
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for ch in data["channels"]:
        text += f"• {ch['name']} ({ch['username']})\n"
    if not data["channels"]:
        text += "Hozircha kanal yo'q.\n"
    text += "\nO'chirish uchun kanal nomini bosing:"
    await message.answer(text, parse_mode="HTML", reply_markup=channels_keyboard(data))


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
async def admin_receive_channel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    username = message.text.strip()
    if not username.startswith("@"):
        username = "@" + username
    await state.update_data(ch_username=username)
    await message.answer(
        f"✅ Username: <code>{username}</code>\n\nEndi kanal nomini kiriting:\nMasalan: <b>Tarjima Kinolar</b>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_channel_name)


@dp.message(AdminStates.waiting_for_channel_name)
async def admin_receive_channel_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    d        = await state.get_data()
    username = d["ch_username"]
    name     = message.text.strip()
    data     = load_data()

    if any(ch["username"] == username for ch in data["channels"]):
        await message.answer(f"⚠️ <code>{username}</code> allaqachon mavjud!", parse_mode="HTML")
        await state.clear()
        return

    data["channels"].append({"username": username, "name": name})
    save_data(data)
    await state.clear()
    await message.answer(
        f"✅ Kanal qo'shildi!\n📢 <b>{name}</b> (<code>{username}</code>)",
        parse_mode="HTML",
        reply_markup=admin_reply_keyboard()
    )


@dp.callback_query(F.data.startswith("del_channel:"))
async def delete_channel(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    username = call.data.split(":", 1)[1]
    data     = load_data()
    data["channels"] = [ch for ch in data["channels"] if ch["username"] != username]
    save_data(data)
    await call.answer("✅ Kanal o'chirildi!")
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for ch in data["channels"]:
        text += f"• {ch['name']} ({ch['username']})\n"
    if not data["channels"]:
        text += "Hozircha kanal yo'q.\n"
    text += "\nO'chirish uchun kanal nomini bosing:"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=channels_keyboard(data))


@dp.callback_query(F.data == "back_admin")
async def back_admin(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await call.message.edit_text("👑 Admin panel:")


# ─── Admin: Statistika ────────────────────────────

@dp.message(F.text == "📊 Statistika")
async def admin_stats_btn(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    data        = load_data()
    movies      = data["movies"]
    total_views = sum(m.get("views", 0) for m in movies.values())
    text = (
        f"📊 <b>Statistika:</b>\n\n"
        f"🎬 Kinolar soni: <b>{len(movies)}</b>\n"
        f"👁 Umumiy ko'rishlar: <b>{total_views}</b>\n"
        f"📢 Kanallar soni: <b>{len(data['channels'])}</b>"
    )
    await message.answer(text, parse_mode="HTML")


# ─── Run ──────────────────────────────────────────

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
