"""Throttled in-place progress updater for Pyrogram transfers and FFmpeg encoding."""

from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import Client
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.utils.helpers import humanbytes, render_progress_bar, time_formatter

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """Raised when a user explicitly cancels an active download, encode, or upload."""


class ProgressTracker:
    """Throttles message edits to avoid Telegram FloodWait during transfers."""

    def __init__(
        self,
        client: Client,
        status_message: Message,
        job_id: str,
        cancel_event: asyncio.Event,
    ) -> None:
        self.client = client
        self.status_message = status_message
        self.job_id = job_id
        self.cancel_event = cancel_event
        self.start_time = time.monotonic()
        self.last_edit_time = 0.0
        self._markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✖ Cancel Job", callback_data=f"cancel:{job_id}")]]
        )

    def reset_timer(self) -> None:
        """Reset phase start timer when transitioning from download to encode/upload."""
        self.start_time = time.monotonic()
        self.last_edit_time = 0.0

    async def pyrogram_callback(
        self, current: int, total: int, phase_title: str
    ) -> None:
        """Progress callback compatible with Pyrogram's download_media and send_video."""
        if self.cancel_event.is_set():
            self.client.stop_transmission()
            return

        now = time.monotonic()
        if (
            current < total
            and (now - self.last_edit_time) < settings.PROGRESS_UPDATE_INTERVAL
        ):
            return

        self.last_edit_time = now
        elapsed = max(0.1, now - self.start_time)
        speed = current / elapsed
        percentage = (current * 100.0 / total) if total > 0 else 0.0
        eta = ((total - current) / speed) if speed > 0 and total > current else 0.0

        text = (
            f"**{phase_title}**\n"
            f"`{render_progress_bar(percentage)} {percentage:.1f}%`\n\n"
            f"📦 **Size:** `{humanbytes(current)} / {humanbytes(total)}`\n"
            f"⚡ **Speed:** `{humanbytes(speed)}/s`\n"
            f"⏳ **ETA:** `{time_formatter(eta)}`\n"
            f"🆔 **Job ID:** `{self.job_id}`"
        )
        await self._safe_edit(text)

    async def update_ffmpeg_progress(
        self, processed_seconds: float, total_seconds: float
    ) -> None:
        """Update the status message with FFmpeg encoding progress."""
        if self.cancel_event.is_set():
            return

        now = time.monotonic()
        if (now - self.last_edit_time) < settings.PROGRESS_UPDATE_INTERVAL:
            return

        self.last_edit_time = now
        elapsed = max(0.1, now - self.start_time)
        percentage = (
            min(99.9, (processed_seconds * 100.0 / total_seconds))
            if total_seconds > 0
            else 0.0
        )
        rate = processed_seconds / elapsed if elapsed > 0 else 0.0
        eta = (
            (total_seconds - processed_seconds) / rate
            if rate > 0 and total_seconds > processed_seconds
            else 0.0
        )

        text = (
            "🎨 **Burning Watermark (FFmpeg)...**\n"
            f"`{render_progress_bar(percentage)} {percentage:.1f}%`\n\n"
            f"🎞 **Processed:** `{time_formatter(processed_seconds)} / {time_formatter(total_seconds)}`\n"
            f"🚀 **Speed:** `{rate:.2f}x`\n"
            f"⏳ **ETA:** `{time_formatter(eta)}`\n"
            f"🆔 **Job ID:** `{self.job_id}`"
        )
        await self._safe_edit(text)

    async def _safe_edit(self, text: str) -> None:
        """Edit the Telegram message while handling FloodWait and MessageNotModified."""
        try:
            await self.status_message.edit_text(text, reply_markup=self._markup)
        except MessageNotModified:
            pass
        except FloodWait as fw:
            logger.warning("FloodWait of %ss encountered during progress update.", fw.value)
            self.last_edit_time = time.monotonic() + float(fw.value)
        except Exception as exc:
            logger.debug("Ignored error during progress edit: %s", exc)
