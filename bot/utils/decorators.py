"""Access-control decorators for ban checks and optional Force-Subscribe verification."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Coroutine

from pyrogram import Client
from pyrogram.errors import UserNotParticipant
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import settings
from bot.database import db

logger = logging.getLogger(__name__)


def check_user_access(
    func: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Verify the user is not banned and satisfies Force-Subscribe if configured."""

    @functools.wraps(func)
    async def wrapper(
        client: Client, update: Message | CallbackQuery, *args: Any, **kwargs: Any
    ) -> Any:
        user = update.from_user
        if not user:
            return None

        user_settings = await db.get_user(user.id)
        if user_settings.banned and user.id != settings.OWNER_ID:
            text = "🚫 You are banned from using this bot."
            if isinstance(update, CallbackQuery):
                await update.answer(text, show_alert=True)
            else:
                await update.reply_text(text, quote=True)
            return None

        if settings.FORCE_SUB_CHANNEL and user.id != settings.OWNER_ID:
            channel = settings.FORCE_SUB_CHANNEL
            try:
                member = await client.get_chat_member(channel, user.id)
                if member.status.name in ("LEFT", "BANNED"):
                    raise UserNotParticipant
            except UserNotParticipant:
                invite_link = (
                    f"https://t.me/{channel.lstrip('@')}"
                    if channel.startswith("@")
                    else None
                )
                if not invite_link:
                    try:
                        chat = await client.get_chat(channel)
                        invite_link = chat.invite_link or await client.export_chat_invite_link(
                            channel
                        )
                    except Exception as exc:
                        logger.warning("Could not fetch invite link for %s: %s", channel, exc)

                buttons = []
                if invite_link:
                    buttons.append(
                        [InlineKeyboardButton("📢 Join Channel", url=invite_link)]
                    )
                markup = InlineKeyboardMarkup(buttons) if buttons else None
                msg = "⚠️ Please join our updates channel to use this bot, then try again."
                if isinstance(update, CallbackQuery):
                    await update.answer(msg, show_alert=True)
                else:
                    await update.reply_text(msg, reply_markup=markup, quote=True)
                return None
            except Exception as exc:
                logger.error("Force-sub check error for %s: %s", channel, exc)

        return await func(client, update, *args, **kwargs)

    return wrapper
