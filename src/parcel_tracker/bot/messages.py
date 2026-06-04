"""Bot UI message constants. English baseline; translated via gettext."""

from __future__ import annotations

import html

from parcel_tracker.i18n import _


def esc(value: object) -> str:
    """HTML-escape an untrusted value for safe interpolation into parse_mode='HTML' text."""
    return html.escape(str(value), quote=False) if value is not None else ""


def welcome() -> str:
    return _(
        "📦 <b>Parcel Tracker Bot</b>\n\n"
        "Track your parcels and get smart notifications with maps.\n\n"
        "<b>Quick start:</b>\n"
        "• Just send a tracking number to start tracking it\n"
        "• Press /menu for everything else (buttons)"
    )


def help_text() -> str:
    return _(
        "📦 <b>Parcel Tracker Bot</b>\n\n"
        "• Send a tracking number → I track it automatically\n"
        "• /menu — buttons for list, status, events, map, settings\n"
        "• /list — your active parcels\n"
        "• /help — this message"
    )


def unauthorized() -> str:
    return _("⛔ You are not authorised to use this bot.")


def owner_only() -> str:
    return _("⛔ Only the owner can use this command.")


def parcel_added(name: str) -> str:
    return _("✅ Parcel added: <b>{name}</b>").format(name=name)


def parcel_duplicate(tracking_number: str) -> str:
    return _("⚠️ Parcel <code>{tracking_number}</code> is already tracked.").format(
        tracking_number=tracking_number
    )


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


def checkall_done_count(n: int) -> str:
    return _("✅ Checked {n} parcel(s).").format(n=n)


def clean_done() -> str:
    return _("🧹 Cleanup complete.")


def cleanall_done() -> str:
    return _("🧹 All parcels removed.")


def stats_header() -> str:
    return _("<b>📊 Statistics</b>")


def map_placeholder() -> str:
    return _("🗺 Parcel map (coming soon)")


def map_usage() -> str:
    return _("Usage: <code>/map CODE</code>")


def map_no_position(tracking_number: str) -> str:
    return _("🗺 No mappable position yet for <code>{tracking_number}</code>.").format(
        tracking_number=esc(tracking_number)
    )


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


def menu_section_parcels() -> str:
    return _("📦 <b>Parcels</b>")


def menu_section_settings() -> str:
    return _("⚙️ <b>Settings</b>")


def menu_section_advanced() -> str:
    return _("🔧 <b>Advanced</b>")


def menu_section_admin() -> str:
    return _("👮 <b>Admin</b>")


def prompt_add() -> str:
    return _(
        "➕ <b>Add a parcel</b>\n\n"
        "Send a message in this format:\n"
        "<code>/add CODE [name] [carrier]</code>\n\n"
        "Examples:\n"
        "• <code>/add 1Z999AA10123456784</code>\n"
        "• <code>/add 1Z999AA10123456784 my package</code>\n"
        "• <code>/add 1Z999AA10123456784 my package ups</code>\n\n"
        "Carrier auto-detection works for most codes; specify it only if you want to override."
    )


def prompt_status() -> str:
    return _(
        "🔍 <b>Parcel status</b>\n\n"
        "Send: <code>/status CODE</code>\n"
        "Example: <code>/status 1Z999AA10123456784</code>\n\n"
        "Tip: use 📋 Parcel list to see all your codes."
    )


def prompt_events() -> str:
    return _(
        "📋 <b>Events history</b>\n\n"
        "Send: <code>/events CODE</code>\n"
        "Example: <code>/events 1Z999AA10123456784</code>"
    )


def prompt_remove() -> str:
    return _(
        "🗑 <b>Remove a parcel</b>\n\n"
        "Send: <code>/remove CODE</code>\n"
        "Example: <code>/remove 1Z999AA10123456784</code>"
    )


def prompt_rename() -> str:
    return _(
        "✏️ <b>Rename a parcel</b>\n\n"
        "Send: <code>/rename CODE NEW_NAME</code>\n"
        "Example: <code>/rename 1Z999AA10123456784 amazon order</code>"
    )


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


def stats_full(  # noqa: PLR0913
    *,
    by_status: str,
    by_carrier: str,
    events: int,
    last_check: str,
    quarantined: int,
    total_trackers: int,
    users: int,
) -> str:
    return _(
        "<b>📊 Statistics</b>\n\n"
        "<b>Parcels:</b> {by_status}\n"
        "<b>By carrier:</b> {by_carrier}\n"
        "<b>Activity:</b> {events} events · last check {last_check}\n"
        "<b>Health:</b> {ok}/{total} trackers ok · {quarantined} quarantined\n"
        "<b>Authorised users:</b> {users}"
    ).format(
        by_status=by_status,
        by_carrier=by_carrier or "—",
        events=events,
        last_check=last_check or "—",
        ok=total_trackers - quarantined,
        total=total_trackers,
        quarantined=quarantined,
        users=users,
    )


def generic_error() -> str:
    return _("⚠️ Something went wrong. Please try again in a moment.")


def history_header() -> str:
    return _("<b>📦 Delivered (archived)</b>")


def no_history() -> str:
    return _("No delivered parcels in your history yet.")


def delivery_confirm_prompt(title: str, tracking_number: str) -> str:
    return _(
        "✅ <b>{title}</b>\n<code>{tracking_number}</code>\n\n"
        "This parcel looks <b>delivered</b>. Did you receive it?"
    ).format(title=esc(title), tracking_number=esc(tracking_number))


def delivered_archived(tracking_number: str) -> str:  # noqa: ARG001
    return _("📦 Marked as received and archived. See /history.")


def delivery_kept_tracking(tracking_number: str) -> str:
    return _("👀 OK, I'll keep tracking <code>{tracking_number}</code>.").format(
        tracking_number=esc(tracking_number)
    )


def parcel_undone(tracking_number: str) -> str:
    return _("↩️ Removed <code>{tracking_number}</code>.").format(
        tracking_number=esc(tracking_number)
    )


def parcel_added_auto(tracking_number: str) -> str:
    return _("✅ Added <code>{tracking_number}</code> and tracking it now.").format(
        tracking_number=esc(tracking_number)
    )
