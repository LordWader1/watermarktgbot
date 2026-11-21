"""Async database abstraction supporting MongoDB (Motor) with an aiosqlite fallback."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator

import aiosqlite
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from bot.config import settings

logger = logging.getLogger(__name__)

VALID_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
VALID_COLORS = ("white", "yellow", "red", "cyan", "green", "black")
VALID_FONT_SIZES = (18, 24, 32, 48, 64)
VALID_OPACITIES = (0.3, 0.5, 0.75, 1.0)


@dataclass
class UserSettings:
    """Per-user watermark and account state."""

    user_id: int
    watermark_text: str = "Sample Watermark"
    position: str = "bottom-right"
    font_size: int = 28
    color: str = "white"
    opacity: float = 0.75
    moving: bool = False
    banned: bool = False
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["created_at"]:
            data["created_at"] = time.time()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserSettings:
        return cls(
            user_id=int(data["user_id"]),
            watermark_text=str(data.get("watermark_text", "Sample Watermark")),
            position=str(data.get("position", "bottom-right")),
            font_size=int(data.get("font_size", 28)),
            color=str(data.get("color", "white")),
            opacity=float(data.get("opacity", 0.75)),
            moving=bool(data.get("moving", False)),
            banned=bool(data.get("banned", False)),
            created_at=float(data.get("created_at", time.time())),
        )


class Database:
    """Unified async repository using Motor when MONGO_URI is set, else SQLite."""

    def __init__(self) -> None:
        self._mongo_client: AsyncIOMotorClient | None = None
        self._mongo_db: AsyncIOMotorDatabase | None = None
        self._sqlite_conn: aiosqlite.Connection | None = None
        self._using_mongo: bool = bool(settings.MONGO_URI)

    async def connect(self) -> None:
        """Initialize the underlying database connection and indexes."""
        if self._using_mongo:
            logger.info("Connecting to MongoDB...")
            self._mongo_client = AsyncIOMotorClient(
                settings.MONGO_URI, serverSelectionTimeoutMS=5000
            )
            self._mongo_db = self._mongo_client[settings.DB_NAME]
            await self._mongo_db.users.create_index("user_id", unique=True)
            logger.info("Connected to MongoDB database '%s'.", settings.DB_NAME)
        else:
            logger.warning(
                "MONGO_URI not set. Falling back to local SQLite at '%s'.",
                settings.SQLITE_PATH,
            )
            self._sqlite_conn = await aiosqlite.connect(settings.SQLITE_PATH)
            await self._sqlite_conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            await self._sqlite_conn.commit()

    async def close(self) -> None:
        """Close open database connections cleanly."""
        if self._mongo_client is not None:
            self._mongo_client.close()
            logger.info("Closed MongoDB connection.")
        if self._sqlite_conn is not None:
            await self._sqlite_conn.close()
            logger.info("Closed SQLite connection.")

    async def get_user(self, user_id: int) -> UserSettings:
        """Fetch user settings or create default settings if the user is new."""
        if self._using_mongo and self._mongo_db is not None:
            doc = await self._mongo_db.users.find_one({"user_id": user_id})
            if doc:
                return UserSettings.from_dict(doc)
            user = UserSettings(user_id=user_id, created_at=time.time())
            await self._mongo_db.users.insert_one(user.to_dict())
            return user

        assert self._sqlite_conn is not None
        async with self._sqlite_conn.execute(
            "SELECT payload FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return UserSettings.from_dict(json.loads(row[0]))

        user = UserSettings(user_id=user_id, created_at=time.time())
        await self._sqlite_conn.execute(
            "INSERT INTO users (user_id, payload) VALUES (?, ?)",
            (user_id, json.dumps(user.to_dict())),
        )
        await self._sqlite_conn.commit()
        return user

    async def update_user(self, user_id: int, **updates: Any) -> UserSettings:
        """Update specific fields for a user and return the updated UserSettings."""
        user = await self.get_user(user_id)
        data = user.to_dict()
        data.update(updates)
        updated = UserSettings.from_dict(data)

        if self._using_mongo and self._mongo_db is not None:
            await self._mongo_db.users.update_one(
                {"user_id": user_id}, {"$set": updated.to_dict()}, upsert=True
            )
            return updated

        assert self._sqlite_conn is not None
        await self._sqlite_conn.execute(
            "INSERT OR REPLACE INTO users (user_id, payload) VALUES (?, ?)",
            (user_id, json.dumps(updated.to_dict())),
        )
        await self._sqlite_conn.commit()
        return updated

    async def get_stats(self) -> tuple[int, int]:
        """Return (total_users, banned_users)."""
        if self._using_mongo and self._mongo_db is not None:
            total = await self._mongo_db.users.count_documents({})
            banned = await self._mongo_db.users.count_documents({"banned": True})
            return total, banned

        assert self._sqlite_conn is not None
        total = 0
        banned = 0
        async with self._sqlite_conn.execute("SELECT payload FROM users") as cursor:
            async for (payload_str,) in cursor:
                total += 1
                if json.loads(payload_str).get("banned"):
                    banned += 1
        return total, banned

    async def iter_user_ids(self) -> AsyncIterator[int]:
        """Yield all registered user IDs for broadcasting."""
        if self._using_mongo and self._mongo_db is not None:
            async for doc in self._mongo_db.users.find({}, {"user_id": 1}):
                yield int(doc["user_id"])
            return

        assert self._sqlite_conn is not None
        async with self._sqlite_conn.execute("SELECT user_id FROM users") as cursor:
            async for (uid,) in cursor:
                yield int(uid)


db = Database()
