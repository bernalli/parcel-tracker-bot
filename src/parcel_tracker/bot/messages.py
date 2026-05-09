"""Bot UI messages (Italian baseline; will be wrapped with gettext _() in Phase 3)."""

from __future__ import annotations

WELCOME = (
    "📦 <b>Parcel Tracker Bot</b>\n\n"
    "Traccia automaticamente i tuoi pacchi e ricevi notifiche intelligenti.\n\n"
    "<b>Come iniziare:</b>\n"
    "• Invia un codice tracking per aggiungerlo\n"
    "• Usa <code>/add CODICE nome corriere</code>\n"
    "• Premi /menu per il menu interattivo"
)

HELP_TEXT = (
    "<b>Comandi disponibili:</b>\n"
    "/add CODICE [nome] [corriere] - aggiungi un pacco\n"
    "/list - elenca i pacchi attivi\n"
    "/status CODICE - dettagli pacco\n"
    "/events CODICE - storico eventi\n"
    "/remove CODICE - rimuovi pacco\n"
    "/rename CODICE NOME - rinomina pacco\n"
    "/checkall - aggiorna tutti i pacchi\n"
    "/menu - menu interattivo\n"
    "/help - questa guida"
)

UNAUTHORIZED = "⛔ Non sei autorizzato a usare questo bot."
OWNER_ONLY = "⛔ Solo l'owner può usare questo comando."

PARCEL_ADDED = "✅ Pacco aggiunto: <b>{name}</b>"
PARCEL_REMOVED = "🗑 Pacco rimosso: <b>{tracking_number}</b>"
PARCEL_NOT_FOUND = "❌ Pacco <code>{tracking_number}</code> non trovato."
PARCEL_RENAMED = "✏️ Pacco <code>{tracking_number}</code> rinominato in <b>{name}</b>."

NO_PARCELS_ACTIVE = "Non hai pacchi attivi. Aggiungine uno con <code>/add</code>."
NO_EVENTS = "Nessun evento per <code>{tracking_number}</code>."

ADD_USAGE = "Uso: <code>/add CODICE [nome] [corriere]</code>"
REMOVE_USAGE = "Uso: <code>/remove CODICE</code>"
RENAME_USAGE = "Uso: <code>/rename CODICE NUOVO_NOME</code>"
STATUS_USAGE = "Uso: <code>/status CODICE</code>"
EVENTS_USAGE = "Uso: <code>/events CODICE</code>"

USER_ADDED = "✅ Utente <code>{user_id}</code> aggiunto."
USER_REMOVED = "🗑 Utente <code>{user_id}</code> rimosso."
USER_DUPLICATE = "⚠️ Utente <code>{user_id}</code> già presente."
ADDUSER_USAGE = "Uso: <code>/adduser USER_ID</code>"
REMOVEUSER_USAGE = "Uso: <code>/removeuser USER_ID</code>"

CHECKALL_STARTED = "🔄 Controllo di tutti i pacchi avviato..."
CHECKALL_DONE = "✅ Controllo completato."

CLEAN_DONE = "🧹 Pulizia completata."
CLEANALL_DONE = "🧹 Tutti i pacchi rimossi."

STATS_HEADER = "<b>📊 Statistiche</b>"
MAP_PLACEHOLDER = "🗺 Mappa pacchi (in sviluppo)"
