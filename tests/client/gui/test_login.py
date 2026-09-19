"""LoginWindow (client/Login.py) and the post-login routing in client/main.py.

Nothing here touches the network, the OS keyring or the user's real QSettings: the login
request is a stub that answers synchronously (or on the next event-loop turn), `keyring` is an
in-memory fake, and `QSettings("PTW", "PTW")` is redirected at a per-test ini file.

client/main.py builds a QApplication and calls `app.exec()` at import, so it cannot be
imported under pytest-qt. Its definitions (everything above `app = QApplication([])`) are
compiled and executed into a private module instead - the routing functions under test are
the real ones, only the process-level bootstrap is skipped.
"""

import os
import sys
import types

import pytest
from PyQt6.QtCore import Qt, QSettings, QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox
from keyring.errors import KeyringError

import helper.i18n as i18n
import Login as login_module
import widgets.RefreshOverlay as overlay_module
from Login import (LoginWindow, PasswordLineEdit, ResetPasswordDialog, GuestDetailsDialog,
                   SERVICE_NAME, SETTINGS_REMEMBERED_USERS_KEY)
from models.User import User, UserRoles, UserDepartments
from network.clientRequests import ClientRequests
from conftest import make_user

pytestmark = pytest.mark.gui

CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'client'))
MAIN_PY = os.path.join(CLIENT_DIR, 'main.py')


# ---- isolation fixtures -----------------------------------------------------------------

@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    """`QSettings("PTW", "PTW")` inside Login.py -> a throwaway ini file for this test."""
    ini = str(tmp_path / 'ptw-test-settings.ini')

    class TempSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(login_module, 'QSettings', TempSettings)

    def remembered():
        value = TempSettings().value(SETTINGS_REMEMBERED_USERS_KEY, [], type=list)
        return [str(v) for v in value] if value else []

    def set_remembered(usernames):
        s = TempSettings()
        s.setValue(SETTINGS_REMEMBERED_USERS_KEY, list(usernames))
        s.sync()

    return types.SimpleNamespace(remembered=remembered, set_remembered=set_remembered)


class FakeKeyring:
    """In-memory stand-in for the OS keyring; `fail` makes every call raise KeyringError."""

    def __init__(self):
        self.store = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise KeyringError('keyring backend locked')

    def set_password(self, service, username, password):
        self._check()
        self.store[(service, username)] = password

    def get_password(self, service, username):
        self._check()
        return self.store.get((service, username))

    def delete_password(self, service, username):
        self._check()
        if (service, username) not in self.store:
            raise KeyringError('no such password')
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(login_module, 'keyring', fake)
    return fake


@pytest.fixture(autouse=True)
def restore_app_state(qapp):
    """A login applies the user's language/theme app-wide; put it back for the next test."""
    yield
    i18n.init('en')
    i18n.apply_layout(qapp)
    overlay_module._manager.count = 0


@pytest.fixture
def color_scheme_calls(monkeypatch):
    """Record QStyleHints.setColorScheme calls: the offscreen QPA plugin has no real platform
    theme, so the resulting colorScheme() never actually changes - the call itself is what
    Login.py's contract is, so that's what's asserted on."""
    from PyQt6.QtGui import QStyleHints
    calls = []
    original = QStyleHints.setColorScheme

    def recording(self, scheme):
        calls.append(scheme)
        return original(self, scheme)

    monkeypatch.setattr(QStyleHints, 'setColorScheme', recording)
    return calls


@pytest.fixture
def messages(monkeypatch):
    """Capture QMessageBox.warning/information/critical calls as (kind, title, text)."""
    seen = []

    def record(kind):
        def fn(parent, title, text, *a, **k):
            seen.append((kind, title, text))
            return QMessageBox.StandardButton.Ok
        return staticmethod(fn)

    for kind in ('warning', 'information', 'critical'):
        monkeypatch.setattr(QMessageBox, kind, record(kind))
    return seen


@pytest.fixture
def login_window(qtbot):
    """A real LoginWindow, torn down without close() (its closeEvent quits the application)."""
    made = []

    def build():
        w = LoginWindow()
        made.append(w)
        return w

    yield build
    for w in made:
        w.hide()
        w.deleteLater()


