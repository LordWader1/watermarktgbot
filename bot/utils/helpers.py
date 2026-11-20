"""Formatting, validation, and string sanitization helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path

from pyrogram.types import Message

ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".flv",
    ".m4v",
    ".mpeg",
    ".mpg",
    ".ts",
}


def humanbytes(size: int | float) -> str:
    """Format a byte count into a human-readable string."""
    if not size or size <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {units[i]}"


def time_formatter(seconds: float) -> str:
    """Format seconds into a compact human-readable duration."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def render_progress_bar(percentage: float, length: int = 12) -> str:
    """Build a visual Unicode progress bar for status messages."""
    clamped = max(0.0, min(100.0, percentage))
    filled = int(round(length * clamped / 100.0))
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}]"


def sanitize_filename(name: str) -> str:
    """Sanitize an arbitrary filename so it is safe on POSIX filesystems."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "video.mp4"


def extract_video_media(message: Message) -> tuple[object | None, str, int]:
    """
    Extract media object, safe filename, and file size from a Message.
    Returns (None, "", 0) if the message does not contain a valid video file.
    """
    if message.video:
        media = message.video
        raw_name = media.file_name or f"video_{media.file_unique_id}.mp4"
        ext = Path(raw_name).suffix.lower() or ".mp4"
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raw_name = f"{Path(raw_name).stem}.mp4"
        return media, sanitize_filename(raw_name), int(media.file_size or 0)

    if message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        raw_name = doc.file_name or f"video_{doc.file_unique_id}.mp4"
        ext = Path(raw_name).suffix.lower()
        if mime.startswith("video/") or ext in ALLOWED_VIDEO_EXTENSIONS:
            if ext not in ALLOWED_VIDEO_EXTENSIONS:
                raw_name = f"{raw_name}.mp4"
            return doc, sanitize_filename(raw_name), int(doc.file_size or 0)

    return None, "", 0
