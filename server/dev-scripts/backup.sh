#!/usr/bin/env bash
# Backs up the PTW database and server-side file storage (MIWI docs + PTW/IC
# attachments) into a single timestamped directory. Prunes backups older than
# RETENTION_DAYS. Safe to run while the server is up (pg_dump and tar both
# take a consistent read-only snapshot).
#
# Usage: ./backup.sh [backup_root]
#   backup_root defaults to /home/shady/ptw-backups
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${1:-/home/shady/ptw-backups}"
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

echo "[$TIMESTAMP] Archiving file storage..."
cd "$SERVER_DIR"
FILE_TARGETS=(.env)
[ -d miwi ] && FILE_TARGETS+=(miwi)
for d in ptw-*-attachments ic-*-attachments; do
    [ -d "$d" ] && FILE_TARGETS+=("$d")
done
tar -czf "$DEST/files.tar.gz" "${FILE_TARGETS[@]}"

echo "[$TIMESTAMP] Backup complete: $DEST"
du -sh "$DEST"

find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;
