"""Interactive inline settings panel and /preview generator."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database import db
from bot.database.db import (
    VALID_COLORS,
    VALID_FONT_SIZES,
    VALID_OPACITIES,
    VALID_POSITIONS,
    UserSettings,
)
from bot.services.ffmpeg import generate_preview_image
from bot.utils.decorators import check_user_access
from bot.utils.disk import cleanup_path, create_job_dir


def _cycle_next(options: tuple, current: object) -> object:
    """Return the next value in a tuple, cycling around to the first item."""
    try:
        idx = options.index(current)
        return options[(idx + 1) % len(options)]
    except ValueError:
        return options[0]


def build_settings_panel(cfg: UserSettings) -> tuple[str, InlineKeyboardMarkup]:
    """Build the settings caption and inline keyboard for a user."""
    mode_label = "🌀 Moving / Scrolling" if cfg.moving else "📌 Static"
    text = (
        "⚙️ **Watermark Customization Panel**\n\n"
        f"🏷 **Text:** `{cfg.watermark_text}`\n"
        f"📍 **Position:** `{cfg.position}`\n"
        f"🔠 **Font Size:** `{cfg.font_size}px`\n"
        f"🎨 **Color:** `{cfg.color}`\n"
        f"💧 **Opacity:** `{int(cfg.opacity * 100)}%`\n"
        f"🎞 **Mode:** `{mode_label}`\n\n"
        "_Tap any button below to cycle its setting, or use `/setwatermark <text>` to change the text._"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"📍 Position: {cfg.position}", callback_data="set:position"
                ),
                InlineKeyboardButton(
                    f"🔠 Size: {cfg.font_size}px", callback_data="set:font_size"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"🎨 Color: {cfg.color.capitalize()}", callback_data="set:color"
                ),
                InlineKeyboardButton(
                    f"💧 Opacity: {int(cfg.opacity * 100)}%", callback_data="set:opacity"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"🎞 Mode: {'Moving ON' if cfg.moving else 'Static'}",
                    callback_data="set:moving",
                )
            ],
            [
                InlineKeyboardButton("🖼 Generate Preview", callback_data="settings:preview"),
                InlineKeyboardButton("✖ Close", callback_data="settings:close"),
            ],
        ]
    )
    return text, keyboard


async def _send_preview(client: Client, user_id: int, chat_id: int, reply_to_id: int) -> None:
    """Render and send a sample 1280x720 preview frame with the user's settings."""
    user_cfg = await db.get_user(user_id)
    temp_dir = create_job_dir(user_id)
    preview_path = temp_dir / "preview.jpg"
    status = await client.send_message(
        chat_id, "🎨 Generating watermark preview...", reply_to_message_id=reply_to_id
    )
    try:
        result = await generate_preview_image(preview_path, user_cfg)
        if not result:
            await status.edit_text("❌ Failed to generate preview image.")
            return

        await client.send_photo(
            chat_id=chat_id,
            photo=str(result),
            caption=(
                f"🖼 **Watermark Preview** (1280×720)\n"
                f"• **Text:** `{user_cfg.watermark_text}`\n"
                f"• **Position:** `{user_cfg.position}` | **Size:** `{user_cfg.font_size}px`\n"
                f"• **Color:** `{user_cfg.color}@{user_cfg.opacity}` | **Moving:** `{user_cfg.moving}`"
            ),
            reply_to_message_id=reply_to_id,
        )
        await status.delete()
    finally:
        cleanup_path(temp_dir)


def register_settings_handlers(app: Client) -> None:
    """Register /settings, /preview, and customization callback queries."""

    @app.on_message(filters.command("settings") & filters.private)
    @check_user_access
    async def settings_command(_: Client, message: Message) -> None:
        cfg = await db.get_user(message.from_user.id)
        text, markup = build_settings_panel(cfg)
        await message.reply_text(text, reply_markup=markup, quote=True)

    @app.on_message(filters.command("preview") & filters.private)
    @check_user_access
    async def preview_command(client: Client, message: Message) -> None:
        await _send_preview(client, message.from_user.id, message.chat.id, message.id)

    @app.on_callback_query(filters.regex(r"^settings:(open|preview|close)$"))
    @check_user_access
    async def settings_navigation_cb(client: Client, query: CallbackQuery) -> None:
        action = query.matches[0].group(1)
        if action == "close":
            await query.message.delete()
            return

        if action == "open":
            cfg = await db.get_user(query.from_user.id)
            text, markup = build_settings_panel(cfg)
            try:
                await query.message.edit_text(text, reply_markup=markup)
            except MessageNotModified:
                pass
            await query.answer()
            return

        if action == "preview":
            await query.answer("Rendering preview...")
            await _send_preview(
                client, query.from_user.id, query.message.chat.id, query.message.id
            )

    @app.on_callback_query(filters.regex(r"^set:(position|font_size|color|opacity|moving)$"))
    @check_user_access
    async def settings_toggle_cb(_: Client, query: CallbackQuery) -> None:
        field_name = query.matches[0].group(1)
        user_id = query.from_user.id
        cfg = await db.get_user(user_id)

        if field_name == "position":
            new_val = _cycle_next(VALID_POSITIONS, cfg.position)
            cfg = await db.update_user(user_id, position=new_val)
        elif field_name == "font_size":
            new_val = _cycle_next(VALID_FONT_SIZES, cfg.font_size)
            cfg = await db.update_user(user_id, font_size=new_val)
        elif field_name == "color":
            new_val = _cycle_next(VALID_COLORS, cfg.color)
            cfg = await db.update_user(user_id, color=new_val)
        elif field_name == "opacity":
            new_val = _cycle_next(VALID_OPACITIES, cfg.opacity)
            cfg = await db.update_user(user_id, opacity=new_val)
        elif field_name == "moving":
            cfg = await db.update_user(user_id, moving=not cfg.moving)

        text, markup = build_settings_panel(cfg)
        try:
            await query.message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            pass
        await query.answer("Updated!")
