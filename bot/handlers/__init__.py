"""Register all Pyrogram message and callback handlers."""

from __future__ import annotations

from pyrogram import Client

from bot.handlers.admin import register_admin_handlers
from bot.handlers.settings import register_settings_handlers
from bot.handlers.start import register_start_handlers
from bot.handlers.video import register_video_handlers


def register_all_handlers(app: Client) -> None:
    """Attach start, settings, admin, and video handlers to the client."""
    register_start_handlers(app)
    register_settings_handlers(app)
    register_admin_handlers(app)
    register_video_handlers(app)
