import os
import logging
from logging.handlers import RotatingFileHandler

from paths import LOGS_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(location)-35s - %(message)s"
_LOG_DATE = "%Y-%m-%d %H:%M:%S"


class _Formatter(logging.Formatter):
    def format(self, record):
        record.location = f"{record.name}:{record.funcName}:{record.lineno}"
        return super().format(record)


def setupLogging():
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