@pytest.fixture
def window(login_window):
    return login_window()


@pytest.fixture
def login_stub(monkeypatch):
    """Replace ClientRequests.login: answer `(err, user)` through the callback, recording the credentials."""
    calls = []

    def install(err=None, user=None, deferred=False):
        def login(username, password, callback=None):
            calls.append((username, password))
            if deferred:
                QTimer.singleShot(0, lambda: callback(err, user))
            else:
                callback(err, user)
        monkeypatch.setattr(ClientRequests, 'login', staticmethod(login))
        return calls

    return install


def emitted(window):
    seen = []
    window.on_login_success.connect(seen.append)
    return seen


def enter_credentials(window, username, password):
    window.boxUsername.setCurrentText(username)
    window.boxPassword.setText(password)


# ---- LoginWindow.login ------------------------------------------------------------------

class TestLogin:
    def test_success_emits_the_user_and_applies_language_and_theme(self, qapp, window, login_stub, messages, fake_keyring, settings, color_scheme_calls):
        user = make_user('alice').setLanguage('ar').setTheme('dark')
        calls = login_stub(None, user)
        seen = emitted(window)
        enter_credentials(window, 'alice', 'pw')
        window.login()
        assert calls == [('alice', 'pw')]
        assert seen == [user]
        assert messages == []
        assert i18n.current_lang() == 'ar'
        assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
        assert color_scheme_calls == [Qt.ColorScheme.Dark]
        # remember-me is on by default: credentials went to the keyring, the name to QSettings
        assert fake_keyring.store == {(SERVICE_NAME, 'alice'): 'pw'}
        assert settings.remembered() == ['alice']

    def test_success_delivered_asynchronously(self, qtbot, window, login_stub, messages):
        user = make_user('alice')
        login_stub(None, user, deferred=True)
        enter_credentials(window, 'alice', 'pw')
        with qtbot.waitSignal(window.on_login_success, timeout=3000) as blocker:
            window.login()
        assert blocker.args == [user]
        assert overlay_module._manager.count == 0             # busy overlay released again

    def test_no_saved_language_falls_back_to_the_os_locale(self, qapp, window, login_stub, messages, monkeypatch, color_scheme_calls):
        fake_locale = types.SimpleNamespace(system=lambda: types.SimpleNamespace(name=lambda: 'fr_FR'))
        monkeypatch.setattr(login_module, 'QLocale', fake_locale)
        i18n.init('ar')
        i18n.apply_layout(qapp)
        login_stub(None, make_user('alice').setTheme('light'))
        enter_credentials(window, 'alice', 'pw')
        window.login()
        assert i18n.current_lang() == 'fr'                    # not the previous session's Arabic
        assert qapp.layoutDirection() == Qt.LayoutDirection.LeftToRight
        assert color_scheme_calls == [Qt.ColorScheme.Light]

    def test_failure_shows_the_server_error_and_keeps_the_window(self, window, login_stub, messages, fake_keyring):
        login_stub('Invalid username or password', None)
        seen = emitted(window)
        window.show()
        enter_credentials(window, 'alice', 'wrong')
        window.login()
        assert messages == [('warning', 'Error', 'Invalid username or password')]
        assert seen == []
        assert window.isVisible()
        assert fake_keyring.store == {}                       # nothing remembered for a failed attempt

    def test_empty_fields_are_submitted_and_the_servers_verdict_is_shown(self, window, login_stub, messages):
        # there is no client-side emptiness check: the server decides, and its message is what the user sees
        calls = login_stub('Username and password are required', None)
        seen = emitted(window)
        window.login()
        assert calls == [('', '')]
        assert messages == [('warning', 'Error', 'Username and password are required')]
        assert seen == []

    def test_remember_me_unchecked_stores_nothing(self, window, login_stub, messages, fake_keyring, settings):
        login_stub(None, make_user('alice'))
        window.btnRememberMe.setChecked(False)
        enter_credentials(window, 'alice', 'pw')
        window.login()
        assert fake_keyring.store == {} and settings.remembered() == []

    def test_remembered_username_moves_to_the_front(self, fake_keyring, settings, login_window, login_stub, messages):
        fake_keyring.store = {(SERVICE_NAME, 'bob'): 'pw-bob', (SERVICE_NAME, 'alice'): 'pw-alice'}
        settings.set_remembered(['bob', 'alice'])
        window = login_window()
        login_stub(None, make_user('alice'))
        window.boxUsername.setCurrentText('alice')
        window._onUsernameSelected('alice')
        window.login()
        assert settings.remembered() == ['alice', 'bob']
        assert fake_keyring.store[(SERVICE_NAME, 'alice')] == 'pw-alice'

    def test_keyring_failure_is_reported_but_does_not_block_the_login(self, window, login_stub, messages, fake_keyring):
        login_stub(None, make_user('alice'))
        seen = emitted(window)
        fake_keyring.fail = True
        enter_credentials(window, 'alice', 'pw')
        window.login()
        assert messages == [('warning', 'Error', 'keyring backend locked')]
        assert len(seen) == 1


