"""Owner-only administration handlers: /stats, /broadcast, /ban, and /unban."""

from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from pyrogram.types import Message

from bot.config import settings
from bot.database import db
from bot.services.queue import job_queue
from bot.utils.disk import get_free_disk_bytes
from bot.utils.helpers import humanbytes, time_formatter

logger = logging.getLogger(__name__)
BOT_START_TIME = time.monotonic()


def register_admin_handlers(app: Client) -> None:
    """Register owner-only commands."""
    owner_filter = filters.user(settings.OWNER_ID) & filters.private

    @app.on_message(filters.command("stats") & owner_filter)
    async def stats_handler(_: Client, message: Message) -> None:
        total_users, banned_users = await db.get_stats()
        running_jobs, queued_jobs = job_queue.get_counts()
        free_disk = get_free_disk_bytes()
        uptime = time_formatter(time.monotonic() - BOT_START_TIME)

        await message.reply_text(
            "📊 **Bot System Statistics**\n\n"
            f"👥 **Total Users:** `{total_users}`\n"
            f"🚫 **Banned Users:** `{banned_users}`\n"
            f"⚙️ **Running Jobs:** `{running_jobs} / {settings.MAX_CONCURRENT_JOBS}`\n"
            f"🕒 **Queued Jobs:** `{queued_jobs}`\n"
            f"💾 **Free Disk Space:** `{humanbytes(free_disk)}`\n"
            f"⏱ **Uptime:** `{uptime}`",
            quote=True,
        )

    @app.on_message(filters.command("ban") & owner_filter)
    async def ban_handler(_: Client, message: Message) -> None:
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.reply_text("⚠️ **Usage:** `/ban <user_id>`", quote=True)
            return
        target_id = int(parts[1])
        await db.update_user(target_id, banned=True)
        job_queue.cancel_user_jobs(target_id)
        await message.reply_text(f"🚫 User `{target_id}` has been banned.", quote=True)

    @app.on_message(filters.command("unban") & owner_filter)
    async def unban_handler(_: Client, message: Message) -> None:
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.reply_text("⚠️ **Usage:** `/unban <user_id>`", quote=True)
            return
        target_id = int(parts[1])
        await db.update_user(target_id, banned=False)
        await message.reply_text(f"✅ User `{target_id}` has been unbanned.", quote=True)

    @app.on_message(filters.command("broadcast") & owner_filter)
    async def broadcast_handler(_: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.reply_text(
                "⚠️ Reply to any message with `/broadcast` to send it to all users.",
                quote=True,
            )
            return

        status = await message.reply_text("📣 **Starting broadcast...**", quote=True)
        sent = 0
        failed = 0

        async for uid in db.iter_user_ids():
            try:
                await message.reply_to_message.copy(chat_id=uid)
                sent += 1
                await asyncio.sleep(0.05)
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await message.reply_to_message.copy(chat_id=uid)
                    sent += 1
                except Exception:
                    failed += 1
            except (UserIsBlocked, InputUserDeactivated):
                failed += 1
            except Exception as exc:
                logger.debug("Broadcast error for %d: %s", uid, exc)
                failed += 1

        await status.edit_text(
            f"✅ **Broadcast Complete**\n\n"
            f"• **Delivered:** `{sent}`\n"
            f"• **Failed / Blocked:** `{failed}`"
        )
