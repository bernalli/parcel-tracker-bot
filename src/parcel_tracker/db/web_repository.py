"""Web dashboard persistence: one-time login links, sessions and API tokens.

Every secret handed to a browser or a script is random (``secrets``) and only its
SHA-256 digest is stored, so reading the database never yields a usable link,
session cookie or API token.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from parcel_tracker.db.migrations import get_connection
from parcel_tracker.db.repository import sql_ts

LOGIN_TOKEN_TTL = timedelta(minutes=15)
API_TOKEN_PREFIX = "ptb_"  # noqa: S105 — public prefix, not a secret
_MAX_API_TOKENS_PER_USER = 20


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WebSession:
    user_id: int
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ApiToken:
    id: int
    name: str
    created_at: str
    last_used_at: str | None


class WebRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # --- one-time login links ------------------------------------------------

    async def create_login_token(self, user_id: int, *, now: datetime | None = None) -> str:
        """Issue a single-use login token valid for LOGIN_TOKEN_TTL."""
        now = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        async with get_connection(self._db_path) as conn:
            # Expired links are garbage-collected whenever a new one is issued.
            await conn.execute("DELETE FROM web_login_tokens WHERE expires_at < ?", (sql_ts(now),))
            await conn.execute(
                "INSERT INTO web_login_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (digest(token), user_id, sql_ts(now + LOGIN_TOKEN_TTL)),
            )
            await conn.commit()
        return token

    async def consume_login_token(self, token: str, *, now: datetime | None = None) -> int | None:
        """Burn a login token and return its user, or None if unknown/expired/used."""
        now = now or datetime.now(UTC)
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM web_login_tokens WHERE token_hash = ? RETURNING user_id, expires_at",
                (digest(token),),
            )
            row = await cursor.fetchone()
            await conn.commit()
        if row is None or str(row["expires_at"]) < sql_ts(now):
            return None
        return int(row["user_id"])

    # --- sessions --------------------------------------------------------------

    async def create_session(
        self, user_id: int, *, lifetime: timedelta, now: datetime | None = None
    ) -> str:
        """Start a session and return the raw cookie value."""
        now = now or datetime.now(UTC)
        session_id = secrets.token_urlsafe(32)
        async with get_connection(self._db_path) as conn:
            await conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (sql_ts(now),))
            await conn.execute(
                "INSERT INTO web_sessions (session_hash, user_id, csrf_token, created_at, "
                "expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    digest(session_id),
                    user_id,
                    secrets.token_urlsafe(24),
                    sql_ts(now),
                    sql_ts(now + lifetime),
                    sql_ts(now),
                ),
            )
            await conn.commit()
        return session_id

    async def get_session(
        self, session_id: str, *, now: datetime | None = None
    ) -> WebSession | None:
        now = now or datetime.now(UTC)
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT user_id, csrf_token, expires_at FROM web_sessions WHERE session_hash = ?",
                (digest(session_id),),
            )
            row = await cursor.fetchone()
            if row is None or str(row["expires_at"]) < sql_ts(now):
                return None
            await conn.execute(
                "UPDATE web_sessions SET last_seen_at = ? WHERE session_hash = ?",
                (sql_ts(now), digest(session_id)),
            )
            await conn.commit()
        expires = datetime.strptime(str(row["expires_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        return WebSession(
            user_id=int(row["user_id"]), csrf_token=str(row["csrf_token"]), expires_at=expires
        )

    async def delete_session(self, session_id: str) -> None:
        async with get_connection(self._db_path) as conn:
            await conn.execute(
                "DELETE FROM web_sessions WHERE session_hash = ?", (digest(session_id),)
            )
            await conn.commit()

    async def delete_sessions_for_user(self, user_id: int) -> int:
        """Log a user out everywhere. Returns the number of sessions ended."""
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute("DELETE FROM web_sessions WHERE user_id = ?", (user_id,))
            await conn.commit()
            return int(cursor.rowcount or 0)

    # --- API tokens ------------------------------------------------------------

    async def create_api_token(self, user_id: int, name: str) -> str | None:
        """Create a token and return it (shown once). None when the user hit the cap."""
        token = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS n FROM api_tokens WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row is not None and int(row["n"]) >= _MAX_API_TOKENS_PER_USER:
                return None
            await conn.execute(
                "INSERT INTO api_tokens (token_hash, user_id, name) VALUES (?, ?, ?)",
                (digest(token), user_id, name),
            )
            await conn.commit()
        return token

    async def list_api_tokens(self, user_id: int) -> list[ApiToken]:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, name, created_at, last_used_at FROM api_tokens "
                "WHERE user_id = ? ORDER BY id",
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [
            ApiToken(
                id=int(r["id"]),
                name=str(r["name"]),
                created_at=str(r["created_at"]),
                last_used_at=str(r["last_used_at"]) if r["last_used_at"] else None,
            )
            for r in rows
        ]

    async def revoke_api_token(self, user_id: int, token_id: int) -> bool:
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM api_tokens WHERE id = ? AND user_id = ?", (token_id, user_id)
            )
            await conn.commit()
            return bool(cursor.rowcount)

    async def user_for_api_token(self, token: str, *, now: datetime | None = None) -> int | None:
        """Resolve a bearer token to its user and stamp last_used_at."""
        if not token.startswith(API_TOKEN_PREFIX):
            return None
        now = now or datetime.now(UTC)
        async with get_connection(self._db_path) as conn:
            cursor = await conn.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE token_hash = ? RETURNING user_id",
                (sql_ts(now), digest(token)),
            )
            row = await cursor.fetchone()
            await conn.commit()
        return int(row["user_id"]) if row else None
