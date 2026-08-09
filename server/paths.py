"""Filesystem layout for the server: BASE_DIR is the checked-out/deployed code
location (this file's directory, or the frozen executable's directory when built
as a Nuitka/PyInstaller onefile binary) and never receives generated content.
DATA_DIR is the separate, per-machine location for everything generated or
uploaded at runtime (MIWI documents, PTW/IC attachments, logs, DB backups) —
it defaults to an OS-appropriate per-machine data directory (see
_defaultDataDir()) but can be overridden wholesale via the PTW_DATA_DIR
environment variable."""

import os
import sys

from models.User import UserDepartments

# Resolve the directory that contains this file (works both as a plain script and
# as a Nuitka/PyInstaller onefile binary, regardless of the process's CWD). This is
# where the *code* (and .env, which is config, not data) lives — nothing else should
# be written here. See DATA_DIR below for where generated/uploaded content goes.
BASE_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False) else os.path.abspath(__file__))


def _defaultDataDir() -> str:
    """OS-appropriate per-machine data directory, used unless PTW_DATA_DIR overrides it.
    Deliberately NOT BASE_DIR-relative: BASE_DIR is the checked-out/deployed code location
    (server/ in this repo), and generated content (MIWI uploads, attachments, logs, DB
    backups — some of it containing real user data and PII) has no business living inside
    a git-tracked source tree, where a stray `git add -A` or a zipped copy of the repo would
    sweep it up. On Windows this also avoids trying to write under a possibly read-only
    Program Files install directory."""
    if os.name == 'nt':
        root = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        return os.path.join(root, 'PTW', 'server')
    root = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(root, 'ptw-server')


DATA_DIR = os.environ.get('PTW_DATA_DIR') or _defaultDataDir()
MIWI_DIR = os.path.join(DATA_DIR, 'miwi')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
# Per-record attachment folders are grouped one level down by resource, instead of sitting
# loose in DATA_DIR's root — DATA_DIR/ptws/ptw-<id>-attachments/, not DATA_DIR/ptw-<id>-attachments/.
PTWS_DIR = os.path.join(DATA_DIR, 'ptws')
ICS_DIR = os.path.join(DATA_DIR, 'ics')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MIWI_DIR, exist_ok=True)
os.makedirs(PTWS_DIR, exist_ok=True)
os.makedirs(ICS_DIR, exist_ok=True)
MIWI_DEPARTMENTS = {d.value for d in UserDepartments}


_ATTACHMENT_GROUP_DIRS = {'ptw': PTWS_DIR, 'ic': ICS_DIR}


def attachmentsDir(kind: str, recordId) -> str:
    """Per-record attachment folder for a resource kind ('ptw', 'ic', ...), grouped under
    its own DATA_DIR subfolder - e.g. attachmentsDir('ptw', 30) -> PTWS_DIR/ptw-30-attachments.
    Add new kinds by extending _ATTACHMENT_GROUP_DIRS (and creating the group dir above)."""
    return os.path.join(_ATTACHMENT_GROUP_DIRS[kind], f'{kind}-{recordId}-attachments')


def resolveMiwiPath(filename: str, department: str = None) -> str:
    """Find `filename` under the MIWI store. `department` is preferred but the
    legacy flat layout and every other department folder are also searched —
    any authenticated user may review a MIWI belonging to any department.
    """
    candidateDirs = []
    if department in MIWI_DEPARTMENTS:
        candidateDirs.append(os.path.join(MIWI_DIR, department))
    candidateDirs.append(MIWI_DIR)
    candidateDirs.extend(os.path.join(MIWI_DIR, d) for d in MIWI_DEPARTMENTS if d != department)
    for dirpath in candidateDirs:
        filepath = os.path.abspath(os.path.join(dirpath, filename))
        if not filepath.startswith(os.path.abspath(MIWI_DIR)):
            continue
        if os.path.isfile(filepath):
            return filepath
    return None
