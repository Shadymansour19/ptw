#!/usr/bin/env bash
# Restores a PTW backup produced by backup.sh. DESTRUCTIVE: drops and
# recreates the database, and overwrites file-storage directories.
# Stop the server before running this.
#
# Usage: ./restore.sh /path/to/ptw-backups/20260801_020000
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${1:?Usage: restore.sh /path/to/backup/TIMESTAMP}"

env_get() { grep -E "^$1=" "$SERVER_DIR/.env" | head -1 | cut -d'=' -f2-; }
DB_HOST="$(env_get DB_HOST)"
DB_NAME="$(env_get DB_NAME)"
DB_USER="$(env_get DB_USER)"
DB_PASSWORD="$(env_get DB_PASSWORD)"

[ -f "$BACKUP_DIR/${DB_NAME}.dump" ] || { echo "No ${DB_NAME}.dump in $BACKUP_DIR"; exit 1; }
[ -f "$BACKUP_DIR/files.tar.gz" ] || { echo "No files.tar.gz in $BACKUP_DIR"; exit 1; }

echo "This will DROP the current '$DB_NAME' database and overwrite file storage in $SERVER_DIR."
read -p "Type 'yes' to continue: " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 1; }

echo "Restoring database..."
PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -U "$DB_USER" --if-exists "$DB_NAME"
PGPASSWORD="$DB_PASSWORD" createdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME"
PGPASSWORD="$DB_PASSWORD" pg_restore -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" "$BACKUP_DIR/${DB_NAME}.dump"

echo "Restoring file storage..."
tar -xzf "$BACKUP_DIR/files.tar.gz" -C "$SERVER_DIR"

echo "Restore complete. Start the server again."
