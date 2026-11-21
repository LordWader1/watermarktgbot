"""Database package exposing the singleton database instance."""

from bot.database.db import Database, UserSettings, db

__all__ = ["Database", "UserSettings", "db"]
