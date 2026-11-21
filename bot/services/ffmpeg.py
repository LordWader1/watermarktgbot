"""Async FFmpeg and FFprobe service with drawtext builder and progress parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Coroutine

from bot.config import settings
from bot.database.db import UserSettings
from bot.services.progress import CancelledError

logger = logging.getLogger(__name__)

PADDING = 24

POSITION_COORDS: dict[str, tuple[str, str]] = {
    "top-left": (f"{PADDING}", f"{PADDING}"),
    "top-right": (f"w-tw-{PADDING}", f"{PADDING}"),
    "bottom-left": (f"{PADDING}", f"h-th-{PADDING}"),
    "bottom-right": (f"w-tw-{PADDING}", f"h-th-{PADDING}"),
    "center": ("(w-tw)/2", "(h-th)/2"),
}


@dataclass
class VideoMetadata:
    """Extracted stream metadata from ffprobe."""

    duration: float = 0.0
    width: int = 0
    height: int = 0


def escape_drawtext(text: str) -> str:
    """
    Escape user text for safe inclusion inside an FFmpeg drawtext filter value.
    Handles backslashes, colons, single quotes, percent signs, and newlines.
    """
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace("\n", " ").replace("\r", "")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("%", r"\%")
    return escaped


def build_drawtext_filter(
    user_settings: UserSettings, font_path: str | None = None
) -> str:
    """Construct the FFmpeg drawtext filter string from a user's settings."""
    resolved_font = font_path if font_path is not None else settings.FONT_PATH
    safe_text = escape_drawtext(user_settings.watermark_text or "Watermark")
    opacity = max(0.1, min(1.0, float(user_settings.opacity)))
    font_size = max(10, min(120, int(user_settings.font_size)))
    color = user_settings.color if user_settings.color else "white"

    if user_settings.moving:
        # Smooth horizontal marquee across the video with vertical oscillation
        x_expr = "w-mod(t*90\\,w+tw)"
        y_expr = f"({PADDING})+(h-th-{PADDING * 2})*(0.5+0.4*sin(t*0.8))"
    else:
        x_expr, y_expr = POSITION_COORDS.get(
            user_settings.position, POSITION_COORDS["bottom-right"]
        )

    parts: list[str] = []
    if resolved_font and Path(resolved_font).exists():
        escaped_font = resolved_font.replace("\\", "/").replace(":", r"\:")
        parts.append(f"fontfile='{escaped_font}'")

    parts.extend(
        [
            f"text='{safe_text}'",
            f"fontsize={font_size}",
            f"fontcolor={color}@{opacity:.2f}",
            f"x={x_expr}",
            f"y={y_expr}",
            "shadowcolor=black@0.6",
            "shadowx=2",
            "shadowy=2",
        ]
    )
    return "drawtext=" + ":".join(parts)


def build_ffmpeg_cmd(
    input_path: Path | str,
    output_path: Path | str,
    user_settings: UserSettings,
    font_path: str | None = None,
) -> list[str]:
    """
    Build the full FFmpeg command list.
    Preserves original resolution, aspect ratio, and audio stream (-c:a copy)
    while encoding video with libx264 -preset veryfast.
    """
    vf_filter = build_drawtext_filter(user_settings, font_path=font_path)
    return [
        settings.FFMPEG_BINARY,
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]


async def probe_video(input_path: Path) -> VideoMetadata:
    """Run ffprobe asynchronously to inspect video duration and dimensions."""
    cmd = [
        settings.FFPROBE_BINARY,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=width,height,codec_type",
        "-of",
        "json",
        str(input_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return VideoMetadata()

        data = json.loads(stdout.decode("utf-8", errors="replace"))
        duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
        width, height = 0, 0
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0) or 0)
                height = int(stream.get("height", 0) or 0)
                break
        return VideoMetadata(duration=duration, width=width, height=height)
    except Exception as exc:
        logger.warning("ffprobe failed for %s: %s", input_path, exc)
        return VideoMetadata()


async def extract_thumbnail(
    input_path: Path, output_thumb: Path, timestamp: float = 1.0
) -> Path | None:
    """Extract a single JPEG frame from the video to use as the Telegram thumbnail."""
    cmd = [
        settings.FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, timestamp):.2f}",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-vf",
        "scale='min(320,iw)':-1",
        str(output_thumb),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=20)
        if output_thumb.exists() and output_thumb.stat().st_size > 0:
            return output_thumb
    except Exception as exc:
        logger.debug("Thumbnail extraction skipped: %s", exc)
    return None


async def generate_preview_image(
    output_image: Path, user_settings: UserSettings
) -> Path | None:
    """Generate a 1280x720 preview image showing the user's current watermark styling."""
    vf_filter = build_drawtext_filter(user_settings)
    cmd = [
        settings.FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1e293b:s=1280x720:d=1",
        "-vf",
        vf_filter,
        "-frames:v",
        "1",
        str(output_image),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
    if proc.returncode != 0 or not output_image.exists():
        logger.error("Preview generation failed: %s", stderr.decode(errors="replace"))
        return None
    return output_image


async def burn_watermark(
    input_path: Path,
    output_path: Path,
    user_settings: UserSettings,
    duration: float,
    progress_cb: Callable[[float, float], Coroutine[None, None, None]],
    cancel_event: asyncio.Event,
    register_process: Callable[[asyncio.subprocess.Process | None], None],
    retries: int = 1,
) -> None:
    """
    Execute FFmpeg asynchronously, parse real-time progress from stdout,
    and support instant process termination on cancellation.
    """
    cmd = build_ffmpeg_cmd(input_path, output_path, user_settings)
    attempt = 0

    while attempt <= retries:
        attempt += 1
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        register_process(proc)
        stderr_Task = asyncio.create_task(proc.stderr.read())  # type: ignore[union-attr]

        try:
            assert proc.stdout is not None
            while True:
                if cancel_event.is_set():
                    proc.terminate()
                    await proc.wait()
                    raise CancelledError("Job cancelled by user.")

                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    _, raw_val = line.split("=", 1)
                    if raw_val.isdigit():
                        # Both out_time_us and out_time_ms in FFmpeg progress are microseconds
                        processed_sec = int(raw_val) / 1_000_000.0
                        await progress_cb(processed_sec, duration)

            return_code = await proc.wait()
            stderr_output = (await stderr_Task).decode("utf-8", errors="replace")

            if cancel_event.is_set():
                raise CancelledError("Job cancelled by user.")

            if return_code == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return

            logger.error(
                "FFmpeg failed (attempt %d/%d, code %s): %s",
                attempt,
                retries + 1,
                return_code,
                stderr_output[-800:],
            )
            if attempt > retries:
                raise RuntimeError(
                    f"FFmpeg exited with code {return_code}. Details: {stderr_output[-300:]}"
                )
        finally:
            register_process(None)
