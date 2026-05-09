"""Bot UI message constants. English baseline; translated via gettext."""

from __future__ import annotations

from parcel_tracker.i18n import _


def welcome() -> str:
    return _(
        "📦 <b>Parcel Tracker Bot</b>\n\n"
        "Track your parcels automatically and get smart notifications.\n\n"
        "<b>Getting started:</b>\n"
        "• Send a tracking number to add it\n"
        "• Use <code>/add CODE [name] [carrier]</code>\n"
        "• Press /menu for the interactive menu"
    )


def help_text() -> str:
    return _(
        "<b>Available commands:</b>\n"
        "/add CODE [name] [carrier] - add a parcel\n"
        "/list - list active parcels\n"
        "/status CODE - parcel details\n"
        "/events CODE - event history\n"
        "/remove CODE - remove parcel\n"
        "/rename CODE NAME - rename parcel\n"
        "/checkall - refresh all parcels\n"
        "/menu - interactive menu\n"
        "/lang [code] - change language\n"
        "/help - this help"
    )


def unauthorized() -> str:
    return _("⛔ You are not authorised to use this bot.")


def owner_only() -> str:
    return _("⛔ Only the owner can use this command.")


def parcel_added(name: str) -> str:
    return _("✅ Parcel added: <b>{name}</b>").format(name=name)


def parcel_removed(tracking_number: str) -> str:
    return _("🗑 Parcel removed: <b>{tracking_number}</b>").format(tracking_number=tracking_number)


def parcel_not_found(tracking_number: str) -> str:
    return _("❌ Parcel <code>{tracking_number}</code> not found.").format(
        tracking_number=tracking_number
    )


def parcel_renamed(tracking_number: str, name: str) -> str:
    return _("✏️ Parcel <code>{tracking_number}</code> renamed to <b>{name}</b>.").format(
        tracking_number=tracking_number, name=name
    )


def no_parcels_active() -> str:
    return _("You have no active parcels. Add one with <code>/add</code>.")


def no_events(tracking_number: str) -> str:
    return _("No events for <code>{tracking_number}</code>.").format(
        tracking_number=tracking_number
    )


def add_usage() -> str:
    return _("Usage: <code>/add CODE [name] [carrier]</code>")


def remove_usage() -> str:
    return _("Usage: <code>/remove CODE</code>")


def rename_usage() -> str:
    return _("Usage: <code>/rename CODE NEW_NAME</code>")


def status_usage() -> str:
    return _("Usage: <code>/status CODE</code>")


def events_usage() -> str:
    return _("Usage: <code>/events CODE</code>")


def user_added(user_id: int) -> str:
    return _("✅ User <code>{user_id}</code> added.").format(user_id=user_id)


def user_removed(user_id: int) -> str:
    return _("🗑 User <code>{user_id}</code> removed.").format(user_id=user_id)


def user_duplicate(user_id: int) -> str:
    return _("⚠️ User <code>{user_id}</code> already present.").format(user_id=user_id)


def adduser_usage() -> str:
    return _("Usage: <code>/adduser USER_ID</code>")


def removeuser_usage() -> str:
    return _("Usage: <code>/removeuser USER_ID</code>")


def checkall_started() -> str:
    return _("🔄 Checking all parcels…")


def checkall_done() -> str:
    return _("✅ Check complete.")


def clean_done() -> str:
    return _("🧹 Cleanup complete.")


def cleanall_done() -> str:
    return _("🧹 All parcels removed.")


def stats_header() -> str:
    return _("<b>📊 Statistics</b>")


def map_placeholder() -> str:
    return _("🗺 Parcel map (coming soon)")


def lang_current(current: str, available: list[str]) -> str:
    return _("Current language: <code>{current}</code>\nAvailable: {available}").format(
        current=current, available=", ".join(available)
    )


def lang_changed(new: str) -> str:
    return _("Language switched to <code>{new}</code>.").format(new=new)


def lang_not_supported(requested: str, available: list[str]) -> str:
    return _("Language <code>{requested}</code> is not available. Try: {available}").format(
        requested=requested, available=", ".join(available)
    )


def menu_header() -> str:
    return _("Main menu:")


def no_users() -> str:
    return _("(no users)")


def no_delivered_parcels() -> str:
    return _("(no delivered parcels)")


def events_for(tracking_number: str) -> str:
    return _("<b>Events for <code>{tracking_number}</code></b>").format(
        tracking_number=tracking_number
    )


def to_add_use(text: str) -> str:
    return _("To add, use: <code>/add {text}</code>").format(text=text)


def carrier_label() -> str:
    return _("Carrier")


def authorised_users_count(count: int) -> str:
    return _("Authorised users: <b>{count}</b>").format(count=count)