# ---- remembered credentials -------------------------------------------------------------

class TestRememberedCredentials:
    def test_most_recent_user_is_prefilled_without_exposing_the_password(self, fake_keyring, settings, login_window, login_stub, messages):
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 's3cret'}
        settings.set_remembered(['alice', 'bob'])
        window = login_window()
        assert window.boxUsername.currentText() == 'alice'
        assert [window.boxUsername.itemText(i) for i in range(window.boxUsername.count())] == ['alice', 'bob']
        assert window.boxPassword.getPassword() == 's3cret'
        assert window.boxPassword.text() == PasswordLineEdit._SENTINEL     # the widget never holds the secret
        assert not window.boxPassword._btn.isEnabled()                     # reveal toggle locked
        calls = login_stub(None, make_user('alice'))
        window.login()
        assert calls == [('alice', 's3cret')]                              # ... but the real value is what gets sent

    def test_selecting_another_user_swaps_or_clears_the_password(self, fake_keyring, settings, login_window):
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 'pw-alice', (SERVICE_NAME, 'bob'): 'pw-bob'}
        settings.set_remembered(['alice', 'bob'])
        window = login_window()
        window._onUsernameSelected('bob')
        assert window.boxPassword.getPassword() == 'pw-bob'
        window._onUsernameSelected('carol')                                # not remembered
        assert window.boxPassword.getPassword() == '' and window.boxPassword.text() == ''
        assert window.boxPassword._btn.isEnabled()

    def test_remembered_user_without_a_keyring_entry_gets_an_empty_field(self, fake_keyring, settings, login_window):
        settings.set_remembered(['alice'])
        fake_keyring.fail = True
        window = login_window()
        assert window.boxUsername.currentText() == 'alice'
        assert window.boxPassword.getPassword() == ''

    def test_typing_over_a_retrieved_password_discards_it(self, qtbot, fake_keyring, settings, login_window):
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 's3cret'}
        settings.set_remembered(['alice'])
        window = login_window()
        window.show()
        qtbot.keyClicks(window.boxPassword, 'x')
        assert window.boxPassword._realValue == ''
        assert window.boxPassword.text() == ''                             # sentinel and keystroke both dropped
        assert window.boxPassword._btn.isEnabled()
        qtbot.keyClicks(window.boxPassword, 'new')
        assert window.boxPassword.getPassword() == 'new'

    def test_forget_removes_both_the_name_and_the_secret(self, fake_keyring, settings, window):
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 'pw', (SERVICE_NAME, 'bob'): 'pw'}
        settings.set_remembered(['alice', 'bob'])
        window.forgetLoginCredentials('alice')
        assert settings.remembered() == ['bob']
        assert fake_keyring.store == {(SERVICE_NAME, 'bob'): 'pw'}
        window.forgetLoginCredentials('nobody')                            # missing entries are not an error
        assert settings.remembered() == ['bob']

    def test_reset_repopulates_after_a_logout(self, fake_keyring, settings, window):
        assert window.boxUsername.count() == 0
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 'pw'}
        settings.set_remembered(['alice'])
        window.reset()
        assert window.boxUsername.currentText() == 'alice'
        assert window.boxPassword.getPassword() == 'pw'


