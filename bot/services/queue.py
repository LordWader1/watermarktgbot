"""Bounded async job queue with per-user limits, cancellation, and SIGTERM notification."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Coroutine

from pyrogram import Client
from pyrogram.types import Message

from bot.config import settings
from bot.utils.disk import cleanup_path

logger = logging.getLogger(__name__)


@dataclass
class VideoJob:
    """Represents a single queued or active video watermarking job."""

    user_id: int
    chat_id: int
    source_message: Message
    status_message: Message
    file_name: str
    file_size: int
    processor: Callable[[VideoJob], Coroutine[None, None, None]]
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    ffmpeg_process: asyncio.subprocess.Process | None = None
    temp_dir: Path | None = None
    is_running: bool = False

    def register_process(self, proc: asyncio.subprocess.Process | None) -> None:
        """Bind or clear the active FFmpeg subprocess handle."""
        self.ffmpeg_process = proc

    def trigger_cancel(self) -> None:
        """Signal cancellation and terminate FFmpeg if currently encoding."""
        self.cancel_event.set()
        if self.ffmpeg_process and self.ffmpeg_process.returncode is None:
            try:
                self.ffmpeg_process.terminate()
            except ProcessLookupError:
                pass


class JobQueueManager:
    """Manages concurrent video processing workers and user job limits."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[VideoJob] = asyncio.Queue()
        self._jobs: dict[str, VideoJob] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._shutting_down: bool = False

    def start_workers(self) -> None:
        """Spawn the configured number of background worker tasks."""
        if self._workers:
            return
        for idx in range(settings.MAX_CONCURRENT_JOBS):
            task = asyncio.create_task(self._worker_loop(idx + 1), name=f"worker-{idx+1}")
            self._workers.append(task)
        logger.info("Started %d job queue worker(s).", settings.MAX_CONCURRENT_JOBS)

    def get_user_jobs(self, user_id: int) -> list[VideoJob]:
        """Return all queued or running jobs belonging to a user."""
        return [job for job in self._jobs.values() if job.user_id == user_id]

    def get_counts(self) -> tuple[int, int]:
        """Return (running_jobs_count, queued_jobs_count)."""
        running = sum(1 for j in self._jobs.values() if j.is_running)
        queued = len(self._jobs) - running
        return running, queued

    async def enqueue(self, job: VideoJob) -> int:
        """Add a job to the queue and return its 1-based queue position."""
        self._jobs[job.job_id] = job
        await self._queue.put(job)
        return self._queue.qsize()

    def cancel_job_by_id(self, job_id: str, user_id: int) -> bool:
        """Cancel a specific job if owned by user_id (or OWNER_ID)."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.user_id != user_id and user_id != settings.OWNER_ID:
            return False
        job.trigger_cancel()
        return True

    def cancel_user_jobs(self, user_id: int) -> int:
        """Cancel all queued and running jobs for a given user. Returns count cancelled."""
        user_jobs = self.get_user_jobs(user_id)
        for job in user_jobs:
            job.trigger_cancel()
        return len(user_jobs)

    async def _worker_loop(self, worker_id: int) -> None:
        """Continuously pull jobs from the queue and execute them."""
        while not self._shutting_down:
            job = await self._queue.get()
            try:
                if job.cancel_event.is_set():
                    try:
                        await job.status_message.edit_text("🛑 **Job cancelled before start.**")
                    except Exception:
                        pass
                    continue

                job.is_running = True
                logger.info(
                    "Worker #%d starting job %s for user %d",
                    worker_id,
                    job.job_id,
                    job.user_id,
                )
                await job.processor(job)
            except Exception as exc:
                logger.exception("Unhandled error in worker #%d for job %s: %s", worker_id, job.job_id, exc)
            finally:
                cleanup_path(job.temp_dir)
                self._jobs.pop(job.job_id, None)
                self._queue.task_done()

    async def graceful_shutdown(self, client: Client) -> None:
        """
        Handle Heroku SIGTERM by aborting active jobs, cleaning temp files,
        and notifying affected users that the server is restarting.
        """
        self._shutting_down = True
        active_jobs = list(self._jobs.values())
        logger.warning("Graceful shutdown initiated. Interrupting %d job(s).", len(active_jobs))

        for job in active_jobs:
            job.trigger_cancel()
            cleanup_path(job.temp_dir)
            try:
                await client.send_message(
                    chat_id=job.chat_id,
                    text=(
                        "⚠️ **Server Restart Notice**\n\n"
                        f"Your watermark job (`{job.job_id}`) was interrupted because the "
                        "dyno is restarting. Please resend your video in a moment."
                    ),
                    reply_to_message_id=job.source_message.id,
                )
            except Exception as exc:
                logger.debug("Could not notify user %d during shutdown: %s", job.user_id, exc)

        for task in self._workers:
            task.cancel()


job_queue = JobQueueManager()
