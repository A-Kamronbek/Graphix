# What's left for you

Everything here needs a password, a secret, a card, or an account only you can
sign into. Everything that didn't is already done — see **Already done** at the
bottom so you don't redo it.

Work top to bottom. Step 1 blocks step 2; after that the order is yours.

Every command runs **on the server** unless it says otherwise:

```bash
ssh ubuntu@57.128.240.51
```

That works from your machine with your existing key, no password.

---

## 1. Let the server pull from GitHub

**Why this is first:** `/srv/graphix` is **not a git checkout** — there is no
`.git` directory in it. The code got there by hand. So `git pull` does not
work, `deploy/RUNBOOK.md` §20 cannot run as written, and **Phase 14 is not on
the server**: it is still running the 2026-09-19 code, with `click-pkg`
instead of `tolov`, no slide cards, no Payme or Octo.

The repository is private, so the server needs its own read-only key. I have
already made one — the private half is on the server and has never left it.

### 1a. Push `main` to GitHub — on your machine

```powershell
cd D:\phyton\ValleyMade
git push origin main
git push origin phase-10-tests
```

I have not pushed anything; both branches are ahead of `origin` locally only.
Say the word and I'll do it instead.

### 1b. Add the deploy key to GitHub

Go to **github.com/A-Kamronbek/Graphix → Settings → Deploy keys → Add deploy key**.

- **Title:** `graphix production server`
- **Key:** paste exactly this line —

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKcWy3fkg8S9TW3fGjrcgLpCf9DmT+izU9tjxtB6vTEV graphix-deploy@vps
```

- **Leave "Allow write access" unchecked.** The server only ever reads.

### 1c. Check it worked

```bash
sudo -u graphix ssh -T git@github.com
```

Expect: `Hi A-Kamronbek/Graphix! You've successfully authenticated, but GitHub
does not provide shell access.` That sentence is success.

Then tell me, and I'll turn `/srv/graphix` into a real checkout and deploy
Phase 14. It is not risky — `.env`, `media/`, `logs/` and `staticfiles/` are
all gitignored, so nothing you care about is touched — but it changes
production, so I'd rather do it with you there than while you're asleep.

---

## 2. Payment credentials

Payme and Octo are **not in the server's `.env` at all** — it predates Phase 14.
Add them after step 1's deploy, or the app won't know the names yet.

```bash
sudo -u graphix nano /srv/graphix/.env
```

Add:

```
PAYME_ID=
PAYME_KEY=
OCTO_SHOP_ID=
OCTO_SECRET=
OCTO_UNIQUE_KEY=
```

**`OCTO_UNIQUE_KEY` is required in production.** Octo issues it separately from
the shop id and secret. Without it the site treats Octo as unconfigured and
refuses to start an Octo payment — which is deliberate: with `DEBUG` off and no
key, the callback cannot be built at all, so a customer would pay and the order
would never be marked paid. Ask Octo for it by name: *unique key* / *уникальный
ключ*.

Then:

```bash
sudo systemctl restart graphix
```

Then in **Boshqaruv → Toʻlov usullari**, check each method reads **Sozlangan**
before you switch it on.

> **Do this now, before anything else on this page: switch Payme OFF.** It is
> switched on today with no credentials, so a customer can choose it and place
> an order that can never be paid for.

---

## 3. Telegram

Four keys are empty on the server, so the shop gets no order notifications at
all:

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_BOT_WEBHOOK_URL=
WEBSITE_WEBHOOK_SECRET=
```

- **If the site talks to Telegram directly:** fill the first two and leave the
  other two empty.
- **If it relays through your bot service:** fill all four — and that needs
  **Q33 answered first: where does the bot service run, and at what address?**
  If it runs anywhere but this server, the privacy policy has to name that
  machine, so this is a legal question as much as a technical one.

Restart, then place a test order and confirm exactly **one** message arrives,
headed `toʻlandi`.

---

## 4. Eskiz sender name

The server sends SMS as **`4546`** — Eskiz's test sender, not yours:

```bash
sudo grep ESKIZ_FROM /srv/graphix/.env     # ESKIZ_FROM=4546
```

If the `GRAPHIX` sender is approved (§19 Q17 says it is), change it to
`ESKIZ_FROM=GRAPHIX`, restart, and sign up with a real number to confirm the
SMS arrives branded.

**Careful:** Eskiz moderates the *message bodies* as well as the sender, and
the bodies changed in Phase 1a. If the new bodies aren't approved, the SMS
silently stops. Confirm both with Eskiz before switching.

---

## 5. Backups off the server — the most important one

The nightly backup **has never run**. The timer is disabled, and it is disabled
for a good reason: the script refuses to report success when nothing has left
the machine.