class TestPasswordLineEdit:
    def test_reveal_toggle_flips_echo_mode(self, qtbot):
        box = PasswordLineEdit()
        qtbot.addWidget(box)
        box.setText('typed')
        assert box.echoMode() == QLineEdit.EchoMode.Password
        box._toggle_visibility()
        assert box.echoMode() == QLineEdit.EchoMode.Normal
        box._toggle_visibility()
        assert box.echoMode() == QLineEdit.EchoMode.Password

    def test_disabling_the_toggle_re_masks_a_revealed_field(self, qtbot):
        box = PasswordLineEdit()
        qtbot.addWidget(box)
        box._toggle_visibility()
        assert box.echoMode() == QLineEdit.EchoMode.Normal
        box.setRetrievedPassword('s3cret')
        assert box.echoMode() == QLineEdit.EchoMode.Password
        box._toggle_visibility()                                            # locked: no effect
        assert box.echoMode() == QLineEdit.EchoMode.Password
        assert box.getPassword() == 's3cret'


# ---- forgot / reset password ------------------------------------------------------------

class FakeDialog:
    """Stands in for a modal dialog: `exec()` returns the preset code, attributes are preset."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        FakeDialog.instances.append(self)
        for k, v in self.preset.items():
            setattr(self, k, v)

    def exec(self):
        return self.code


def fake_dialog(monkeypatch, module, name, code, **preset):
    FakeDialog.instances = []
    cls = type(f'Fake{name}', (FakeDialog,), {'code': code, 'preset': preset})
    monkeypatch.setattr(module, name, cls)
    return FakeDialog.instances


@pytest.fixture
def reset_request(monkeypatch):
    calls = []

    def install(err=None):
        def resetPassword(username, newPassword, code, callback=None):
            calls.append((username, newPassword, code))
            callback(err, None)
        monkeypatch.setattr(ClientRequests, 'resetPassword', staticmethod(resetPassword))
        return calls
    return install


class TestForgotPassword:
    def test_requires_a_username(self, window, messages, monkeypatch, reset_request):
        dialogs = fake_dialog(monkeypatch, login_module, 'ResetPasswordDialog', QDialog.DialogCode.Accepted)
        calls = reset_request()
        window.forgotPassword()
        assert messages == [('warning', 'Error', 'Please enter your username to reset your password.')]
        assert dialogs == [] and calls == []

    def test_accepted_dialog_submits_the_reset(self, window, messages, monkeypatch, reset_request):
        dialogs = fake_dialog(monkeypatch, login_module, 'ResetPasswordDialog', QDialog.DialogCode.Accepted,
                              newPassword='NewPass123', verificationCode='654321')
        calls = reset_request()
        window.boxUsername.setCurrentText('alice')
        window.forgotPassword()
        assert dialogs[0].args == ('alice', window)
        assert calls == [('alice', 'NewPass123', '654321')]
        assert messages == [('information', 'Success', 'Your password has been reset successfully. You can now log in with your new password.')]
        assert overlay_module._manager.count == 0

    def test_cancelled_dialog_sends_nothing(self, window, messages, monkeypatch, reset_request):
        fake_dialog(monkeypatch, login_module, 'ResetPasswordDialog', QDialog.DialogCode.Rejected)
        calls = reset_request()
        window.boxUsername.setCurrentText('alice')
        window.forgotPassword()
        assert calls == [] and messages == []

    def test_server_error_is_shown(self, window, messages, monkeypatch, reset_request):
        fake_dialog(monkeypatch, login_module, 'ResetPasswordDialog', QDialog.DialogCode.Accepted, newPassword='x', verificationCode='1')
        reset_request('Invalid or expired verification code')
        window.boxUsername.setCurrentText('alice')
        window.forgotPassword()
        assert messages == [('warning', 'Error', 'Invalid or expired verification code')]


class TestResetPasswordDialog:
    @pytest.fixture
    def code_request(self, monkeypatch):
        calls = []

        def install(err=None):
            def requestResetPassword(username, callback=None):
                calls.append(username)
                callback(err, None)
            monkeypatch.setattr(ClientRequests, 'requestResetPassword', staticmethod(requestResetPassword))
            return calls
        return install

    def test_code_is_requested_on_open_and_the_form_unlocks(self, qtbot, code_request, messages):
        calls = code_request()
        dlg = ResetPasswordDialog('alice')
        qtbot.addWidget(dlg)
        assert calls == ['alice']
        assert dlg.boxUsername.text() == 'alice' and dlg.boxUsername.isReadOnly()
        assert dlg.lblStatus.text() == 'Verification code sent. Check your email.'
        assert dlg.boxCode.isEnabled() and dlg.boxNewPassword.isEnabled()
        assert messages == []

    def test_failed_code_request_rejects_the_dialog(self, qtbot, code_request, messages):
        code_request('No email on file for this account')
        dlg = ResetPasswordDialog('alice')
        qtbot.addWidget(dlg)
        assert messages == [('warning', 'Error', 'No email on file for this account')]
        assert not dlg.boxCode.isEnabled()
        assert dlg.result() == QDialog.DialogCode.Rejected

    def test_validation_before_accepting(self, qtbot, code_request, messages):
        code_request()
        dlg = ResetPasswordDialog('alice')
        qtbot.addWidget(dlg)
        dlg.boxCode.setText('123456')
        dlg.resetPassword()
        assert messages[-1] == ('warning', 'Error', 'Please enter a new password.')
        dlg.boxNewPassword.setText('NewPass123')
        dlg.boxConfirmPassword.setText('different')
        dlg.resetPassword()
        assert messages[-1] == ('warning', 'Error', 'Passwords do not match.')
        assert dlg.result() != QDialog.DialogCode.Accepted
        dlg.boxConfirmPassword.setText('NewPass123')
        dlg.resetPassword()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert (dlg.verificationCode, dlg.newPassword) == ('123456', 'NewPass123')


# ---- guest login ------------------------------------------------------------------------

class TestGuest:
    def test_guest_dialog_requires_a_name(self, qtbot, messages):
        dlg = GuestDetailsDialog(list(UserDepartments))
        qtbot.addWidget(dlg)
        dlg.boxName.setText('   ')
        dlg._onAccept()
        assert messages == [('warning', 'Error', 'Please enter your name.')]
        assert dlg.result() != QDialog.DialogCode.Accepted
        dlg.boxName.setText('  Visitor One ')
        dlg.boxDepartment.setCurrentText('HSE')
        dlg._onAccept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert (dlg.getName(), dlg.getDepartment()) == ('Visitor One', 'HSE')

    def test_login_as_guest_emits_an_ephemeral_guest_user(self, window, monkeypatch):
        fake_dialog(monkeypatch, login_module, 'GuestDetailsDialog', QDialog.DialogCode.Accepted,
                    getName=lambda: 'Visitor One', getDepartment=lambda: 'HSE')
        seen = emitted(window)
        window.loginAsGuest()
        assert len(seen) == 1
        guest = seen[0]
        assert isinstance(guest, User)
        assert (guest.getUsername(), guest.getName(), guest.getRole(), guest.getDepartment()) == ('Visitor One', 'Visitor One', UserRoles.GUEST, 'HSE')

    def test_cancelled_guest_dialog_emits_nothing(self, window, monkeypatch):
        fake_dialog(monkeypatch, login_module, 'GuestDetailsDialog', QDialog.DialogCode.Rejected)
        seen = emitted(window)
        window.loginAsGuest()
        assert seen == []


# ---- client/main.py routing -------------------------------------------------------------

WINDOW_CLASSES = ('MainWindow', 'GuestMainWindow', 'UserMainWindow', 'CoordinatorMainWindow', 'IssuingMainWindow',
                  'HSEMainWindow', 'GasTesterMainWindow', 'ManagerMainWindow', 'AdminMainWindow', 'IsolatorMainWindow')


class FakeMainWindow(QObject):
    """Records construction instead of building a real role window."""
    on_logout = pyqtSignal()
    built = []

    def __init__(self, *args):
        super().__init__()
        self.args = args
        self.maximized = False
        FakeMainWindow.built.append(self)

    def showMaximized(self):
        self.maximized = True


@pytest.fixture(scope='module')
def main_module(qapp):
    """client/main.py's definitions, executed without its QApplication/exec() bootstrap."""
    with open(MAIN_PY, encoding='utf-8') as f:
        source = f.read()
    cut = source.index('\napp = QApplication([])')
    assert cut > 0
    saved_hook = sys.excepthook
    saved_path = list(sys.path)
    if CLIENT_DIR not in sys.path:
        sys.path.insert(0, CLIENT_DIR)
    mod = types.ModuleType('ptw_main_under_test')
    mod.__file__ = MAIN_PY
    try:
        exec(compile(source[:cut], MAIN_PY, 'exec'), mod.__dict__)
    finally:
        sys.excepthook = saved_hook           # main.py installs its own QMessageBox excepthook
        sys.path[:] = saved_path
    return mod


