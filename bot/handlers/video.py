"""Video and video-document submission handler and job processing pipeline."""

from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.database import db
from bot.services.ffmpeg import burn_watermark, extract_thumbnail, probe_video
from bot.services.progress import CancelledError, ProgressTracker
from bot.services.queue import VideoJob, job_queue
from bot.utils.decorators import check_user_access
from bot.utils.disk import cleanup_path, create_job_dir, has_sufficient_disk_space
from bot.utils.helpers import extract_video_media, humanbytes, time_formatter

logger = logging.getLogger(__name__)


async def _send_video_with_retry(
    client: Client,
    chat_id: int,
    video_path: str,
    caption: str,
    duration: int,
    width: int,
    height: int,
    thumb_path: str | None,
    reply_to_message_id: int,
    progress_cb,
) -> Message | None:
    """Upload the processed video while automatically respecting Telegram FloodWait."""
    for attempt in range(3):
        try:
            return await client.send_video(
                chat_id=chat_id,
                video=video_path,
                caption=caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path,
                supports_streaming=True,
                reply_to_message_id=reply_to_message_id,
                progress=progress_cb,
                progress_args=("📤 **Uploading Watermarked Video...**",),
            )
        except FloodWait as fw:
            logger.warning("FloodWait of %ss on send_video (attempt %d)", fw.value, attempt + 1)
            await asyncio.sleep(fw.value + 1)
    raise RuntimeError("Upload failed after multiple FloodWait retries.")


