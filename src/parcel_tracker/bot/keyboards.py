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
            InlineKeyboardButton(_("📦 My parcels"), callback_data="nav:parcels"),
            InlineKeyboardButton(_("🗺 Maps"), callback_data="nav:maps"),
        ],
        [
            InlineKeyboardButton(_("⚙️ Settings"), callback_data="nav:settings"),
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
    """Settings submenu — language, notifications, whoami."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_("🌍 Language"), callback_data="action:lang"),
                InlineKeyboardButton(_("🔔 Notifications"), callback_data="action:notify"),
            ],
            [InlineKeyboardButton(_("🪴 Whoami"), callback_data="action:whoami")],
            _back_row(),
        ]
    )


def admin_submenu() -> InlineKeyboardMarkup:
    """Admin-only submenu — users, stats, cleanup."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("👥 Users"), callback_data="action:users")],
            [
                InlineKeyboardButton(_("📈 Stats"), callback_data="action:stats"),
                InlineKeyboardButton(_("📊 Tracker health"), callback_data="action:health"),
            ],
            [
                InlineKeyboardButton(_("📦 Delivered"), callback_data="action:delivered"),
                InlineKeyboardButton(_("🧹 Cleanup"), callback_data="nav:cleanup"),
            ],
            _back_row(),
        ]
    )


def cleanup_submenu() -> InlineKeyboardMarkup:
    """Cleanup submenu — clean delivered, remove all."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("🧹 Clean delivered"), callback_data="action:clean")],
            [InlineKeyboardButton(_("⚠️ Remove all"), callback_data="action:cleanall")],
            [InlineKeyboardButton(_("⬅️ Back"), callback_data="nav:admin")],
        ]
    )


def users_submenu() -> InlineKeyboardMarkup:
    """Users submenu — authorise, revoke."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_("➕ Authorise user"), callback_data="action:adduser")],
            [InlineKeyboardButton(_("🗑 Revoke user"), callback_data="action:revoke")],
            [InlineKeyboardButton(_("⬅️ Back"), callback_data="nav:admin")],
        ]
    )


_PICKER_LABEL_MAX = 32


def _picker_label(parcel: Parcel) -> str:
    """Human label for picker buttons: name first, tracking code as fallback."""
    label = parcel.name or parcel.tracking_number
    if len(label) > _PICKER_LABEL_MAX:
        return label[: _PICKER_LABEL_MAX - 1] + "…"
    return label


def parcel_picker_keyboard(
    parcels: list[Parcel],
    action: str,
    *,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard for picking a parcel (label = name or code), with given action prefix.

    ``extra_rows`` are appended as footer rows below the parcel list (e.g. a
    'Refresh all' action and a back row on the My-parcels view).
    """
    rows = [
        [
            InlineKeyboardButton(
                _picker_label(p), callback_data=f"parcel:{action}:{p.tracking_number}"
            )
        ]
        for p in parcels
    ]
    if not rows:
        rows = [[InlineKeyboardButton(_("(no parcels)"), callback_data="nav:main")]]
    if extra_rows:
        rows.extend(extra_rows)
    return InlineKeyboardMarkup(rows)


def name_prompt_keyboard(
    tracking_number: str, *, include_undo: bool = False
) -> InlineKeyboardMarkup:
    """Skip (+ optional Undo) shown under the post-add 'name this parcel' prompt."""
    row = [InlineKeyboardButton(_("⏭ Skip"), callback_data=f"parcel:skipname:{tracking_number}")]
    if include_undo:
        row.append(
            InlineKeyboardButton(_("↩️ Undo"), callback_data=f"confirm:undo:{tracking_number}")
        )
    return InlineKeyboardMarkup([row])


def parcel_actions_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    """Keyboard with actions for a single parcel."""
    tn = tracking_number
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_("🔄 Update now"), callback_data=f"parcel:refresh:{tn}"),
                InlineKeyboardButton(_("📋 Events"), callback_data=f"parcel:events:{tn}"),
            ],
            [
                InlineKeyboardButton(_("🗺 Map"), callback_data=f"parcel:map:{tn}"),
                InlineKeyboardButton(_("✏️ Rename"), callback_data=f"parcel:rename:{tn}"),
            ],
            [InlineKeyboardButton(_("🗑 Remove"), callback_data=f"parcel:remove:{tn}")],
            [InlineKeyboardButton(_("⬅️ Back"), callback_data="nav:parcels")],
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