@pytest.fixture
def main(main_module, monkeypatch, window):
    """The real routing functions with fake role windows and a real LoginWindow as `loginWindow`."""
    FakeMainWindow.built = []
    for name in WINDOW_CLASSES:
        monkeypatch.setattr(main_module, name, type(f'Fake{name}', (FakeMainWindow,), {}))
    monkeypatch.setattr(main_module, 'loginWindow', window, raising=False)
    return main_module


ROLE_TO_WINDOW = [
    (UserRoles.GUEST, 'GuestMainWindow', ()),
    (UserRoles.USER, 'UserMainWindow', ()),
    (UserRoles.COORDINATOR, 'CoordinatorMainWindow', ()),
    (UserRoles.ISSUING, 'IssuingMainWindow', ()),
    (UserRoles.HSE_ENGINEER, 'HSEMainWindow', ()),
    (UserRoles.GAS_TESTER, 'GasTesterMainWindow', ()),
    (UserRoles.PGM, 'ManagerMainWindow', ('PGM',)),
    (UserRoles.PDH, 'ManagerMainWindow', ('PDH',)),
    (UserRoles.SOD, 'ManagerMainWindow', ('SOD',)),
    (UserRoles.DFGM, 'ManagerMainWindow', ('DFGM',)),
    (UserRoles.ADMIN, 'AdminMainWindow', ()),
    (UserRoles.ISOLATOR, 'IsolatorMainWindow', ()),
]


