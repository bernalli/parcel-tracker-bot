"""Bot UI message constants. English baseline; translated via gettext."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from parcel_tracker.i18n import _, _n

if TYPE_CHECKING:
    from parcel_tracker.db.models import Parcel


def esc(value: object) -> str:
    """HTML-escape an untrusted value for safe interpolation into parse_mode='HTML' text."""
    return html.escape(str(value), quote=False) if value is not None else ""


def welcome() -> str:
    return _(
        "📦 <b>Parcel Tracker Bot</b>\n\n"
        "I follow your parcels with the carriers and tell you when something changes, "
        "with a map of the route.\n\n"
        "<b>Quick start</b>\n"
        "• Send a tracking number (or several, one per line) to start tracking\n"
        "• Send a .csv file to import many shipments at once\n"
        "• /menu opens everything else\n\n"
        "Selling online? Turn on <b>Seller mode</b> in Settings and open the web dashboard "
        "with /web."
    )


def help_text() -> str:
    return _(
        "📦 <b>Parcel Tracker Bot</b>\n\n"
        "• Send a tracking number → I track it (spaces and dashes are fine)\n"
        "• Several codes, one per line → I add them all\n"
        "• A .csv file → I import it (columns: tracking_number, name, order_ref, recipient, "
        "destination, tags, notes)\n"
        "• /menu — parcels, maps, settings\n"
        "• /list — your active parcels\n"
        "• /web — open the web dashboard\n"
        "• /export — download your shipments as CSV\n"
        "• /forgetme — delete all your data\n"
        "• /help — this message"
    )


def try_again_in(seconds: int) -> str:
    return _("⏳ Please wait {seconds}s before trying again.").format(seconds=int(seconds))


def forgetme_confirm_prompt() -> str:
    return _(
        "⚠️ <b>Delete all your data?</b>\n\n"
        "Your parcels (active and archived), their tracking history, your notification "
        "settings and your language choice will be deleted. This cannot be undone."
    )


def forgetme_done() -> str:
    return _("🗑 Done: everything the bot stored about you has been deleted.")


def unauthorized() -> str:
    return _("⛔ You are not authorised to use this bot.")


def owner_only() -> str:
    return _("⛔ Only admins can use this command.")


def parcel_added(name: str) -> str:
    return _("✅ Parcel added: <b>{name}</b>").format(name=esc(name))


def parcel_duplicate(tracking_number: str) -> str:
    return _("⚠️ Parcel <code>{tracking_number}</code> is already tracked.").format(
        tracking_number=esc(tracking_number)
    )


def max_active_reached(limit: int) -> str:
    return _(
        "⚠️ You already track the maximum of <b>{limit}</b> active parcels. "
        "Remove one (🗑 button or <code>/remove CODE</code>) before adding another."
    ).format(limit=limit)


def parcel_removed(tracking_number: str) -> str:
    return _("🗑 Parcel removed: <b>{tracking_number}</b>").format(
        tracking_number=esc(tracking_number)
    )


def parcel_not_found(tracking_number: str) -> str:
    return _("❌ Parcel <code>{tracking_number}</code> not found.").format(
        tracking_number=esc(tracking_number)
    )


def parcel_renamed(tracking_number: str, name: str) -> str:
    return _("✏️ Parcel <code>{tracking_number}</code> renamed to <b>{name}</b>.").format(
        tracking_number=esc(tracking_number), name=esc(name)
    )


def no_parcels_active() -> str:
    return _("You have no active parcels. Add one with <code>/add</code>.")


def no_events(tracking_number: str) -> str:
    return _("No events for <code>{tracking_number}</code>.").format(
        tracking_number=esc(tracking_number)
    )


def add_usage() -> str:
    return _("Usage: <code>/add CODE [name]</code>")


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


def cleanall_done(count: int) -> str:
    return _("🗑 Removed {count} active parcel(s).").format(count=count)


def cleanall_confirm_prompt() -> str:
    return _("⚠️ Remove ALL your active parcels? This archives every tracked parcel.")


def stats_header() -> str:
    return _("<b>📊 Statistics</b>")


def map_no_position(tracking_number: str) -> str:
    return _("🗺 No mappable position yet for <code>{tracking_number}</code>.").format(
        tracking_number=esc(tracking_number)
    )


def lang_current(current: str, available: list[str]) -> str:
    return _("Current language: <code>{current}</code>\nAvailable: {available}").format(
        current=esc(current), available=esc(", ".join(available))
    )


def lang_changed(new: str) -> str:
    return _("Language switched to <code>{new}</code>.").format(new=esc(new))


def lang_not_supported(requested: str, available: list[str]) -> str:
    return _("Language <code>{requested}</code> is not available. Try: {available}").format(
        requested=esc(requested), available=esc(", ".join(available))
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
        "Just paste the tracking number here — I'll detect the carrier automatically.\n\n"
        "You can also use:\n"
        "<code>/add CODE [name]</code>\n"
        "Example: <code>/add 1Z999AA10123456784 new phone</code>\n\n"
        "Right after adding, I'll ask you for a name so the parcel is easy to recognise."
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
        tracking_number=esc(tracking_number)
    )


def to_add_use(text: str) -> str:
    return _("To add, use: <code>/add {text}</code>").format(text=esc(text))


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


def delivery_confirm_prompt(title: str | None, tracking_number: str) -> str:
    if title:
        return _(
            "✅ <b>{title}</b>\n<code>{tracking_number}</code>\n\n"
            "This parcel looks <b>delivered</b>. Did you receive it?"
        ).format(title=esc(title), tracking_number=esc(tracking_number))
    return _(
        "✅ <code>{tracking_number}</code>\n\n"
        "This parcel looks <b>delivered</b>. Did you receive it?"
    ).format(tracking_number=esc(tracking_number))


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


def menu_maps_title() -> str:
    return _("🗺 Choose a parcel to see its route map:")


def prompt_rename_value(tracking_number: str) -> str:
    return _("✏️ Send the new name for <code>{tn}</code>:").format(tn=esc(tracking_number))


def prompt_adduser_value() -> str:
    return _("➕ Send the numeric user ID to authorise:")


def prompt_revoke_value() -> str:
    return _("🗑 Send the numeric user ID to revoke:")


def user_not_present(user_id: int) -> str:
    return _("⚠️ User <code>{user_id}</code> is not in the authorised list.").format(user_id=user_id)


def ask_parcel_name() -> str:
    return _("📛 What name do you want to give this parcel? Send it now (e.g. «iPhone 15»).")


def refresh_in_progress() -> str:
    return _("🔄 Checking with the carrier…")


def refresh_quarantined() -> str:
    return _("⏳ Tracker temporarily unavailable (quarantined). Showing last known data.")


def refresh_failed() -> str:
    return _("⚠️ Couldn't reach the carrier. Showing last known data.")


def name_hint() -> str:
    return _("✏️ Tip: give this parcel a name from the menu (Rename).")


def parcel_detail_card(parcel: Parcel) -> str:
    """Single source of truth for the parcel detail view (menu card and /status)."""
    from parcel_tracker.bot.formatting import (  # noqa: PLC0415 — avoid import cycle at module load
        fmt_check_time,
        fmt_event_time,
        status_emoji,
        status_label,
    )

    # Kept out of the f-strings below: babel cannot extract gettext calls nested
    # in f-strings on Python < 3.12.
    status_word = _("Status")
    last_check_word = _("Last check")
    lines = [
        f"📦 <b>{esc(parcel.name or parcel.tracking_number)}</b>",
        f"<code>{esc(parcel.tracking_number)}</code>",
        f"{status_word}: {status_emoji(parcel.status)} <b>{status_label(parcel.status)}</b>",
        f"{carrier_label()}: {esc(parcel.carrier_name or parcel.carrier_code or '?')}",
    ]
    if parcel.last_location:
        lines.append(f"📍 {esc(parcel.last_location)}")
    if parcel.last_event:
        row = f"🛈 {esc(parcel.last_event)}"
        when = fmt_event_time(parcel.last_event_time)
        if when:
            row += f" — <i>{esc(when)}</i>"
        lines.append(row)
    checked = fmt_check_time(parcel.last_check_at)
    if checked:
        lines.append(f"{last_check_word}: {checked}")
    lines.extend(_seller_lines(parcel))
    return "\n".join(lines)


def _seller_lines(parcel: Parcel) -> list[str]:
    """Order, customer, destination, tags and notes, when the seller set them."""
    order_word = _("Order")
    customer_word = _("Customer")
    lines: list[str] = []
    if parcel.order_ref or parcel.recipient or parcel.destination or parcel.tags or parcel.notes:
        lines.append("")
    if parcel.order_ref:
        lines.append(f"🧾 {order_word}: {esc(parcel.order_ref)}")
    if parcel.recipient or parcel.destination:
        who = " — ".join(esc(v) for v in (parcel.recipient, parcel.destination) if v)
        lines.append(f"👤 {customer_word}: {who}")
    if parcel.tags:
        lines.append("🏷 " + " ".join(f"#{esc(t)}" for t in parcel.tags))
    if parcel.notes:
        lines.append(f"🗒 <i>{esc(parcel.notes[:300])}</i>")
    return lines


def delivered_notice(title: str | None, tracking_number: str, recipient: str | None) -> str:
    """Seller mode: the parcel reached the customer and was archived automatically."""
    head = f"✅ <b>{esc(title)}</b>\n" if title else "✅ "
    body = (
        _("Delivered to the recipient.")
        if not recipient
        else _("Delivered to <b>{recipient}</b>.").format(recipient=esc(recipient))
    )
    archived = _("Archived automatically — see /history.")
    return f"{head}<code>{esc(tracking_number)}</code>\n\n{body}\n<i>{archived}</i>"


def stall_alert(title: str | None, tracking_number: str, *, days: int, status_text: str) -> str:
    """A shipment saw no carrier update for ``days`` days."""
    head = f"⏸ <b>{esc(title)}</b>\n" if title else "⏸ "
    body = _(
        "No carrier update for <b>{days} days</b> (last status: {status}). "
        "The shipment may be stuck: consider contacting the carrier."
    ).format(days=int(days), status=status_text)
    return f"{head}<code>{esc(tracking_number)}</code>\n\n{body}"


def user_protected(user_id: int) -> str:
    return _(
        "⛔ User <code>{user_id}</code> is authorised in the configuration "
        "(OWNER_ID, ADMIN_USER_IDS or ALLOWED_USER_IDS). Remove them from .env instead."
    ).format(user_id=user_id)


def whoami(user_id: int, username: str | None) -> str:
    if username:
        return _("Your ID: <code>{user_id}</code>\nUsername: @{username}").format(
            user_id=user_id, username=esc(username)
        )
    return _("Your ID: <code>{user_id}</code>\nUsername: (none)").format(user_id=user_id)


def count_active(n: int) -> str:
    return _n("{n} active", "{n} active", n).format(n=n)


def count_archived(n: int) -> str:
    return _n("{n} archived", "{n} archived", n).format(n=n)


def bulk_added(*, added: int, duplicates: int, over_limit: int) -> str:
    lines = [_n("✅ Added {n} parcel.", "✅ Added {n} parcels.", added).format(n=added)]
    if duplicates:
        lines.append(
            _n("{n} was already tracked.", "{n} were already tracked.", duplicates).format(
                n=duplicates
            )
        )
    if over_limit:
        lines.append(
            _n(
                "⚠️ {n} not added: active parcel limit reached.",
                "⚠️ {n} not added: active parcel limit reached.",
                over_limit,
            ).format(n=over_limit)
        )
    return "\n".join(lines)


def web_disabled() -> str:
    return _(
        "🌐 The web dashboard is not enabled on this bot.\n"
        "The admin can turn it on with <code>WEB_ENABLED=true</code> and "
        "<code>WEB_PUBLIC_URL</code> in the .env file."
    )


def web_login_link(url: str) -> str:
    return _(
        "🌐 <b>Web dashboard</b>\n\n"
        '<a href="{url}">Open the dashboard</a>\n\n'
        "The link signs you in once and expires in 15 minutes. Don't share it."
    ).format(url=esc(url))


def share_link(url: str) -> str:
    return _(
        "🔗 <b>Customer tracking link</b>\n\n{url}\n\n"
        "Send it to your customer: it shows the carrier status and history, never your notes. "
        "You can revoke it from the web dashboard."
    ).format(url=esc(url))


def export_caption(n: int) -> str:
    return _n("📄 {n} shipment exported.", "📄 {n} shipments exported.", n).format(n=n)


def import_too_large() -> str:
    return _("⚠️ The file is too large (1 MB max).")


def import_unreadable() -> str:
    return _("⚠️ I couldn't read that file as CSV.")


def import_report(
    *,
    added: int,
    duplicates: int,
    invalid: int,
    over_limit: int,
    first_errors: list[tuple[int, str]],
) -> str:
    lines = [
        _("📥 <b>Import finished</b>"),
        _(
            "Added: {added} · already tracked: {dup} · invalid: {invalid} · over the limit: {over}"
        ).format(added=added, dup=duplicates, invalid=invalid, over=over_limit),
    ]
    for line_no, reason in first_errors:
        lines.append(_("Line {line}: {reason}").format(line=line_no, reason=esc(reason)))
    return "\n".join(lines)


def details_menu(parcel: Parcel) -> str:
    return _("📝 <b>Details</b> of <code>{tn}</code>\nChoose what to edit:").format(
        tn=esc(parcel.tracking_number)
    )


def ask_detail_value(label: str, tracking_number: str) -> str:
    return _(
        "📝 Send the new <b>{label}</b> for <code>{tn}</code> (send <code>-</code> to clear it):"
    ).format(label=esc(label), tn=esc(tracking_number))


def detail_saved(label: str) -> str:
    return _("✅ {label} saved.").format(label=esc(label))


def seller_mode_changed(enabled: bool) -> str:
    if enabled:
        return _(
            "🏪 <b>Seller mode on.</b> Delivered parcels are archived automatically and you "
            'get a short notice instead of the "did you receive it?" question.'
        )
    return _("📦 <b>Seller mode off.</b> I'll ask you to confirm each delivery again.")
