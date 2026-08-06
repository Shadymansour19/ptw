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
    if not _BACKUP_NAME_RE.match(name or ''):
        raise ValueError("Invalid backup name")
    path = os.path.abspath(os.path.join(BACKUP_DIR, name))
    if not path.startswith(os.path.abspath(BACKUP_DIR)):
        raise ValueError("Invalid backup name")
    return path


def deleteBackup(name: str):
    path = resolveBackupDir(name)
    if not os.path.isdir(path):
        raise ValueError("Backup not found")
    shutil.rmtree(path)


def backupFilePath(name: str, which: str) -> str:
    dest = resolveBackupDir(name)
    _, dbName, _, _ = _dbConfig()
    if which == 'dump':
        return os.path.join(dest, f'{dbName}.dump')
    if which == 'files':
        return os.path.join(dest, 'files.tar.gz')
    raise ValueError("Invalid file requested")
