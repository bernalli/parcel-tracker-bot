# Using the bot for a shop

If you sell online and ship parcels to customers, the bot works as a small
shipment control room: it follows every parcel with the carrier, tells you
when one needs attention, and gives each customer a tracking page under your
shop's name. Everything stays on your server.

## A typical setup

1. **Add a 17track key.** It covers BRT, GLS, SDA, Poste Italiane, InPost and
   2,000+ other carriers, and backs up every built-in scraper. See
   [api-keys](api-keys.md).
2. **Raise the shipment limit.** `MAX_ACTIVE_SHIPMENTS=0` removes it; keep an
   eye on your 17track quota.
3. **Enable the dashboard.** `WEB_ENABLED=true` and a `WEB_PUBLIC_URL` your
   customers can reach (see [operations](operations.md#exposing-the-dashboard)).
4. **Turn on seller mode** in the bot (**Settings → Seller mode**) or in the
   dashboard. Delivered parcels are archived automatically with a short notice,
   instead of the buyer-style "did you receive it?" question.
5. **Set your shop name** in the dashboard settings. It heads every tracking
   page you share.

## Adding shipments

Pick whatever fits your day:

- **Telegram:** paste a tracking number, or several, one per line. Spaces and
  dashes copied from a label are fine. Add a name after the code:
  `RR123456785IT blue mug`.
- **CSV:** export orders from your shop back-office and send the file to the
  bot, or upload it in **Import**. Columns such as order number, customer,
  destination, tags and notes are picked up automatically.
- **Dashboard:** **Add shipment** for one parcel with all its details, or
  paste many codes at once.
- **API:** create the shipment from your shop or an automation tool the moment
  the label is printed. See [web](web.md#json-api).

Each shipment can carry an order reference, the customer, the destination,
tags (for example `express`, `gift`, `return`) and notes. Edit them from the
dashboard, or in Telegram with **📝 Details** on the parcel card.

## Knowing what needs you

- **Status changes** arrive in Telegram with a route map. Mute the statuses
  you don't care about in **Settings → Notifications**; problems
  (undelivered, exception, returned) are worth keeping on.
- **Stalled shipments:** when an active parcel has had no carrier news for
  `STALL_ALERT_DAYS` days (default 7), the bot warns you once with buttons to
  check it now. A label that was printed but never handed to the carrier shows
  up this way too.
- **Need attention** in the dashboard lists every problem and every stalled
  parcel in one place. It is the list to go through when a customer writes
  "where is my order?".

## Telling customers where their parcel is

Open a shipment and choose **Create link**, or tap **🔗 Share** in Telegram.
Send the link to your customer by email or chat. The page shows the carrier
status, history and route map in the customer's language, and nothing of your
own: no notes, no order number, no customer data. Revoke it whenever you like.

## Measuring

The dashboard shows how long deliveries take (median and the time within which
nine in ten arrive), the share of shipments delivered rather than returned or
failed, weekly volume, and the same per carrier. Use it to choose carriers,
set honest delivery promises, and spot a carrier having a bad week.

## Privacy and data

- Customer names and destinations stay in your SQLite database; they are never
  sent to a carrier or to 17track. Only the tracking number is.
- Archived shipments are deleted after `DATA_RETENTION_DAYS` days (default
  180, `0` keeps them). Export them first if you want to keep records.
- In an export, a cell that starts with `=`, `+`, `-` or `@` gets a leading
  apostrophe, so a spreadsheet shows it as text instead of running it as a
  formula. Importing the file removes the apostrophe again.
- **Settings → Delete all my data** in the dashboard, or `/forgetme` in
  Telegram, erases everything stored about you.

## Working as a team

Every authorised Telegram user has their own shipments. To share one view,
use one Telegram account for the shop, or give colleagues their own access
with `/adduser` and split shipments between them.
