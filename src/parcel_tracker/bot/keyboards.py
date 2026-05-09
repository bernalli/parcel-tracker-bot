"""Inline keyboards for the bot UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from parcel_tracker.db.models import Parcel


def main_menu() -> InlineKeyboardMarkup:
    """Top-level menu keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 I miei pacchi", callback_data="list")],
            [
                InlineKeyboardButton("➕ Aggiungi", callback_data="add"),
                InlineKeyboardButton("🔄 Aggiorna tutti", callback_data="checkall"),
            ],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        ]
    )


def parcel_picker_keyboard(parcels: list[Parcel], action: str) -> InlineKeyboardMarkup:
    """Keyboard for picking a parcel by tracking_number, with given action prefix."""
    rows = [
        [InlineKeyboardButton(p.tracking_number, callback_data=f"{action}:{p.tracking_number}")]
        for p in parcels
    ]
    return InlineKeyboardMarkup(
        rows or [[InlineKeyboardButton("(nessun pacco)", callback_data="noop")]]
    )


def parcel_actions_keyboard(tracking_number: str) -> InlineKeyboardMarkup:
    """Keyboard with actions for a single parcel."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Aggiorna", callback_data=f"refresh:{tracking_number}"),
                InlineKeyboardButton("📋 Eventi", callback_data=f"events:{tracking_number}"),
            ],
            [InlineKeyboardButton("🗑 Rimuovi", callback_data=f"remove:{tracking_number}")],
        ]
    )
