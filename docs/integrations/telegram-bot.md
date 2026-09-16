# Telegram bot service — what the site sends

Plan §17 #206. When a bot service is set up, the site does not call Telegram
itself. It sends every notification to the bot as a signed JSON request, and
the bot shows it to the shop's staff. This page is everything the bot needs
to know to receive them. The bot never has to call the site: the site pushes
each event once, when it happens.

The code is `vm/core/telegram.py`.

## Setting it up

Both sides hold **the same secret**. Generate it once and paste it into both
`.env` files, and nowhere else:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

On the site, `vm/.env`:

```
TELEGRAM_BOT_WEBHOOK_URL=https://bot.example.uz/graphix/events
WEBSITE_WEBHOOK_SECRET=<the shared secret>
```

On the bot: `WEBSITE_WEBHOOK_SECRET=<the same value>`.

- The URL must be `https://`. Plain `http://` is accepted only when the bot
  runs on the same server as the site (`127.0.0.1`, `localhost` or `::1`).
  Any other address is refused before anything is sent, because the request
  carries the secret.
- The site does not follow redirects. Give it the final URL.
- Once the URL is set, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` on the site
  are not used. Clear the URL and the site goes back to calling Telegram
  directly with those two values.
- If the URL is set but the secret is blank, nothing is sent and the site logs
  an error.

## The request

`POST <TELEGRAM_BOT_WEBHOOK_URL>` — one request per event. It is sent after the
database change it reports has been saved, and it is never repeated. The site
waits at most 10 seconds.

| Header | Value |
|---|---|
| `Content-Type` | `application/json; charset=utf-8` |
| `User-Agent` | `GRAPHIX-webhook/1` |
| `X-Webhook-Event` | the event name, the same as `event` in the body |
| `X-Webhook-Timestamp` | Unix time, in seconds, when the request was signed |
| `X-Webhook-Signature` | `sha256=` + hex HMAC-SHA256 of `<timestamp>.<raw body>`, keyed with the secret |
| `X-Webhook-Secret` | the shared secret itself |

The body is UTF-8 JSON:

```json
{
  "event": "order.created",
  "sent_at": "2026-09-16T23:41:07.512+05:00",
  "text": "🧾 <b>Yangi buyurtma</b> GX-260916-0001\n• Mahsulot — M × 1\n…",
  "parse_mode": "HTML",
  "data": {"order": {"…": "…"}}
}
```

- `text` is the finished message, in Uzbek, for Telegram's `sendMessage` with
  `parse_mode=HTML`. Everything the customer typed is already HTML-escaped. A
  bot that only forwards messages can send `text` exactly as it is.
- `data` carries the same facts, unformatted, for a bot that lays the message
  out itself or adds buttons. It never holds anything `text` does not say.

## Checking that a request is from the site

Check one of the two. The signature is the stronger one.

1. **The secret header.** `X-Webhook-Secret` equals your secret. Compare in
   constant time (`hmac.compare_digest`), never with `==`.
2. **The signature.** Recompute it over the **raw body bytes** — not over JSON
   you parsed and serialised again — and reject a timestamp more than five
   minutes away from your clock:

```python
import hashlib
import hmac
import time


def is_from_the_site(headers, raw_body: bytes, secret: str) -> bool:
    """True when the request was signed with our shared secret, recently."""
    timestamp = headers.get('X-Webhook-Timestamp', '')
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    signed = timestamp.encode('ascii') + b'.' + raw_body
    expected = 'sha256=' + hmac.new(secret.encode('utf-8'), signed,
                                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers.get('X-Webhook-Signature', ''))
```

Refuse anything that fails with `401` and do nothing with it.

## The answer

- Any **2xx** means delivered. The body of the answer is ignored.
- Anything else — another status, a redirect, a timeout, no answer — is logged
  on the site as a failure, and the event is **not** sent again.
- Answer within 10 seconds. If sending to Telegram can be slow, answer first
  and send afterwards.
- **An event you do not recognise: answer 2xx and ignore it.** New events may
  be added later, and they must not look like failures.

## The events

Amounts are whole so'm, as integers. Dates are ISO 8601 with a time zone.
`admin_url` links to the order, message or review in the site's admin; it is
empty if the admin is not reachable. Field values below are examples.

### `order.created`

A customer placed an order. It is not paid yet (`status` is `paying`).

```json
{"order": {
  "id": 42,
  "number": "GX-260916-0001",
  "status": "paying",
  "created_at": "2026-09-16T18:41:05.123Z",
  "total": 190000,
  "currency": "UZS",
  "payment_method": "click",
  "delivery": {"code": "uzpost_office", "name": "Pochta boʻlimigacha",
               "price": 15000, "to_branch": true},
  "address": "Toshkent shahri · Chilonzor tumani · 100011",
  "location": {"lat": 41.2995, "lng": 69.2401},
  "recipient": {"name": "Ali Valiyev", "phone": "+998 90 123 45 67"},
  "notes": "",
  "items": [{"product": "Mahsulot", "size": "M", "quantity": 1, "price": 175000}],
  "admin_url": "https://graphix.uz/admin/payment/order/42/change/"
}}
```

- `delivery` is `null` for an order without a delivery method.
- `to_branch` is `true` when the parcel goes to a post office, `false` for a
  door delivery.
- `address` is the destination as it was frozen at checkout, on one line.
- `location` is `null` unless the customer dropped a pin on the map.
- `recipient` is the person named on the parcel, which is not always the
  account holder.

### `order.paid`

The payment for an order went through.

```json
{"order": {"id": 42, "number": "GX-260916-0001", "total": 190000,
           "currency": "UZS", "admin_url": "https://graphix.uz/admin/payment/order/42/change/"}}
```

### `message.created`

A signed-in customer sent a message through the contact page.

```json
{"message": {"id": 7, "name": "Ali Valiyev", "username": "ali",
             "phone": "+998 90 123 45 67", "subject": "Oʻlcham haqida",
             "text": "Salom! …", "admin_url": "https://graphix.uz/admin/core/msg/7/change/"}}
```

### `review.created`

A customer wrote a review. It is not public until staff approve it. Sent once,
when the review is created — approving or rejecting it sends nothing.

```json
{"review": {"id": 3, "product": "Mahsulot", "rating": 5, "text": "Zoʻr!",
            "has_photos": true, "admin_url": "https://graphix.uz/admin/product/review/3/change/"}}
```

## Personal data

The events carry customers' names, phone numbers, addresses and messages. The
privacy policy tells customers that notifications reach the shop's staff
through the shop's Telegram bot, and that the site's data is stored in Poland
(Warsaw). So:

- keep this data only as long as the bot needs it, and never share it;
- if the bot runs anywhere other than the site's server in Warsaw, tell
  Kamronbek which country — the privacy policy has to name it before launch.

## Trying it

From `vm/`, with both values in `.env`:

```
python manage.py shell -c "from core import telegram; print(telegram.deliver('test.ping', '<b>GRAPHIX</b>: sinov', {}))"
```

`True` means the bot answered 2xx. `False` means it did not — the reason is in
the site's log. A bot that follows the rule above answers `test.ping` with 2xx
and ignores it.
