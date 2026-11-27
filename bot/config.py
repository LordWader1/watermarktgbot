"""Environment-based configuration for the Telegram Watermark Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _get_int(key: str, default: int = 0) -> int:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key} must be an integer, got '{val}'") from exc


@dataclass(frozen=True)
class Config:
    """Immutable application configuration loaded from environment variables."""

    API_ID: int = _get_int("API_ID", 0)
    API_HASH: str = os.getenv("API_HASH", "").strip()
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # Database: Uses Motor (MongoDB) if MONGO_URI is set; falls back to SQLite otherwise
    MONGO_URI: str = os.getenv("MONGO_URI", "").strip()
    DB_NAME: str = os.getenv("DB_NAME", "watermark_bot").strip()
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "watermark_bot.sqlite3").strip()

    # Administration & Channels
    OWNER_ID: int = _get_int("OWNER_ID", 0)
    LOG_CHANNEL: int = _get_int("LOG_CHANNEL", 0)
    FORCE_SUB_CHANNEL: str = os.getenv("FORCE_SUB_CHANNEL", "").strip()

    # Features & Cleanups
    # Time in seconds to delete processed videos from Telegram (e.g., 600 = 10 min, 1200 = 20 min). 0 disables auto-delete.
    AUTO_DELETE_TIME: int = _get_int("AUTO_DELETE_TIME", 600) 

    # Queue & Resource Limits
    MAX_CONCURRENT_JOBS: int = max(1, _get_int("MAX_CONCURRENT_JOBS", 1))
    MAX_USER_QUEUE: int = max(1, _get_int("MAX_USER_QUEUE", 2))
    MAX_FILE_SIZE: int = _get_int("MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024)  # 2 GiB
    MIN_FREE_DISK_MB: int = _get_int("MIN_FREE_DISK_MB", 250)
    PROGRESS_UPDATE_INTERVAL: float = float(os.getenv("PROGRESS_UPDATE_INTERVAL", "4.5"))

    # Paths & FFmpeg
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "/tmp/watermark_bot"))
    FONT_PATH: str = os.getenv(
        "FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ).strip()
    FFMPEG_BINARY: str = os.getenv("FFMPEG_BINARY", "ffmpeg").strip()
    FFPROBE_BINARY: str = os.getenv("FFPROBE_BINARY", "ffprobe").strip()

    def validate(self) -> None:
        """Validate critical environment variables before starting the bot."""
        missing = []
        if not self.API_ID:
            missing.append("API_ID")
        if not self.API_HASH:
            missing.append("API_HASH")
        if not self.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not self.OWNER_ID:
            missing.append("OWNER_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


settings = Config()