I ran it by hand today and everything up to that point works — the database
dumped, `media/` snapshotted, old snapshots pruned, and a restore into a
throwaway database matched all 35 tables exactly, including one real order's
total read back out of the dump. The only missing piece is somewhere to put it.

**Pick a destination.** It needs to be a machine you can rsync to over SSH,
that is *not this server*. Your TapCon VPS (146.59.57.248) would do; so would a
cheap storage box, or your own laptop if you'd rather start there.

Then, on the GRAPHIX server:

```bash
# 1. let the graphix user reach the destination
sudo -u graphix ssh-keygen -t ed25519 -N '' -f /srv/graphix/.ssh/backup_ed25519
sudo cat /srv/graphix/.ssh/backup_ed25519.pub
#    -> add that line to ~/.ssh/authorized_keys on the DESTINATION machine

# 2. tell the backup where to go
sudo -u graphix nano /srv/graphix-backups/backup.env
#    BACKUP_REMOTE=user@host:/path/to/graphix-backups

# 3. prove it end to end
sudo systemctl start graphix-backup.service
sudo journalctl -u graphix-backup.service -n 20 --no-pager
#    the last line must read: done

# 4. only once that is green, turn the nightly on
sudo systemctl enable --now graphix-backup.timer
systemctl list-timers graphix-backup.timer --no-pager
```

It runs at 03:30 Asia/Tashkent, keeps 14 days, and hard-links unchanged photos
so fourteen nights of media cost barely more than one.

**Until step 4, there is no off-site copy of this site's data.** Right now the
only backups are on the same disk as the thing they are backing up.

---

## 6. Uptime monitoring

Two checks, on any free service (UptimeRobot, Better Stack, Healthchecks.io):

| What | URL | Expect |
|---|---|---|
| The site | `https://graphix.uz/uz/` | 200 |
| The Click webhook | `https://graphix.uz/payment/click/update/` | **405** |

The second matters more than it looks. A `GET` to the webhook *should* be 405 —
that means the path resolves and the view is there. If it ever answers **301,
302 or 404**, payments are silently broken and nothing else on the site will
tell you (§12 risk #2). Set the monitor to treat 405 as up and anything else as
down.

---

## 7. Search Console

Add `https://graphix.uz/` at
[search.google.com/search-console](https://search.google.com/search-console),
verify by DNS TXT record, and submit `https://graphix.uz/sitemap.xml`.

You can do this now — it does no harm while the site is `noindex` — but there
is nothing to see until the catalogue is loaded and indexing is switched on at
launch.

---

## 8. The live payment test

Last, after everything above. **One real order per delivery tier**, paid with a
real card for 1 000 soʻm:

1. A branch order — region, district, postal index.
2. A home order with a dropped pin.
3. A home order with the address typed rather than pinned.

For each, confirm all three halves, because a payment can look fine in the app
and be broken on the server:

```bash
sudo journalctl -u graphix --since '10 min ago' | grep -iE 'click|payme|octo'
```

- the order reads `paid` in `/boshqaruv/buyurtmalar/`
- the Telegram message arrives **once**, headed `toʻlandi`
- the webhook was called at its exact path with no redirect in front of it

Repeat per payment method you have switched on.

---

## Decisions, not steps

These need an answer from you or the owner before launch. None of them is code.

| | |
|---|---|
| **Q38 — how is cash actually collected?** | Cash is a payment option, but an ordinary Uzpost parcel has nobody to take money at handover. Today "cash" has no mechanism behind it. Either arrange the UzPost partner programme (Q24) or switch cash off. |
| **Q30 — register as a personal-data operator** | With the state register, before the site takes a real customer's data. The owner's. |
| **Q33 — where does the Telegram bot run?** | Blocks step 3's second half, and decides whether the privacy policy has to name another machine. |
| **Q24 — call Uzpost about the partner programme** | Also the answer to Q38. |
| **Q8 — were the mockup designs placeholders?** | If any reproduce other brands' marks and are meant for sale, worth checking before listing. |
| **Q19 — when can real product photography exist?** | This is what gates launch. Nothing else left is close to it in size. |

---

## Already done — don't redo these

The progress tracker listed these as outstanding. They aren't:

- **Superuser and phone verification** — `graphixadmin` exists, is a superuser,
  and is phone-verified.
- **Click, Eskiz and Google Maps credentials** — all present and non-empty.
- **`media/` is in the backup** — the nightly snapshots it alongside the
  database.
- **Log rotation** — working and proven: nginx logs rotate daily and keep 30,
  Django's `app.log` rotates itself on the same schedule. Disk is at 10%.
- **The dump and the restore** — both verified today, and a real defect fixed
  in the restore checker while doing it. It had been reporting "restore
  verified" while skipping its most important assertion, because that
  assertion only runs once an order exists and on 2026-09-19 there were none.
