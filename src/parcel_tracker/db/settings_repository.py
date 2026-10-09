"""Key/value settings: per-user preferences and process-wide generated values."""

from __future__ import annotations

import secrets

from parcel_tracker.db.migrations import get_connection

# Per-user setting keys. Values are stored as text.
SELLER_MODE = "seller_mode"
SHOP_NAME = "shop_name"

_TRUE = "1"
_FALSE = "0"


class SettingsRepository:
    """CRUD for ``user_settings`` and ``app_settings``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get_user(self, user_id: int, key: str) -> str | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
                (user_id, key),
            )
            row = await cursor.fetchone()
        return str(row["value"]) if row else None

    async def set_user(self, user_id: int, key: str, value: str | None) -> None:
        """Store a value; None (or an empty string) deletes the setting."""
        async with get_connection(self._db_path) as conn:
            if value is None or value == "":
                await conn.execute(
                    "DELETE FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key)
                )
            else:
                await conn.execute(
                    "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                    (user_id, key, value),
                )
            await conn.commit()

    async def seller_mode(self, user_id: int) -> bool:
        """True when the user ships parcels to customers rather than receiving them."""
        return await self.get_user(user_id, SELLER_MODE) == _TRUE

    async def set_seller_mode(self, user_id: int, enabled: bool) -> None:
        await self.set_user(user_id, SELLER_MODE, _TRUE if enabled else _FALSE)

    async def shop_name(self, user_id: int) -> str | None:
        return await self.get_user(user_id, SHOP_NAME)

    async def get_app(self, key: str) -> str | None:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
        return str(row["value"]) if row else None

    async def get_or_create_secret(self, key: str, *, nbytes: int = 32) -> str:
        """Return a random secret stored under ``key``, generating it on first use.

        INSERT OR IGNORE plus a re-read makes concurrent first calls agree on one value.
        """
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (key, secrets.token_urlsafe(nbytes)),
            )
            await conn.commit()
            cursor = await conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
        assert row is not None  # noqa: S101 — just inserted
        return str(row["value"])
