# GRAPHIX — deployment runbook

Phase 1b. Read `docs/PLAN.md` §9 Phase 1b first; this is how, not what or why.

Every command runs on the server unless it says otherwise. Steps marked
**[Kamronbek]** cannot be done for you: they need a password, a secret, a card,
or an account only you can sign into.

---

## 0. Before anything

**Stop if §19 Q36 is unanswered.** The target box is serving valleymade.uz and
refuses the current SSH key, which is what an *older* machine looks like rather
than one bought last week. Confirm in the OVH panel which instance is the
Warsaw VPS from 2026-09-12. Installing GRAPHIX on the wrong machine is cheap to
avoid now and expensive to unpick once the domain points at it.

- [ ] **[Kamronbek]** Q36 answered — the target is confirmed
- [ ] **[Kamronbek]** your public key is in `~/.ssh/authorized_keys` on it
- [ ] `ssh <user>@<host> whoami` answers without a password prompt

**The box already runs another site.** Nothing in this runbook edits, disables
or removes it (§17 #241). GRAPHIX gets its own user, directory, database,
socket, nginx site and log files. If a step here asks you to change something
that is already there, that step is wrong — stop and say so.

---

## 1. Take a dump of what is already on the machine

Before PostgreSQL is touched at all. The standing rule does not care that the
old site's data is believed to be worthless — the point of the rule is that you
find out whether it was worthless *after* you still have it.

```bash
sudo -u postgres psql -lqt | cut -d'|' -f1        # what is there
sudo -u postgres pg_dumpall --file=/root/pre-graphix-$(date +%F).sql
sudo ls -lh /root/pre-graphix-*.sql                # confirm it is not empty
```

Copy it off the machine as well. A dump that only exists on the server is not
a backup — the same argument `deploy/bin/backup.sh` refuses to run without.

---

## 2. Survey

```bash
. /etc/os-release && echo "$PRETTY_NAME"
free -m | head -2 ; df -h /
systemctl list-units --type=service --state=running --no-legend | awk '{print $1}'
ls -l /etc/nginx/sites-enabled/
sudo certbot certificates 2>/dev/null | grep -E 'Certificate Name|Domains|Expiry'
ss -ltnp | grep -E ':(80|443|5432|6379|8000) '
```

Write down what is running. You need it in step 11 to be sure the new nginx
site cannot collide with the old one's `server_name`.

---

## 3. Packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
    postgresql postgresql-client redis-server \
    nginx certbot python3-certbot-nginx \
    git rsync logrotate
```

Most of these are probably already installed for the other site; `apt install`
on an installed package is a no-op, which is why it is safe to run the whole
line rather than picking through it.

Redis is required, not optional: without it each gunicorn worker keeps its own
rate-limit counters and the real limit becomes three times the configured one
(§12 risk #15).

```bash
sudo systemctl enable --now redis-server
redis-cli ping            # PONG
```

---

## 4. A user and a home for the application

```bash
sudo adduser --system --group --home /srv/graphix --shell /usr/sbin/nologin graphix
sudo mkdir -p /srv/graphix /srv/graphix-backups
sudo chown graphix:graphix /srv/graphix /srv/graphix-backups
sudo chmod 755 /srv/graphix
sudo chmod 700 /srv/graphix-backups
```

`--system` and `nologin`: nothing should ever log in as this user, and the
backup job reaches its files through group membership rather than a shell.

---

## 5. The code

```bash
sudo -u graphix git clone https://github.com/A-Kamronbek/Graphix.git /srv/graphix
cd /srv/graphix
sudo -u graphix python3 -m venv .venv
sudo -u graphix .venv/bin/pip install --upgrade pip
sudo -u graphix .venv/bin/pip install -r requirements.txt
```

`requirements.txt` now pins `redis==8.1.0`. It is the single exception to §4's
zero-new-dependencies rule (§17 #240) and it exists because `settings.py`
selects Django's Redis cache backend the moment `REDIS_URL` is set — without
the package the first cache read raises, which means the first page.

---

## 6. The database

**[Kamronbek]** — you type the password; it never passes through the chat.

```bash
sudo -u postgres createuser --pwprompt graphix
sudo -u postgres createdb --owner=graphix graphix
# so restore-check.sh can build its scratch database later
sudo -u postgres psql -c 'ALTER ROLE graphix CREATEDB;'
```

The role name, the database name and the Linux user share a name on purpose:
peer authentication then works for the maintenance commands without a second
credential to keep anywhere.

---

## 7. The environment file

```bash
sudo -u graphix cp /srv/graphix/vm/.env.example /srv/graphix/vm/.env
sudo -u graphix chmod 600 /srv/graphix/vm/.env
sudo -u graphix nano /srv/graphix/vm/.env
```

**[Kamronbek]** — fill it in. The values that must change from the example:

| Key | Value |
|---|---|
| `SECRET_KEY` | fresh, from the command in the file's own comment |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `graphix.uz,www.graphix.uz` |
| `CSRF_TRUSTED_ORIGINS` | `https://graphix.uz,https://www.graphix.uz` |
| `SITE_URL` | `https://graphix.uz` |
| `DB_NAME` `DB_USER` `DB_PASSWORD` | `graphix`, `graphix`, what you typed in step 6 |
| `REDIS_URL` | `redis://127.0.0.1:6379/1` — uncomment it |

The rest — Click, Eskiz, Google Maps, Telegram — are step 18 onward. Every one
of them ships blank and the site runs without it (§17 #93), so the site can go
up before they are filled and each one switches a feature on rather than fixing
a breakage.

---

## 8. Build

```bash
cd /srv/graphix/vm
sudo -u graphix ../.venv/bin/python manage.py migrate
sudo -u graphix ../.venv/bin/python manage.py seed_regions
sudo -u graphix ../.venv/bin/python manage.py compilemessages
sudo -u graphix ../.venv/bin/python manage.py collectstatic --noinput
sudo -u graphix ../.venv/bin/python manage.py check --deploy
```

`seed_regions` is not a migration — no migration loads the fourteen regions and
their two hundred districts, so a fresh database has an empty delivery picker
until this runs. It is idempotent and deactivates rather than deletes.

`check --deploy` must report **no issues**. It does with `DEBUG=False`; if it
lists anything, stop and read it rather than continuing.

---

## 9. The owner's staff account

**[Kamronbek]**

```bash
cd /srv/graphix/vm
sudo -u graphix ../.venv/bin/python manage.py createsuperuser
```

Then open `https://<host>/admin/` once TLS is up and **mark that account's
phone as verified**. Until you do, `/boshqaruv/` will not open for it: the
phone-verification wall applies to staff too, which is §19 Q34 — decided as a
deploy step rather than a code change (§17 #227). This is that step.

---

## 10. The service

```bash
sudo cp /srv/graphix/deploy/systemd/graphix*.service /etc/systemd/system/
sudo cp /srv/graphix/deploy/systemd/graphix*.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now graphix.service
systemctl status graphix.service --no-pager
ls -l /run/graphix/graphix.sock          # srw-rw---- graphix www-data
```

The socket is under `/run/graphix/`, not a shared `/run/gunicorn/`, so it
cannot collide with the other site's (`graphix.service` explains why).

Do **not** enable the timers yet — the backup timer is step 16, after there is
something worth backing up and somewhere to put it.

---

## 11. nginx, over http first

```bash
sudo cp /srv/graphix/deploy/nginx/graphix.conf /etc/nginx/sites-available/graphix.conf
sudo ln -s /etc/nginx/sites-available/graphix.conf /etc/nginx/sites-enabled/
sudo mkdir -p /var/www/certbot
sudo cp /srv/graphix/deploy/logrotate/graphix /etc/logrotate.d/graphix
sudo logrotate --debug /etc/logrotate.d/graphix     # parses, changes nothing
sudo nginx -t
```

`nginx -t` will complain about the missing certificate, because the two `443`
blocks reference files certbot has not written yet. That is expected. Comment
out both `443` server blocks, reload, and let certbot put them back:

```bash
sudo systemctl reload nginx
curl -sI http://<host>/ -H 'Host: graphix.uz' | head -3
```

A 301 to `https://graphix.uz` is the right answer here — Django's
`SECURE_SSL_REDIRECT` is on and TLS is not up yet. The site being unreachable
at this exact moment is correct, not a fault.

---

## 12. DNS

**[Kamronbek]** — at Eskiz, which hosts the zone (`ns1/ns2.eskiz.uz`).
graphix.uz currently resolves to `45.138.159.4`; it needs to be the server.

| Record | Name | Value |
|---|---|---|
| A | `@` | *the server's address* |
| A | `www` | *the server's address* |

Then wait for it, from your own machine:

```powershell
Resolve-DnsName graphix.uz -Type A -Server 1.1.1.1
```

certbot cannot issue anything until both names resolve to the box. Nothing
below this line works before that.

---

## 13. TLS

```bash
sudo certbot --nginx -d graphix.uz -d www.graphix.uz
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl status certbot.timer --no-pager     # renewal is automatic
curl -sI https://graphix.uz/ | head -5
```

Then check the three things that are easy to get wrong and silent when wrong:

```bash
# HSTS, set by Django, not by nginx
curl -sI https://graphix.uz/uz/ | grep -i strict-transport-security
# the Click webhook — unprefixed, outside i18n_patterns. This one breaks payments.
curl -sI https://graphix.uz/payment/click/update/ | head -1
# static files are served by nginx with a year's cache, not by Django
curl -sI https://graphix.uz/static/css/tokens.*.css | grep -i cache-control
```

The webhook must answer from `/payment/click/update/` exactly — no `/uz/`, no
trailing redirect. A 405 or 400 is fine; a 301 or 404 is a broken payment
pipeline that will not show up until a real customer pays.

---

## 14. Redis, across workers

The rate limiter is the only thing that notices, and it notices in production
and not in a test. With `REDIS_URL` set and three workers running:

```bash
sudo systemctl restart graphix
for i in $(seq 1 12); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST https://graphix.uz/uz/login/ \
       -d 'username=nobody&password=wrong'
done ; echo
```

The codes must stop being `200`/`403` and start being the limiter's answer
partway through the run, and must keep it on a second run. If the limit only
bites after roughly three times as many attempts, the workers are counting
separately and `REDIS_URL` did not take.

```bash
redis-cli -n 1 --scan --pattern '*' | head       # keys appearing at all
```

---

## 15. First backup

```bash
sudo -u graphix mkdir -p /srv/graphix-backups
sudo -u graphix tee /srv/graphix-backups/backup.env >/dev/null <<'EOF'
# rsync destination for the off-server copy. Not in the repository: it names
# another machine.
BACKUP_REMOTE=
EOF
sudo -u graphix chmod 600 /srv/graphix-backups/backup.env
```

**[Kamronbek]** — decide where the off-server copy goes and put it in that
file as `user@host:/path`. It has to be a different machine; the tapcon VPS,
a home machine that is usually on, or object storage over rsync all qualify.
Then give the `graphix` user an SSH key and put its public half on the
destination:

```bash
sudo -u graphix ssh-keygen -t ed25519 -N '' -f /srv/graphix/.ssh/id_ed25519
sudo -u graphix cat /srv/graphix/.ssh/id_ed25519.pub
```

Run it, and then prove it:

```bash
sudo -u graphix /srv/graphix/deploy/bin/backup.sh
sudo -u graphix /srv/graphix/deploy/bin/restore-check.sh
```

`restore-check.sh` restores the newest dump into a throwaway database, compares
every table against the counts recorded when the dump was taken, checks that
the catalogue and the orders are not empty, and reads one real order back to
confirm its total survived. It refuses to touch any database that is not
`graphix_restorecheck`. **Exit code 0 is Phase 1b's Definition of Done for
backups** — until it returns 0, the backup is a file of unknown value.

---

## 16. Timers

```bash
sudo systemctl enable --now graphix-backup.timer graphix-prune-carts.timer
systemctl list-timers 'graphix*' --no-pager
```

`prune_guest_carts` is not housekeeping: the privacy policy tells the customer
an abandoned guest cart is deleted after thirty days, and nothing else on the
site deletes one. Without this timer that sentence is false.

---

## 17. Click

**[Kamronbek]** — in the Click merchant cabinet.

1. Register the webhook as `https://graphix.uz/payment/click/update/`.
2. Put `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID` and `CLICK_SECRET_KEY` in
   `/srv/graphix/vm/.env`, then `sudo systemctl restart graphix`.
3. Buy something real for 1 000 so'm and let it complete.

Then confirm all three halves, because a payment can look fine in the app and
be broken on the server:

```bash
sudo journalctl -u graphix --since '10 min ago' | grep -i click
```

- the order's status is `paid` in `/boshqaruv/buyurtmalar/`
- the Telegram message arrives **once**, headed `toʻlandi` (§17 #237)
- the webhook was called at `/payment/click/update/` with no redirect in front

This is the highest-risk step in the project. A wrong webhook URL fails
silently: the customer pays, Click is happy, and the order sits unpaid forever.

---

## 18. Eskiz, Telegram, Maps

**[Kamronbek]**

- `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM=GRAPHIX`. Sign up on the live
  site with a real number and confirm the SMS arrives branded GRAPHIX. The
  sender is approved (§19 Q17); **the message bodies changed in Phase 1a and
  Eskiz moderates bodies too**, so ask them to confirm both, or a rejected body
  fails silently at signup.
- Telegram: either `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, or
  `TELEGRAM_BOT_WEBHOOK_URL` + `WEBSITE_WEBHOOK_SECRET` if the notifications go
  through your own bot service — the first one set wins. **§19 Q33 is open**:
  if that service runs anywhere but this server, the privacy policy has to name
  that country too.
- `GOOGLE_MAPS_API_KEY`: enable billing (the Geocoding API answers
  `REQUEST_DENIED` without it, so a dropped pin cannot fill the address),
  restrict the key to `https://graphix.uz/*` and `https://www.graphix.uz/*`,
  and set a budget alert the same day (§12 risk #5).

`sudo systemctl restart graphix` after each.

---

## 19. Search Console and monitoring

**[Kamronbek]**

- Search Console: add `graphix.uz`, verify, submit `https://graphix.uz/sitemap.xml`.
  No Change of Address — there is no old property to move from (§17 #35).
- Uptime monitoring on `https://graphix.uz/` **and** on
  `https://graphix.uz/payment/click/update/`. The second one matters more: the
  home page going down is visible within minutes, the webhook going down is
  invisible until someone asks where their order is.

---

## Definition of Done (plan §9 Phase 1b)

- [ ] graphix.uz serves over HTTPS
- [ ] a real Click payment completes and the order flips to `paid`
- [ ] an OTP SMS arrives branded GRAPHIX
- [ ] the OG image renders when the link is pasted into Telegram
- [ ] Redis is live and the rate limiter counts correctly across workers
- [ ] `restore-check.sh` exits 0 against an off-server copy

Then record it: §15 tracker, §16 session log, and any decision that came out of
the day in §17. An out-of-date plan makes the next chat worse.
