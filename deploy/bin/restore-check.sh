#!/usr/bin/env bash
# GRAPHIX - prove the backup restores (plan §9 Phase 1b item 8, Phase 10 item 10).
#
# "An untested backup is not a backup" is in the plan twice, and this is the
# thing that makes it true rather than a sentence. It restores the newest dump
# into a throwaway database, compares what came back against the row counts
# recorded when the dump was taken, and drops the scratch database again.
# Those counts are exact counts of every table, not estimates, so "the same
# number came back" means exactly that.
#
# It is deliberately paranoid about the one way this script could hurt you: it
# refuses to touch any database whose name is not the scratch name, so a typo
# cannot point pg_restore at production. The live database is only ever READ.
#
# Run it by hand after the first backup, and again whenever anything about the
# database changes. Exit code 0 means the backup is real.

set -euo pipefail

APP_DIR=${APP_DIR:-/srv/graphix}
BACKUP_DIR=${BACKUP_DIR:-/srv/graphix-backups}
SCRATCH=graphix_restorecheck

# Tables that must EXIST in the restored database. A dump without these is a
# dump of something else, whatever pg_restore said about it.
#
# Their being empty is not checked here, and deliberately: whether a table lost
# its rows is already decided, exactly, by comparing it against the count taken
# when the dump was made. Failing on "empty" as well would mean a brand-new
# installation - no products, no customers, no orders yet - reporting that its
# backups do not work, which is both wrong and the worst possible moment to
# cry wolf.
MUST_HAVE=(product_product product_variant payment_order user_user)

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf 'restore-check: %s\n' "$*" >&2; exit 1; }

case "$SCRATCH" in
    graphix_restorecheck) ;;
    *) die "scratch database must be named graphix_restorecheck, got '$SCRATCH'" ;;
esac

# ------------------------------------------------- database credentials
env_value() {
    local key=$1 line
    line=$(grep -m1 "^${key}=" "$APP_DIR/.env" 2>/dev/null) || return 1
    printf '%s' "${line#*=}" | sed -e 's/^"//' -e "s/^'//" -e 's/"$//' -e "s/'$//"
}
[ -r "$APP_DIR/.env" ] || die "cannot read $APP_DIR/.env"
DB_NAME=$(env_value DB_NAME) || die "DB_NAME not in .env"
DB_USER=$(env_value DB_USER) || die "DB_USER not in .env"
DB_HOST=$(env_value DB_HOST || true); DB_HOST=${DB_HOST:-localhost}
DB_PORT=$(env_value DB_PORT || true); DB_PORT=${DB_PORT:-5432}
PGPASSWORD=$(env_value DB_PASSWORD) || die "DB_PASSWORD not in .env"
export PGPASSWORD
# Keep psql to warnings and errors: "database does not exist, skipping" is
# a notice, and a check that prints noise on a good run teaches you to stop
# reading it.
export PGOPTIONS="-c client_min_messages=warning"

[ "$DB_NAME" != "$SCRATCH" ] || die "the live database is called '$SCRATCH' - stop"

PSQL=(psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER"
      --tuples-only --no-align --quiet)

# Count one table in one database. Prints MISSING if the table is not there.
count_in() {
    "${PSQL[@]}" --dbname="$1" --command="SELECT count(*) FROM \"$2\";" \
        2>/dev/null || echo MISSING
}

# --------------------------------------------------------- the newest dump
DUMP=$(find "$BACKUP_DIR/db" -maxdepth 1 -type f -name 'graphix-*.dump' \
       | sort | tail -1)
[ -n "$DUMP" ] || die "no dump found in $BACKUP_DIR/db"
COUNTS=${DUMP%.dump}.counts
[ -r "$COUNTS" ] || die "no sidecar counts beside $(basename "$DUMP")"
log "checking $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"

