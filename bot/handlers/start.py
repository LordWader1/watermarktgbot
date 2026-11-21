"""Handlers for /start, /help, /setwatermark, and /cancel commands."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database import db
from bot.services.queue import job_queue
from bot.utils.decorators import check_user_access

WELCOME_TEXT = (
    "👋 **Welcome to the Video Watermark Bot!**\n\n"
    "I burn your custom text watermark directly into any video up to **2 GB** "
    "while preserving original resolution and audio quality.\n\n"
    "**Quick Start Guide:**\n"
    "1️⃣ Set your text: `/setwatermark MyChannel`\n"
    "2️⃣ Customize look & position: `/settings`\n"
    "3️⃣ Preview your style: `/preview`\n"
    "4️⃣ Send or forward any video (or video document)!\n\n"
    "**Available Commands:**\n"
    "• `/setwatermark <text>` — Save your custom watermark text\n"
    "• `/settings` — Configure position, size, color, opacity & scrolling\n"
    "• `/preview` — Generate a sample image of your watermark\n"
    "• `/cancel` — Abort your active or queued video job\n"
    "• `/help` — Show detailed usage tips"
)


def register_start_handlers(app: Client) -> None:
    """Register basic user command handlers."""

    @app.on_message(filters.command(["start", "help"]) & filters.private)
    @check_user_access
    async def start_handler(_: Client, message: Message) -> None:
        user_cfg = await db.get_user(message.from_user.id)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⚙️ Open Settings", callback_data="settings:open"),
                    InlineKeyboardButton("🖼 Preview Style", callback_data="settings:preview"),
                ]
            ]
        )
        await message.reply_text(
            f"{WELCOME_TEXT}\n\n"
            f"🏷 **Current Watermark:** `{user_cfg.watermark_text}`",
            reply_markup=keyboard,
            quote=True,
        )

    @app.on_message(filters.command("setwatermark") & filters.private)
    @check_user_access
    async def set_watermark_handler(_: Client, message: Message) -> None:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.reply_text(
                "⚠️ **Usage:** `/setwatermark Your Custom Text`\n"
                "Example: `/setwatermark @MyTelegramChannel`",
                quote=True,
            )
            return

        new_text = parts[1].strip()
        if len(new_text) > 80:
            await message.reply_text(
                "⚠️ Watermark text must be **80 characters or fewer**.",
                quote=True,
            )
            return

        updated = await db.update_user(message.from_user.id, watermark_text=new_text)
        await message.reply_text(
            f"✅ **Watermark text updated!**\n\n"
            f"**New Text:** `{updated.watermark_text}`\n"
            f"Use `/settings` to adjust position, color, or font size, or send a video now.",
            quote=True,
        )

    @app.on_message(filters.command("cancel") & filters.private)
    @check_user_access
    async def cancel_command_handler(_: Client, message: Message) -> None:
        cancelled_count = job_queue.cancel_user_jobs(message.from_user.id)
        if cancelled_count == 0:
            await message.reply_text("ℹ️ You have no active or queued jobs to cancel.", quote=True)
        else:
            await message.reply_text(
                f"🛑 Cancelled **{cancelled_count}** job(s) and cleaned up temporary files.",
                quote=True,
            )

    @app.on_callback_query(filters.regex(r"^cancel:([a-f0-9]+)$"))
    async def cancel_button_callback(_: Client, query: CallbackQuery) -> None:
        job_id = query.matches[0].group(1)
        success = job_queue.cancel_job_by_id(job_id, query.from_user.id)
        if success:
            await query.answer("🛑 Cancelling job...", show_alert=False)
        else:
            await query.answer("⚠️ Job is no longer active or not yours.", show_alert=True)
