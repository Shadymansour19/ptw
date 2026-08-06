#!/usr/bin/env bash
# Restores a PTW backup produced by backup.sh. DESTRUCTIVE: drops and
# recreates the database, and overwrites file-storage directories.
# Stop the server before running this.
#
# Usage: ./restore.sh /path/to/ptw-backups/20260801_020000
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$(cd "$SERVER_DIR" && python3 -c "from paths import DATA_DIR; print(DATA_DIR)")"
BACKUP_DIR="${1:?Usage: restore.sh /path/to/backup/TIMESTAMP}"

env_get() { grep -E "^$1=" "$SERVER_DIR/.env" | head -1 | cut -d'=' -f2-; }
DB_HOST="$(env_get DB_HOST)"
DB_NAME="$(env_get DB_NAME)"
DB_USER="$(env_get DB_USER)"
DB_PASSWORD="$(env_get DB_PASSWORD)"

[ -f "$BACKUP_DIR/${DB_NAME}.dump" ] || { echo "No ${DB_NAME}.dump in $BACKUP_DIR"; exit 1; }
[ -f "$BACKUP_DIR/files.tar.gz" ] || { echo "No files.tar.gz in $BACKUP_DIR"; exit 1; }

echo "This will DROP the current '$DB_NAME' database and overwrite file storage in $DATA_DIR (and .env in $SERVER_DIR)."
read -p "Type 'yes' to continue: " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 1; }

echo "Restoring database..."
PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -U "$DB_USER" --if-exists "$DB_NAME"
PGPASSWORD="$DB_PASSWORD" createdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME"
PGPASSWORD="$DB_PASSWORD" pg_restore -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" "$BACKUP_DIR/${DB_NAME}.dump"

echo "Restoring file storage..."
# The archive is flat (.env alongside miwi/ and *-attachments/) but those now live in two
# different real directories - extract to a scratch dir, then route each entry home.
TMP_EXTRACT="$(mktemp -d)"
trap 'rm -rf "$TMP_EXTRACT"' EXIT
tar -xzf "$BACKUP_DIR/files.tar.gz" -C "$TMP_EXTRACT"
mkdir -p "$DATA_DIR"
[ -e "$TMP_EXTRACT/.env" ] && mv -f "$TMP_EXTRACT/.env" "$SERVER_DIR/.env"
for entry in "$TMP_EXTRACT"/*; do
    [ -e "$entry" ] || continue
    rm -rf "$DATA_DIR/$(basename "$entry")"
    mv "$entry" "$DATA_DIR/"
done

echo "Restore complete. Start the server again."
