"""Application entrypoint, lifecycle management, and graceful SIGTERM handling."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from pyrogram import Client

from bot.config import settings
from bot.database import db
from bot.handlers import register_all_handlers
from bot.services.queue import job_queue
from bot.utils.disk import init_temp_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def run_bot() -> None:
    """Initialize resources, start the MTProto client, and wait for termination."""
    settings.validate()
    init_temp_root()
    await db.connect()

    app = Client(
        name="watermark_bot",
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        bot_token=settings.BOT_TOKEN,
        workdir=str(settings.TEMP_DIR),
        max_concurrent_transmissions=settings.MAX_CONCURRENT_JOBS * 2,
    )

    register_all_handlers(app)
    stop_event = asyncio.Event()

    def _signal_handler(sig: signal.Signals) -> None:
        logger.warning("Received signal %s. Triggering graceful shutdown...", sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler, sig)
        except NotImplementedError:
            # Windows fallback where add_signal_handler is not supported
            signal.signal(sig, lambda s, f: stop_event.set())

    await app.start()
    me = await app.get_me()
    logger.info("Bot started as @%s (ID: %d)", me.username, me.id)
    job_queue.start_workers()

    await stop_event.wait()

    logger.info("Shutting down active jobs and client...")
    await job_queue.graceful_shutdown(app)
    await app.stop()
    await db.close()
    init_temp_root()
    logger.info("Shutdown complete.")


def main() -> None:
    """Synchronous entrypoint wrapper."""
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
