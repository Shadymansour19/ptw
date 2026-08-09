"""Root logger configuration: console + rotating file handlers under LOGS_DIR,
sharing one format that includes the logger/function/line origin of each record."""

import os
import logging
from logging.handlers import RotatingFileHandler

from paths import LOGS_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(location)-35s - %(message)s"
_LOG_DATE = "%Y-%m-%d %H:%M:%S"


class _Formatter(logging.Formatter):
    """Log formatter that adds a 'location' field (logger:function:line) to each record."""

    def format(self, record):
        """Populate record.location before delegating to the base formatter."""
        record.location = f"{record.name}:{record.funcName}:{record.lineno}"
        return super().format(record)


def setupLogging():
    """Configure the root logger with a DEBUG console handler and a rotating
    DEBUG file handler (ptw-server.log, 10MB x5 backups) under LOGS_DIR, and
    quiet werkzeug's own request logging down to WARNING."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = _Formatter(_LOG_FORMAT, datefmt=_LOG_DATE)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)
    root.addHandler(console)

    os.makedirs(LOGS_DIR, exist_ok=True)
    fh = RotatingFileHandler(os.path.join(LOGS_DIR, 'ptw-server.log'), maxBytes=10 * 1024 * 1024, backupCount=5)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
