#!/usr/bin/env bash
# GRAPHIX - nightly backup of the database and the photographs.
#
# Plan §9 Phase 1b item 8 and §12 risk #19: the database dump alone is not
# enough, because product and review photography is irreplaceable and lives on
# disk, not in PostgreSQL.
#
# What it does, in order:
#   1. reads the database credentials from the application's own .env, so
#      there is one copy of that password on the machine and not two;
#   2. writes a compressed custom-format dump, plus a sidecar file of exact row
#      counts that restore-check.sh compares against;
#   3. snapshots media/ with rsync --link-dest, so an unchanged photograph is
#      hard-linked to yesterday's copy and costs no disk at all;
#   4. deletes snapshots older than KEEP_DAYS;
#   5. copies everything off this machine.
#
# Step 5 is not optional. If BACKUP_REMOTE is unset the script exits non-zero
# and the systemd unit goes red, because a backup that only exists on the
# server it is backing up survives exactly none of the events worth backing up
# for, and a job that reports success while doing that is worse than no job.
#
# Run by graphix-backup.timer. Safe to run by hand at any time.

set -euo pipefail

APP_DIR=${APP_DIR:-/srv/graphix}
BACKUP_DIR=${BACKUP_DIR:-/srv/graphix-backups}
CONFIG=${CONFIG:-$BACKUP_DIR/backup.env}
KEEP_DAYS=${KEEP_DAYS:-14}

STAMP=$(date +%Y%m%d-%H%M%S)
DB_OUT=$BACKUP_DIR/db
MEDIA_OUT=$BACKUP_DIR/media

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf 'backup: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- settings
# BACKUP_REMOTE is an rsync destination: user@host:/path/to/graphix-backups
# It is kept out of the repository because it names another machine.
# shellcheck source=/dev/null
[ -f "$CONFIG" ] && . "$CONFIG"

# ------------------------------------------------- database credentials
# Read straight out of the app's .env rather than duplicated here. Only the
# keys we need, and only the first match of each, so a commented-out line
# cannot shadow a real one.
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

mkdir -p "$DB_OUT" "$MEDIA_OUT"

# ------------------------------------------------------------ row counts
# EXACT counts, not pg_stat_user_tables.n_live_tup. That column is an estimate
# and reads 0 for a table the planner has not looked at yet: a table holding
# five hundred rows measured as zero while this script was being written, which
# would have let restore-check.sh pass a restore that lost all five hundred.
#
# query_to_xml runs a real count(*) per table in one statement, so the whole
# thing is a single round trip whatever the schema grows into.
table_counts() {
    psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
         --dbname="$DB_NAME" --tuples-only --no-align --field-separator=$'\t' \
         --command="
            SELECT relname,
                   (xpath('/row/c/text()',
                          query_to_xml(format('SELECT count(*) AS c FROM %I.%I',
                                              schemaname, relname),
                                       false, true, '')))[1]::text::bigint
            FROM pg_stat_user_tables
            ORDER BY relname;"
}

# ------------------------------------------------------------ the dump
# Counted either side of the dump. pg_dump takes its snapshot when it starts,
# so the BEFORE counts are what the dump holds; if the AFTER counts agree,
# nothing was written while it ran and the sidecar describes the dump exactly.
# If they disagree - somebody ordered a t-shirt at half past three - the
# sidecar records the lower of the two and says so, and restore-check.sh
# relaxes from "exactly this many" to "at least this many".
log "counting rows"
COUNTS_BEFORE=$(table_counts)

log "dumping $DB_NAME"
DUMP=$DB_OUT/graphix-$STAMP.dump
pg_dump --format=custom --compress=6 \
        --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" \
        --dbname="$DB_NAME" --file="$DUMP"
log "dump written: $(du -h "$DUMP" | cut -f1)"

COUNTS_AFTER=$(table_counts)
SIDECAR=$DB_OUT/graphix-$STAMP.counts
if [ "$COUNTS_BEFORE" = "$COUNTS_AFTER" ]; then
    printf '#exact\n%s\n' "$COUNTS_BEFORE" > "$SIDECAR"
    log "counted $(printf '%s\n' "$COUNTS_BEFORE" | wc -l) tables, exact"
else
    # Per table, the smaller of the two readings. paste keeps them aligned;
    # if the table lists themselves differ (a migration ran mid-dump) fall
    # back to the before-counts and let restore-check treat them as a floor.
    if [ "$(printf '%s\n' "$COUNTS_BEFORE" | cut -f1)" \
       = "$(printf '%s\n' "$COUNTS_AFTER" | cut -f1)" ]; then
        lower=$(paste <(printf '%s\n' "$COUNTS_BEFORE") \
                      <(printf '%s\n' "$COUNTS_AFTER") \
                | awk -F'\t' '{print $1 "\t" ($2 < $4 ? $2 : $4)}')
    else
        lower=$COUNTS_BEFORE
    fi
    printf '#raced\n%s\n' "$lower" > "$SIDECAR"
    log "counted $(printf '%s\n' "$lower" | wc -l) tables; the database changed"
    log "  while the dump ran, so the counts are a floor rather than a match"
fi

# --------------------------------------------------------- the photographs
# --link-dest against the newest existing snapshot: identical files become
# hard links, so fourteen nights of a 2 GB media folder cost 2 GB plus what
# actually changed.
PREVIOUS=$(find "$MEDIA_OUT" -maxdepth 1 -mindepth 1 -type d | sort | tail -1 || true)
LINK_ARG=()
[ -n "$PREVIOUS" ] && LINK_ARG=(--link-dest="$PREVIOUS")
log "snapshotting media${PREVIOUS:+ (linked against $(basename "$PREVIOUS"))}"
rsync --archive --delete "${LINK_ARG[@]}" \
      "$APP_DIR/media/" "$MEDIA_OUT/$STAMP/"
log "media snapshot: $(du -sh "$MEDIA_OUT/$STAMP" | cut -f1) apparent"

# ------------------------------------------------------------- retention
log "pruning older than $KEEP_DAYS days"
find "$DB_OUT" -maxdepth 1 -type f -name 'graphix-*' -mtime "+$KEEP_DAYS" -delete
find "$MEDIA_OUT" -maxdepth 1 -mindepth 1 -type d -mtime "+$KEEP_DAYS" \
     -exec rm -rf {} +

# ------------------------------------------------------------ off-server
if [ -z "${BACKUP_REMOTE:-}" ]; then
    die "BACKUP_REMOTE is not set in $CONFIG - nothing has left this machine.
     Everything above succeeded and is on local disk, which protects you from
     a bad migration and from nothing else. Set BACKUP_REMOTE to an rsync
     destination (user@host:/path) and re-run."
fi

log "copying to $BACKUP_REMOTE"
rsync --archive --hard-links --delete --partial \
      --rsh="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
      "$BACKUP_DIR/db" "$BACKUP_DIR/media" "$BACKUP_REMOTE/"
log "off-server copy complete"
log "done"
