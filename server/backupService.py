"""On-demand backup helpers backing GET/POST/DELETE /backups: POST triggers
createBackup(), which pg_dump -Fc's the database and tars/gzips the MIWI store
and PTW/IC attachment folders into a timestamped BACKUP_DIR subfolder; GET lists
or downloads existing backups; DELETE removes one. Mirrors the on-disk layout
produced by dev-scripts/backup.sh|.ps1 so backups from either path are
interchangeable with dev-scripts/restore.sh|.ps1."""

import os
import re
import shutil
import tarfile
import subprocess
from datetime import datetime

from paths import BASE_DIR, MIWI_DIR, PTWS_DIR, ICS_DIR, BACKUP_DIR

_BACKUP_NAME_RE = re.compile(r'^\d{8}_\d{6}$')   # YYYYMMDD_HHMMSS, matches dev-scripts/backup.sh|.ps1
_BACKUP_RETENTION_DAYS = 14                        # matches dev-scripts/backup.sh|.ps1 pruning


def _dbConfig() -> tuple[str, str, str, str]:
    """Return the (host, dbName, dbUser, dbPassword) tuple from environment
    variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD), applying the same
    localhost/ptw_database/postgres defaults used elsewhere for the DB connection."""
    return (
        os.environ.get('DB_HOST', 'localhost'),
        os.environ.get('DB_NAME', 'ptw_database'),
        os.environ.get('DB_USER', 'postgres'),
        os.environ.get('DB_PASSWORD'),
    )


def _backupTargets() -> list[tuple[str, str]]:
    """(absolute source path, arcname) pairs to include in a backup's files.tar.gz - mirrors
    dev-scripts/backup.sh|.ps1's file-target selection exactly, so backups made from either
    path are interchangeable. `.env` lives beside the code (BASE_DIR); the MIWI store and the
    grouped PTW/IC attachment folders (paths.PTWS_DIR/ICS_DIR) live under DATA_DIR."""
    targets = [(os.path.join(BASE_DIR, '.env'), '.env')]
    if os.path.isdir(MIWI_DIR):
        targets.append((MIWI_DIR, 'miwi'))
    if os.path.isdir(PTWS_DIR):
        targets.append((PTWS_DIR, 'ptws'))
    if os.path.isdir(ICS_DIR):
        targets.append((ICS_DIR, 'ics'))
    return targets


def _backupRow(name: str) -> dict:
    """Build the summary dict (name, created timestamp, dump/files/total sizes
    in bytes, and whether both the dump and files archive are present) for the
    named backup folder under BACKUP_DIR."""
    dest = os.path.join(BACKUP_DIR, name)
    _, dbName, _, _ = _dbConfig()
    dumpPath = os.path.join(dest, f'{dbName}.dump')
    filesPath = os.path.join(dest, 'files.tar.gz')
    dumpSize = os.path.getsize(dumpPath) if os.path.isfile(dumpPath) else 0
    filesSize = os.path.getsize(filesPath) if os.path.isfile(filesPath) else 0
    return {
        "name": name,
        "created": datetime.strptime(name, '%Y%m%d_%H%M%S').isoformat(),
        "dumpSizeBytes": dumpSize,
        "filesSizeBytes": filesSize,
        "totalSizeBytes": dumpSize + filesSize,
        "complete": dumpSize > 0 and filesSize > 0,
    }


def createBackup() -> dict:
    """Dumps the database and archives file storage into a fresh
    BACKUP_DIR/<timestamp>/ folder - same <dbname>.dump + files.tar.gz layout
    dev-scripts/backup.sh|.ps1 produce, so restore.sh|.ps1 work on either."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(BACKUP_DIR, timestamp)
    os.makedirs(dest, exist_ok=True)

    host, dbName, dbUser, dbPassword = _dbConfig()
    dumpPath = os.path.join(dest, f'{dbName}.dump')
    try:
        subprocess.run(
            ['pg_dump', '-h', host, '-U', dbUser, '-d', dbName, '-Fc', '-f', dumpPath],
            env={**os.environ, 'PGPASSWORD': dbPassword or ''},
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pg_dump failed: {e.stderr.strip()}") from e
    except FileNotFoundError as e:
        raise RuntimeError("pg_dump not found on server PATH") from e

    with tarfile.open(os.path.join(dest, 'files.tar.gz'), 'w:gz') as tf:
        for sourcePath, arcname in _backupTargets():
            tf.add(sourcePath, arcname=arcname)

    return _backupRow(timestamp)


def listBackups() -> dict:
    """List all backup folders under BACKUP_DIR matching the timestamp naming
    convention, newest first, alongside retention policy and free disk space.

    Returns:
        dict with "backups" (list of _backupRow() summaries), "retentionDays",
        "freeBytes" (None if BACKUP_DIR doesn't exist), and "lastBackupAt".
    """
    rows = []
    if os.path.isdir(BACKUP_DIR):
        for entry in os.listdir(BACKUP_DIR):
            if _BACKUP_NAME_RE.match(entry) and os.path.isdir(os.path.join(BACKUP_DIR, entry)):
                rows.append(_backupRow(entry))
    rows.sort(key=lambda r: r["name"], reverse=True)
    return {
        "backups": rows,
        "retentionDays": _BACKUP_RETENTION_DAYS,
        "freeBytes": shutil.disk_usage(BACKUP_DIR).free if os.path.isdir(BACKUP_DIR) else None,
        "lastBackupAt": rows[0]["created"] if rows else None,
    }


def resolveBackupDir(name: str) -> str:
    """Validate a backup name against the timestamp pattern and resolve it to
    an absolute path confined under BACKUP_DIR, guarding against path traversal.

    Raises:
        ValueError: if the name doesn't match the expected pattern or would
            resolve outside BACKUP_DIR.
    """
    if not _BACKUP_NAME_RE.match(name or ''):
        raise ValueError("Invalid backup name")
    path = os.path.abspath(os.path.join(BACKUP_DIR, name))
    if not path.startswith(os.path.abspath(BACKUP_DIR)):
        raise ValueError("Invalid backup name")
    return path


def deleteBackup(name: str):
    """Remove the named backup folder (and everything in it) from BACKUP_DIR.

    Raises:
        ValueError: if the name is invalid or the backup doesn't exist.
    """
    path = resolveBackupDir(name)
    if not os.path.isdir(path):
        raise ValueError("Backup not found")
    shutil.rmtree(path)


def backupFilePath(name: str, which: str) -> str:
    """Return the path to a specific file ('dump' or 'files') within the named
    backup, for download.

    Raises:
        ValueError: if the backup name is invalid or `which` isn't recognized.
    """
    dest = resolveBackupDir(name)
    _, dbName, _, _ = _dbConfig()
    if which == 'dump':
        return os.path.join(dest, f'{dbName}.dump')
    if which == 'files':
        return os.path.join(dest, 'files.tar.gz')
    raise ValueError("Invalid file requested")
