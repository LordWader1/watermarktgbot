"""Disk space checks and temporary directory management for Heroku's ephemeral filesystem."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)


def init_temp_root() -> None:
    """Purge any leftover temporary files on startup and recreate TEMP_DIR."""
    if settings.TEMP_DIR.exists():
        shutil.rmtree(settings.TEMP_DIR, ignore_errors=True)
        logger.info("Cleaned up leftover files in %s", settings.TEMP_DIR)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)


def create_job_dir(user_id: int) -> Path:
    """Create an isolated temporary directory for a single video job."""
    job_dir = settings.TEMP_DIR / f"job_{user_id}_{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def cleanup_path(path: Path | None) -> None:
    """Immediately remove a file or directory tree without raising errors."""
    if path is None:
        return
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to remove temp path %s: %s", path, exc)


def get_free_disk_bytes() -> int:
    """Return available disk space in bytes on the partition hosting TEMP_DIR."""
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(settings.TEMP_DIR)
    return int(usage.free)


def has_sufficient_disk_space(file_size_bytes: int) -> tuple[bool, int, int]:
    """
    Verify whether there is enough free disk space to store both the input
    and output video plus the configured safety buffer.

    Returns:
        (is_enough, free_bytes, required_bytes)
    """
    free_bytes = get_free_disk_bytes()
    safety_bytes = settings.MIN_FREE_DISK_MB * 1024 * 1024
    # Input video + output watermarked video + safety margin
    required_bytes = int(file_size_bytes * 2.15) + safety_bytes
    return free_bytes >= required_bytes, free_bytes, required_bytes