# backup.sh writes '#exact' when nothing was written to the database while the
# dump ran, and '#raced' when something was. Exact means every table must come
# back with the same number; raced means the counts are a floor.
MODE=$(head -1 "$COUNTS")
case "$MODE" in
    '#exact') log "the sidecar is exact - every count must match" ;;
    '#raced') log "the database changed while the dump ran - counts are a floor" ;;
    *) die "sidecar has no mode line; it was written by an older backup.sh" ;;
esac

# ------------------------------------------------------------- restore
cleanup() {
    "${PSQL[@]}" --dbname=postgres \
        --command="DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "creating $SCRATCH"
"${PSQL[@]}" --dbname=postgres --command="DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null
"${PSQL[@]}" --dbname=postgres --command="CREATE DATABASE $SCRATCH;" >/dev/null

log "restoring"
# --exit-on-error so a half-restored database cannot pass as a good one.
pg_restore --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
           --dbname="$SCRATCH" --no-owner --no-privileges --exit-on-error \
           "$DUMP"
log "pg_restore returned 0"

# ------------------------------------------------------------ the counts
fail=0
printf '\n  %-34s %10s %10s   %s\n' TABLE 'AT DUMP' RESTORED ''
printf '  %s\n' '--------------------------------------------------------------------'
while IFS=$'\t' read -r table expected; do
    [ -n "$table" ] || continue
    actual=$(count_in "$SCRATCH" "$table")
    note=''
    if [ "$actual" = MISSING ]; then
        note='TABLE MISSING'; fail=1
    elif [ "$actual" -lt "$expected" ]; then
        note='SHORT'; fail=1
    elif [ "$actual" -gt "$expected" ] && [ "$MODE" = '#exact' ]; then
        # More rows than were dumped is not a happy surprise: it means this
        # dump is not of the database the sidecar describes.
        note='MORE THAN DUMPED'; fail=1
    fi
    printf '  %-34s %10s %10s   %s\n' "$table" "$expected" "$actual" "$note"
done < <(tail -n +2 "$COUNTS")
printf '\n'

rows=0
for table in "${MUST_HAVE[@]}"; do
    n=$(count_in "$SCRATCH" "$table")
    if [ "$n" = MISSING ]; then
        printf 'restore-check: %s is absent from the restored database\n' "$table" >&2
        fail=1
    else
        rows=$((rows + n))
    fi
done
if [ "$rows" -eq 0 ]; then
    log "note: no products, customers or orders yet - this checks that the"
    log "      backup machinery works, not that it saved anything valuable"
fi

# One real row, end to end. Row counts prove the shape restored; this proves the
# bytes did. The live database is read and nothing else.
#
# The column is `total_price`. It read `total` until 2026-09-23, and the error
# was invisible for four days because this branch only runs once an order
# exists - on 2026-09-19 there were none, the `else` below ran, and the script
# printed "restore verified" having skipped the one assertion that reads a
# real value out of a restored dump. Same shape as §17 #248: a check that
# passed because the thing it checks was not there.
order_no=$("${PSQL[@]}" --dbname="$SCRATCH" --command="
    SELECT order_no FROM payment_order ORDER BY id DESC LIMIT 1;" | head -1)
if [ -n "$order_no" ]; then
    restored=$("${PSQL[@]}" --dbname="$SCRATCH" --command="
        SELECT total_price FROM payment_order WHERE order_no = '$order_no';" | head -1)
    live=$("${PSQL[@]}" --dbname="$DB_NAME" --command="
        SELECT total_price FROM payment_order WHERE order_no = '$order_no';" | head -1)
    if [ "$live" = "$restored" ]; then
        log "spot check: order $order_no restored with total $restored"
    else
        printf 'restore-check: order %s restored as %s, live says %s\n' \
               "$order_no" "$restored" "$live" >&2
        fail=1
    fi
else
    log "spot check skipped: no orders in the dump yet"
fi

[ "$fail" -eq 0 ] || die "the restore did NOT check out - see above"
log "restore verified"
