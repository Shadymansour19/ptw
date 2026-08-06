import os
import logging
import threading
from time import sleep
from dotenv import load_dotenv
from flask import Flask, request
from flask_mail import Mail

from db.commonDb import CommonDB
from db.usersDb import UsersDb
from db.ptwDb import PtwsDb
from db.risksDb import RisksDb
from db.ICDb import ICDb
from GlobalData import globalData
from loggingSetup import setupLogging

load_dotenv()

setupLogging()
log = logging.getLogger("app")

CommonDB.ensure_database_exists()
app = Flask(__name__)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD')
)
mail = Mail(app)

_DB_PERIODIC_REFRESH_INTERVAL = 5 * 60


@app.before_request
def _log_request():
    log.debug("%s %s", request.method, request.path)


try:
    log.info("Initializing databases...")
    CommonDB.init_pool()
    userDB = UsersDb()
    ptwDB = PtwsDb()
    risksDB = RisksDb()
    icDB = ICDb()
    globalData.refresh(userDB, ptwDB, icDB)
    log.info("All databases initialized successfully")
except Exception as e:
    log.critical("Database initialization failed: %s", e, exc_info=True)
    exit(1)


def syncPtwCache(ptw_id):
    """Re-reads a PTW from the DB into globalData.allPTWs — shared by routes/ptws.py's own
    mutations and routes/ics.py's link/unlink handlers, which also touch PTW state."""
    updated = ptwDB.getPTWById(ptw_id)
    if updated:
        with globalData.lock:
            globalData.allPTWs[updated.id] = updated
        log.debug("PTW #%s synced from DB", ptw_id)
    else:
        log.warning("PTW #%s not found in DB during sync", ptw_id)


def _periodic_refresh():
    while True:
        sleep(_DB_PERIODIC_REFRESH_INTERVAL)
        try:
            globalData.refresh(userDB, ptwDB, icDB)
            log.info("Periodic DB resync completed")
        except Exception as e:
            log.error("Periodic DB resync failed: %s", e, exc_info=True)


threading.Thread(target=_periodic_refresh, daemon=True, name="globaldata-refresh").start()
log.info("Periodic DB resync thread started (interval: 5 min)")