def register_video_handlers(app: Client) -> None:
    """Register the handler for incoming videos and video documents."""

    @app.on_message((filters.video | filters.document) & filters.private)
    @check_user_access
    async def handle_incoming_video(client: Client, message: Message) -> None:
        user_id = message.from_user.id
        media, safe_filename, file_size = extract_video_media(message)

        if media is None:
            await message.reply_text(
                "⚠️ **Unsupported file format.**\n"
                "Please send a valid video file (`.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`).",
                quote=True,
            )
            return

        if file_size <= 0 or file_size > settings.MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ **File too large!**\n"
                f"Maximum allowed size is `{humanbytes(settings.MAX_FILE_SIZE)}`, "
                f"but your file is `{humanbytes(file_size)}`.",
                quote=True,
            )
            return

        user_jobs = job_queue.get_user_jobs(user_id)
        if len(user_jobs) >= settings.MAX_USER_QUEUE:
            await message.reply_text(
                f"⏳ **Queue limit reached ({settings.MAX_USER_QUEUE} jobs).**\n"
                "Please wait for your current videos to finish or use `/cancel`.",
                quote=True,
            )
            return

        ok_disk, free_bytes, required_bytes = has_sufficient_disk_space(file_size)
        if not ok_disk:
            await message.reply_text(
                "⚠️ **Server disk is temporarily full.**\n\n"
                f"• **Required Free Space:** `{humanbytes(required_bytes)}`\n"
                f"• **Available Space:** `{humanbytes(free_bytes)}`\n\n"
                "Please wait a minute for active jobs to finish and try again.",
                quote=True,
            )
            return

        status_msg = await message.reply_text(
            "🕒 **Queued for processing...**", quote=True
        )

        async def process_job(job: VideoJob) -> None:
            job_start = time.monotonic()
            job.temp_dir = create_job_dir(job.user_id)
            input_path = job.temp_dir / f"in_{job.file_name}"
            output_path = job.temp_dir / f"watermarked_{job.file_name}.mp4"
            thumb_path = job.temp_dir / "thumb.jpg"

            tracker = ProgressTracker(
                client=client,
                status_message=job.status_message,
                job_id=job.job_id,
                cancel_event=job.cancel_event,
            )

            try:
                user_cfg = await db.get_user(job.user_id)

                # 1. Download via MTProto
                tracker.reset_timer()
                downloaded = await client.download_media(
                    job.source_message,
                    file_name=str(input_path),
                    progress=tracker.pyrogram_callback,
                    progress_args=("📥 **Downloading Video...**",),
                )
                if job.cancel_event.is_set() or not downloaded:
                    raise CancelledError("Download cancelled by user.")

                # 2. Probe metadata & burn watermark
                meta = await probe_video(input_path)
                tracker.reset_timer()
                await job.status_message.edit_text(
                    "🎨 **Starting FFmpeg watermark encode...**",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✖ Cancel Job", callback_data=f"cancel:{job.job_id}")]]
                    ),
                )

                await burn_watermark(
                    input_path=input_path,
                    output_path=output_path,
                    user_settings=user_cfg,
                    duration=meta.duration,
                    progress_cb=tracker.update_ffmpeg_progress,
                    cancel_event=job.cancel_event,
                    register_process=job.register_process,
                )

                # Free input file immediately to reclaim Heroku disk space before upload
                cleanup_path(input_path)

                # 3. Extract thumbnail & upload result
                extracted_thumb = await extract_thumbnail(
                    output_path, thumb_path, timestamp=min(2.0, meta.duration / 2.0)
                )
                tracker.reset_timer()
                total_elapsed = time_formatter(time.monotonic() - job_start)
                out_size = output_path.stat().st_size

                caption = (
                    f"✅ **Watermark Applied!**\n\n"
                    f"🏷 **Text:** `{user_cfg.watermark_text}`\n"
                    f"📦 **Size:** `{humanbytes(out_size)}`\n"
                    f"⏱ **Total Time:** `{total_elapsed}`"
                )

                sent_msg = await _send_video_with_retry(
                    client=client,
                    chat_id=job.chat_id,
                    video_path=str(output_path),
                    caption=caption,
                    duration=int(meta.duration),
                    width=meta.width,
                    height=meta.height,
                    thumb_path=str(extracted_thumb) if extracted_thumb else None,
                    reply_to_message_id=job.source_message.id,
                    progress_cb=tracker.pyrogram_callback,
                )

                if job.cancel_event.is_set() or sent_msg is None:
                    raise CancelledError("Upload cancelled by user.")

                await job.status_message.delete()

                if settings.LOG_CHANNEL:
                    try:
                        await client.send_message(
                            settings.LOG_CHANNEL,
                            f"✅ **Job `{job.job_id}` Completed**\n"
                            f"• **User:** `{job.user_id}`\n"
                            f"• **File:** `{job.file_name}` (`{humanbytes(job.file_size)}`)\n"
                            f"• **Watermark:** `{user_cfg.watermark_text}`\n"
                            f"• **Elapsed:** `{total_elapsed}`",
                        )
                    except Exception as log_exc:
                        logger.debug("Could not write to LOG_CHANNEL: %s", log_exc)

            except CancelledError:
                logger.info("Job %s cancelled by user %d", job.job_id, job.user_id)
                try:
                    await job.status_message.edit_text(
                        f"🛑 **Job `{job.job_id}` cancelled.** Temporary files deleted."
                    )
                except Exception:
                    pass
            except Exception as exc:
                logger.exception("Job %s failed for user %d: %s", job.job_id, job.user_id, exc)
                try:
                    await job.status_message.edit_text(
                        f"❌ **Processing Failed (`{job.job_id}`)**\n\n"
                        f"`{str(exc)[:300]}`"
                    )
                except Exception:
                    pass
            finally:
                cleanup_path(job.temp_dir)

        job = VideoJob(
            user_id=user_id,
            chat_id=message.chat.id,
            source_message=message,
            status_message=status_msg,
            file_name=safe_filename,
            file_size=file_size,
            processor=process_job,
        )
        position = await job_queue.enqueue(job)
        running, _ = job_queue.get_counts()

        if position > 1 or running > settings.MAX_CONCURRENT_JOBS:
            try:
                await status_msg.edit_text(
                    f"🕒 **Added to Queue (Position #{position})**\n"
                    f"🆔 **Job ID:** `{job.job_id}`\n"
                    f"📦 **File:** `{safe_filename}` (`{humanbytes(file_size)}`)",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✖ Cancel Job", callback_data=f"cancel:{job.job_id}")]]
                    ),
                )
            except Exception:
                pass
