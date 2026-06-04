"""Inline keyboards for the bot UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from parcel_tracker.i18n import _

if TYPE_CHECKING:
    from parcel_tracker.db.models import Parcel


def _back_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(_("⬅️ Back"), callback_data="nav:main")]


def main_menu(*, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Top-level menu keyboard. Admin section visible only to admins."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(_("📦 Parcels"), callback_data="nav:parcels"),
            InlineKeyboardButton(_("⚙️ Settings"), callback_data="nav:settings"),
        ],
        [
            InlineKeyboardButton(_("🔧 Advanced"), callback_data="nav:advanced"),
            InlineKeyboardButton(_("ℹ️ Help"), callback_data="action:help"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(_("👮 Admin"), callback_data="nav:admin")])
    return InlineKeyboardMarkup(rows)


def parcels_submenu() -> InlineKeyboardMarkup:
    """Parcels submenu — list, add (prompt), history, refresh all."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("📋 Parcel list"), callback_data="action:list")],
            [InlineKeyboardButton(_("➕ Add parcel"), callback_data="prompt:add")],
            [InlineKeyboardButton(_("📦 History"), callback_data="action:history")],
            [InlineKeyboardButton(_("🔄 Refresh all"), callback_data="action:checkall")],
            _back_row(),
        ]
    )


def settings_submenu() -> InlineKeyboardMarkup:
    """Settings submenu — language, notifications."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_("🌍 Language"), callback_data="action:lang"),
                InlineKeyboardButton(_("🔔 Notifications"), callback_data="action:notify"),
            ],
            _back_row(),
        ]
    )


def advanced_submenu() -> InlineKeyboardMarkup:
    """Advanced submenu — health, map, parcel detail prompts."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_("📊 Tracker health"), callback_data="action:health"),
                InlineKeyboardButton(_("🗺 Map"), callback_data="action:map"),
            ],
            [
                InlineKeyboardButton(_("🔍 Parcel status"), callback_data="prompt:status"),
                InlineKeyboardButton(_("📋 Events"), callback_data="prompt:events"),
            ],
            [
                InlineKeyboardButton(_("✏️ Rename"), callback_data="prompt:rename"),
                InlineKeyboardButton(_("🗑 Remove"), callback_data="prompt:remove"),
            ],
            _back_row(),
        ]
    )


def admin_submenu() -> InlineKeyboardMarkup:
    """Admin-only submenu — users, stats, cleanup."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("👥 Users"), callback_data="action:users")],
            [InlineKeyboardButton(_("📈 Stats"), callback_data="action:stats")],
            [
                InlineKeyboardButton(_("📦 Delivered"), callback_data="action:delivered"),
                InlineKeyboardButton(_("🧹 Clean"), callback_data="action:clean"),
            ],
            _back_row(),
        ]
    )


def parcel_picker_keyboard(parcels: list[Parcel], action: str) -> InlineKeyboardMarkup:
    """Keyboard for picking a parcel by tracking_number, with given action prefix."""
    rows = [
        [
            InlineKeyboardButton(
                p.tracking_number, callback_data=f"parcel:{action}:{p.tracking_number}"
            )
        ]
        for p in parcels
    ]
    return InlineKeyboardMarkup(
        rows or [[InlineKeyboardButton(_("(no parcels)"), callback_data="nav:main")]]
    )


def parcel_actions_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    """Keyboard with actions for a single parcel."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _("🔄 Refresh"), callback_data=f"parcel:refresh:{tracking_number}"
                ),
                InlineKeyboardButton(
                    _("📋 Events"), callback_data=f"parcel:events:{tracking_number}"
                ),
            ],
            [InlineKeyboardButton(_("🗑 Remove"), callback_data=f"parcel:remove:{tracking_number}")],
        ]
    )


def delivery_confirm_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    """Yes/No keyboard shown when a parcel is detected as delivered."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _("✅ Yes, received"),
                    callback_data=f"confirm:yes:{tracking_number}",
                ),
                InlineKeyboardButton(
                    _("❌ Not yet"),
                    callback_data=f"confirm:no:{tracking_number}",
                ),
            ]
        ]
    )


def undo_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    """Undo button shown after an auto-added parcel."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _("↩️ Undo"),
                    callback_data=f"confirm:undo:{tracking_number}",
                )
            ]
        ]
    )