class TestShowMainWindow:
    def test_every_role_is_covered_by_the_table(self):
        assert {role for role, _, _ in ROLE_TO_WINDOW} == set(UserRoles)

    @pytest.mark.parametrize('role, window_name, extra', ROLE_TO_WINDOW, ids=[str(r) for r, _, _ in ROLE_TO_WINDOW])
    def test_role_opens_its_window_and_hides_login(self, main, window, role, window_name, extra):
        user = make_user('someone', role, UserDepartments.PROD)
        window.show()
        main._showMainWindow(user)
        assert [type(w).__name__ for w in FakeMainWindow.built] == [f'Fake{window_name}']
        built = FakeMainWindow.built[0]
        assert built.args == (user, *extra)
        assert built.maximized
        assert not window.isVisible()

    def test_unrecognised_role_falls_back_to_the_base_window(self, main, window):
        user = make_user('odd', None, UserDepartments.PROD)
        main._showMainWindow(user)
        assert [type(w).__name__ for w in FakeMainWindow.built] == ['FakeMainWindow']

    def test_logout_from_the_main_window_brings_login_back(self, main, window):
        window.show()
        main._showMainWindow(make_user('alice'))
        assert not window.isVisible()
        FakeMainWindow.built[0].on_logout.emit()
        assert window.isVisible()

    def test_build_waits_for_the_busy_overlay_to_finish_its_cycle(self, main, window):
        window.show()
        overlay = window._refreshOverlay
        overlay.showBusy()                                    # what login() does before the request
        assert overlay.isVisible()
        main._showMainWindow(make_user('alice'))
        assert FakeMainWindow.built == []                     # deferred: the pen is still writing
        overlay.hideBusy()                                    # the login callback's hideBusy()...
        assert FakeMainWindow.built == [] and overlay.isVisible()   # ...only queues the hide
        overlay._onCycleBoundary()                            # the animation reaches its loop edge
        assert not overlay.isVisible()
        assert len(FakeMainWindow.built) == 1 and not window.isVisible()
        overlay.hidden.emit()                                 # one-shot: a later hide builds nothing
        assert len(FakeMainWindow.built) == 1

    def test_guest_login_with_no_overlay_builds_immediately(self, main, window):
        window.show()
        assert not window._refreshOverlay.isVisible()
        main._showMainWindow(make_user('guest', UserRoles.GUEST, UserDepartments.HSE))
        assert len(FakeMainWindow.built) == 1


