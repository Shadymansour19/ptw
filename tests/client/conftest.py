"""Client-test harness: headless Qt, no network.

`QT_QPA_PLATFORM=offscreen` is forced before pytest-qt creates the QApplication, so every
widget test renders to an offscreen buffer (deterministic, no display needed). Nothing in
here touches the network: the fixtures below replace the SSE listener and the cache refresh
so a role window can be built exactly as `main.py` would build it, but fed from the
in-memory `globalData` the test populated.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('PTW_SERVER_URL', 'http://127.0.0.1:9')   # discard port - any accidental request fails fast

import pytest  # noqa: E402

import helper.i18n as i18n  # noqa: E402
from GlobalData import globalData  # noqa: E402
from models.User import User, UserRoles, UserDepartments  # noqa: E402

i18n.init('en')


@pytest.fixture(autouse=True)
def clean_global_data():
    """Every test starts with an empty client cache and leaves it empty."""
    for attr in ('allUsers', 'allRiskAssessments', 'allPTWs', 'archivedPTWs', 'ics'):
        getattr(globalData, attr).clear()
    globalData.allMIWIs.clear()
    yield
    for attr in ('allUsers', 'allRiskAssessments', 'allPTWs', 'archivedPTWs', 'ics'):
        getattr(globalData, attr).clear()
    globalData.allMIWIs.clear()


def make_user(username='user_turbo', role=UserRoles.USER, department=UserDepartments.TURBO, name=None) -> User:
    return User(username=username, password='pw', name=name or username.replace('_', ' ').title(),
                role=role, department=str(department) if department is not None else '', email='')


@pytest.fixture
def user():
    return make_user()


@pytest.fixture
def known_users():
    """A user directory with one account per approval role, loaded into globalData.allUsers."""
    users = {
        'user_turbo': make_user(),
        'user_mech': make_user('user_mech', department=UserDepartments.MECH),
        'coord': make_user('coord', UserRoles.COORDINATOR, UserDepartments.PROD),
        'issuing': make_user('issuing', UserRoles.ISSUING, UserDepartments.PROD),
        'hse': make_user('hse', UserRoles.HSE_ENGINEER, UserDepartments.HSE),
        'pgm': make_user('pgm', UserRoles.PGM, UserDepartments.PROD),
        'dfgm': make_user('dfgm', UserRoles.DFGM, UserDepartments.PROD),
        'gas': make_user('gas', UserRoles.GAS_TESTER, UserDepartments.PROD),
    }
    globalData.allUsers.update(users)
    return users


@pytest.fixture
def offline_window(qtbot, monkeypatch):
    """Factory: build a role window with the SSE listener and server refresh stubbed out.

    The stubbed refresh calls its callback synchronously with no error, so the window
    populates its tabs from whatever the test put into `globalData` beforehand. Windows are
    torn down without going through closeEvent (which would prompt about the tray).
    """
    import windows.MainWindow as MW

    class OfflineSSE(MW.SSEListener):
        def start(self, *a, **k):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(MW, 'SSEListener', OfflineSSE)

    from PyQt6.QtCore import QTimer

    calls = []
    delivered = []
    pending = []          # callbacks parked until the window constructor has returned
    constructing = [False]

    def deliver(callback, result):
        def fire():
            callback(None, result)
            delivered.append(1)
        if constructing[0]:
            pending.append(fire)
        else:
            QTimer.singleShot(0, fire)

    def fake_refresh(*args, callback=None, **kwargs):
        # A real server reply lands after the window's constructor has finished (the
        # request runs on a QThread). Some constructors pump the event loop (busy overlay),
        # so a plain singleShot(0) could fire too early - park replies until construction
        # returns, then deliver them on the event loop like the real relay does.
        calls.append((args, kwargs))
        if callback is not None:
            deliver(callback, None)

    monkeypatch.setattr(globalData, 'refresh', fake_refresh)

    # The Admin window's panels fetch on their own (server logs, backups); answer those the
    # same asynchronous, empty way so no error dialog ever pops up headless.
    from network.clientRequests import ClientRequests

    def async_stub(result):
        def stub(*args, callback=None, **kwargs):
            calls.append((args, kwargs))
            if callback is not None:
                deliver(callback, result)
            return None, result
        return staticmethod(stub)

    monkeypatch.setattr(ClientRequests, 'getLogFiles', async_stub([]))
    monkeypatch.setattr(ClientRequests, 'getBackups', async_stub({'backups': [], 'retentionDays': 14}))
    made = []

    def build(window_cls, logged_user, *extra):
        constructing[0] = True
        try:
            w = window_cls(logged_user, *extra)
        finally:
            constructing[0] = False
        made.append(w)
        for fire in pending:
            QTimer.singleShot(0, fire)
        pending.clear()
        qtbot.waitUntil(lambda: len(delivered) == len(calls), timeout=5000)
        return w

    build.refresh_calls = calls          # every stubbed server call: (args, kwargs), in order
    yield build
    for w in made:
        w._ptwAlarmTimer.stop()
        w._fabProximityTimer.stop()
        w._trayIcon.hide()
        w.hide()
        w.deleteLater()
