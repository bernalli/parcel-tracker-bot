"""Single source of truth for the bot's roles.

The owner (``OWNER_ID``) is always an admin; ``ADMIN_USER_IDS`` adds more admins.
Every admin-only command and menu button checks :func:`is_admin`, so the inline
menu and the typed commands grant exactly the same rights.
"""

from __future__ import annotations

from typing import Any


def is_owner(config: Any, user_id: int) -> bool:
    return config is not None and getattr(config, "owner_id", None) == user_id


def is_admin(config: Any, user_id: int) -> bool:
    if config is None:
        return False
    if is_owner(config, user_id):
        return True
    admin_ids = getattr(config, "admin_user_ids", None) or ()
    try:
        return user_id in admin_ids
    except TypeError:
        return False