class TestForcedPasswordChange:
    @pytest.fixture
    def update_user(self, monkeypatch):
        calls = []

        def install(err=None):
            def updateUser(loggedUser, payload, callback=None):
                calls.append((loggedUser, payload))
                callback(err, None)
            monkeypatch.setattr(ClientRequests, 'updateUser', staticmethod(updateUser))
            return calls
        return install

    @pytest.fixture
    def shown(self, main, monkeypatch):
        opened = []
        monkeypatch.setattr(main, '_showMainWindow', opened.append)
        return opened

    def test_no_flag_goes_straight_to_the_main_window(self, main, shown, monkeypatch):
        import dialogs.DialogChangePassword as dcp
        dialogs = fake_dialog(monkeypatch, dcp, 'DialogChangePassword', QDialog.DialogCode.Accepted, newPassword='x')
        user = make_user('alice')
        main.on_login_success(user)
        assert shown == [user] and dialogs == []

    def test_flag_gates_entry_behind_the_dialog_and_saves_the_new_password(self, main, shown, update_user, messages, monkeypatch):
        import dialogs.DialogChangePassword as dcp
        dialogs = fake_dialog(monkeypatch, dcp, 'DialogChangePassword', QDialog.DialogCode.Accepted, newPassword='Fresh-Pass-9')
        calls = update_user()
        user = make_user('alice').setMustChangePassword(True)
        main.on_login_success(user)
        assert dialogs[0].args == (None, 'alice')
        assert len(calls) == 1
        logged, payload = calls[0]
        assert logged is user and payload is not user               # auth with the old record, deep copy carries the change
        assert payload.getPassword() == 'Fresh-Pass-9'
        assert user.getPassword() == 'Fresh-Pass-9' and user.getMustChangePassword() is False
        assert shown == [user]
        assert messages == []
        assert overlay_module._manager.count == 0

    def test_dismissed_dialog_leaves_the_user_at_login(self, main, shown, update_user, monkeypatch):
        import dialogs.DialogChangePassword as dcp
        fake_dialog(monkeypatch, dcp, 'DialogChangePassword', QDialog.DialogCode.Rejected)
        calls = update_user()
        user = make_user('alice').setMustChangePassword(True)
        main.on_login_success(user)
        assert calls == [] and shown == []
        assert user.getMustChangePassword() is True and user.getPassword() == 'pw'

    def test_server_rejection_keeps_the_gate_closed(self, main, shown, update_user, messages, monkeypatch):
        import dialogs.DialogChangePassword as dcp
        fake_dialog(monkeypatch, dcp, 'DialogChangePassword', QDialog.DialogCode.Accepted, newPassword='Fresh-Pass-9')
        update_user('Password was used recently')
        user = make_user('alice').setMustChangePassword(True)
        main.on_login_success(user)
        assert messages == [('warning', 'Fail', 'Password was used recently')]
        assert shown == []
        assert user.getMustChangePassword() is True and user.getPassword() == 'pw'


class TestOnLogout:
    def test_resets_and_reshows_the_login_window(self, main, window, fake_keyring, settings):
        fake_keyring.store = {(SERVICE_NAME, 'alice'): 'pw'}
        settings.set_remembered(['alice'])
        window.hide()
        main.on_logout()
        assert window.isVisible()
        assert window.boxUsername.currentText() == 'alice'
