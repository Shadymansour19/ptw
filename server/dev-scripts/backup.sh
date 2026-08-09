#!/usr/bin/env bash
# Backs up the PTW database and server-side file storage (MIWI docs + PTW/IC
# attachments) into a single timestamped directory. Prunes backups older than
# RETENTION_DAYS. Safe to run while the server is up (pg_dump and tar both
# take a consistent read-only snapshot).
#
# Usage: ./backup.sh [backup_root]
#   backup_root defaults to paths.BACKUP_DIR (the same on-disk location the
#   in-app Admin "Backups" tab / POST /backups already writes to - see
#   server/backupService.py). Pass an explicit path to back up somewhere else
#   (e.g. off this machine's disk entirely, which is the point of running this
#   on a schedule rather than relying on the in-app button alone).
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t _PTW_PATHS < <(cd "$SERVER_DIR" && python3 -c "from paths import DATA_DIR, BACKUP_DIR; print(DATA_DIR); print(BACKUP_DIR)")
DATA_DIR="${_PTW_PATHS[0]}"
BACKUP_ROOT="${1:-${_PTW_PATHS[1]}}"
RETENTION_DAYS=14
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$BACKUP_ROOT/$TIMESTAMP"

env_get() { grep -E "^$1=" "$SERVER_DIR/.env" | head -1 | cut -d'=' -f2-; }
DB_HOST="$(env_get DB_HOST)"
DB_NAME="$(env_get DB_NAME)"
DB_USER="$(env_get DB_USER)"
DB_PASSWORD="$(env_get DB_PASSWORD)"

mkdir -p "$DEST"

echo "[$TIMESTAMP] Dumping database $DB_NAME..."
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$DEST/${DB_NAME}.dump"

# .env lives beside the code (SERVER_DIR); MIWI docs + grouped PTW/IC attachment folders
# (ptws/, ics/) live under DATA_DIR (server/paths.py) - GNU tar accepts multiple -C switches
# to pull members from different real directories into one archive, and adding a directory
# pulls in its contents recursively.
echo "[$TIMESTAMP] Archiving file storage..."
cd "$DATA_DIR"
DATA_TARGETS=()
[ -d miwi ] && DATA_TARGETS+=(miwi)
[ -d ptws ] && DATA_TARGETS+=(ptws)
[ -d ics ] && DATA_TARGETS+=(ics)
tar -czf "$DEST/files.tar.gz" -C "$SERVER_DIR" .env -C "$DATA_DIR" "${DATA_TARGETS[@]}"

echo "[$TIMESTAMP] Backup complete: $DEST"
du -sh "$DEST"

find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;
