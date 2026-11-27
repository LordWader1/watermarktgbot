import asyncio
import logging
from pyrogram.types import Message
from bot.config import settings

logger = logging.getLogger(__name__)

def schedule_auto_delete(message: Message) -> None:
    """
    Schedules a Telegram message to be deleted in the background 
    after the time specified in Config (settings.AUTO_DELETE_TIME).
    """
    if settings.AUTO_DELETE_TIME <= 0:
        return

    async def _delete_task():
        try:
            await asyncio.sleep(settings.AUTO_DELETE_TIME)
            await message.delete()
            logger.info("Auto-deleted message %s", message.id)
        except Exception as e:
            logger.error("Failed to auto-delete message %s: %s", message.id, e)

    # Fire and forget: Runs in the background without blocking the queue
    asyncio.create_task(_delete_task())
