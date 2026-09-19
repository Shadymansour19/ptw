"""DialogGasTest, DialogConfirmRunRequest, DialogSelectHeldICs, DialogUser, DialogSettings,
DialogChangePassword, DialogPtwAlarms and DialogEquipmentStatus: initial state from the
model, driven widgets -> collected result, and validation on accept - headless, no network."""

from datetime import datetime

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QWidget

from GlobalData import globalData
from models.PTW import PTW
from models.Isolation import IC
from models.User import User, UserRoles, UserDepartments
from network.clientRequests import ClientRequests
from tables.TableEquipmentStatus import _EquipmentRow
from dialogs import DialogGasTest as gas_module
from dialogs import DialogConfirmRunRequest as run_module
from dialogs import DialogUser as user_module
from dialogs import DialogSettings as settings_module
from dialogs import DialogChangePassword as pw_module
from dialogs import DialogPtwAlarms as alarms_module
from dialogs.DialogGasTest import DialogGasTest
from dialogs.DialogConfirmRunRequest import DialogConfirmRunRequest
from dialogs.DialogSelectHeldICs import DialogSelectHeldICs
from dialogs.DialogUser import DialogUser
from dialogs.DialogSettings import DialogSettings, SETTINGS_CLOSE_BEHAVIOR_KEY
from dialogs.DialogChangePassword import DialogChangePassword
from dialogs.DialogPtwAlarms import DialogPtwAlarms
from dialogs.DialogEquipmentStatus import DialogEquipmentStatus
from conftest import make_user
from ptw_factory import ptw_payload, full_chain, running_cycle, make_ic, ic_approval

pytestmark = pytest.mark.gui


def buttons(widget, text) -> list[QPushButton]:
    return [b for b in widget.findChildren(QPushButton) if b.text() == text]


def capture(monkeypatch, module, *kinds):
    """Replace QMessageBox.<kind> in `module` with a recorder of (kind, title, text)."""
    seen = []
    for kind in kinds:
        monkeypatch.setattr(module.QMessageBox, kind,
                            staticmethod(lambda *a, _k=kind, **k: seen.append((_k, a[1], a[2]))))
    return seen


def answer(monkeypatch, module, reply):
    monkeypatch.setattr(module.QMessageBox, 'question', staticmethod(lambda *a, **k: reply))


def sync_stub(recorded, result=(None, None)):
    def stub(*args, callback=None, **kwargs):
        recorded.append(args)
        if callback is not None:
            callback(*result)
        return result
    return staticmethod(stub)


def rejected_spy(dlg):
    closed = []
    dlg.rejected.connect(lambda: closed.append(1))
    return closed


def approved_ic(**over) -> IC:
    return make_ic(id=over.pop('id', 9), approvals=[ic_approval(UserRoles.ISSUING)], **over)


def active_ic(**over) -> IC:
    return approved_ic(isolate_requestor='user_turbo', isolate_issuing='issuing', isolate_issuing_action='Approved',
                       isolate_isolator='iso', **over)


# =========================================================================================
# DialogGasTest
# =========================================================================================

class TestDialogGasTest:
    @pytest.fixture
    def warnings(self, monkeypatch):
        return capture(monkeypatch, gas_module, 'warning')

    def test_one_not_entered_spinbox_per_gas_and_title_lists_every_ptw(self, qtbot, warnings):
        ptws = [PTW(ptw_payload(id=5)), PTW(ptw_payload(id=8))]
        d = DialogGasTest(None, ptws)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'Record Gas Test — PTW #5, #8'
        assert list(d.gasBoxes) == PTW.GAS_TEST_TYPES
        assert all(b.value() == -1.0 and b.text() == 'Not entered' for b in d.gasBoxes.values())
        assert any(l.text() == 'Record the same initial gas test readings for PTWs #5, #8.' for l in d.findChildren(QLabel))
        single = DialogGasTest(None, ptws[:1])
        qtbot.addWidget(single)
        assert any(l.text() == 'Record the initial gas test readings for PTW#5.' for l in single.findChildren(QLabel))

    def test_accept_requires_every_reading(self, qtbot, warnings):
        d = DialogGasTest(None, [PTW(ptw_payload(id=5))])
        qtbot.addWidget(d)
        for gas, box in d.gasBoxes.items():
            if gas != 'CO':
                box.setValue(20.9)
        d.accept()
        assert warnings == [('warning', 'Invalid Input', 'Please enter a reading for every gas.')]
        assert d.result() != QDialog.DialogCode.Accepted

    def test_zero_is_a_real_reading_and_results_are_collected(self, qtbot, warnings):
        d = DialogGasTest(None, [PTW(ptw_payload(id=5))])
        qtbot.addWidget(d)
        for box in d.gasBoxes.values():
            box.setValue(0.0)
        d.gasBoxes['O2'].setValue(20.95)
        assert d.getComment() is None
        d.boxComment.setPlainText('  windy  ')
        d.accept()
        assert warnings == [] and d.result() == QDialog.DialogCode.Accepted
        readings = d.getReadings()
        assert [r['gas'] for r in readings] == PTW.GAS_TEST_TYPES
        assert dict((r['gas'], r['percentage']) for r in readings)['O2'] == 20.95
        assert all(r['percentage'] == 0.0 for r in readings if r['gas'] != 'O2')
        assert d.getComment() == 'windy'


# =========================================================================================
# DialogConfirmRunRequest
# =========================================================================================

class TestDialogConfirmRunRequest:
    @pytest.fixture
    def ptw(self):
        return PTW(ptw_payload(id=42, approvals=full_chain('Cold')))

    def rows(self, dlg):
        """[(label text, {button text: enabled})] per linked-IC row."""
        out = []
        for box in dlg.findChildren(QLineEdit):
            row = box.parentWidget()
            out.append((box.text(), {b.text(): b.isEnabled() for b in row.findChildren(QPushButton)}))
        return out

    def test_no_linked_ics_placeholder(self, qtbot, user, ptw):
        d = DialogConfirmRunRequest(None, user, ptw, [])
        qtbot.addWidget(d)
        assert d.windowTitle() == 'Run PTW# 42'
        assert any(l.text() == 'No linked ICs.' for l in d.findChildren(QLabel))
        assert d.findChildren(QPushButton) == [b for b in d.btns.buttons()]

    def test_row_actions_follow_ic_status_for_a_performing_authority(self, qtbot, user, ptw):
        d = DialogConfirmRunRequest(None, user, ptw, [approved_ic(id=1), active_ic(id=2), make_ic(id=3)])
        qtbot.addWidget(d)
        assert self.rows(d) == [
            ('IC #1 — Approved', {'View': True, 'Request Isolate': True, 'Unlink': True}),
            ('IC #2 — Active', {'View': True, 'Request Isolate': False, 'Unlink': False}),
            ('IC #3 — Requested', {'View': True, 'Request Isolate': False, 'Unlink': True}),
        ]

    def test_unlink_is_not_offered_to_other_roles(self, qtbot, known_users, ptw):
        d = DialogConfirmRunRequest(None, known_users['gas'], ptw, [approved_ic(id=1)])
        qtbot.addWidget(d)
        assert self.rows(d) == [('IC #1 — Approved', {'View': True, 'Request Isolate': True})]

    def test_unlink_needs_an_unlinkable_ptw(self, qtbot, user):
        running = PTW(ptw_payload(id=42, approvals=full_chain('Cold'),
                                  run_cycles=[running_cycle(datetime(2026, 9, 1, 8, 0), ia='issuing')]))
        d = DialogConfirmRunRequest(None, user, running, [approved_ic(id=1)])
        qtbot.addWidget(d)
        assert self.rows(d)[0][1]['Unlink'] is False

    def test_request_isolate_confirms_calls_server_and_closes(self, qtbot, user, ptw, monkeypatch):
        d = DialogConfirmRunRequest(None, user, ptw, [approved_ic(id=1)])
        qtbot.addWidget(d)
        closed = rejected_spy(d)
        seen = capture(monkeypatch, run_module, 'warning', 'information')
        answer(monkeypatch, run_module, run_module.QMessageBox.StandardButton.Yes)
        calls = []
        monkeypatch.setattr(ClientRequests, 'requestIsolateIC', sync_stub(calls))
        buttons(d, 'Request Isolate')[0].click()
        assert calls == [(user, 1)]
        assert seen == [('information', 'Requested', 'Isolation requested for IC #1.')]
        assert closed == [1]

    def test_unlink_declined_sends_nothing_and_failure_keeps_dialog_open(self, qtbot, user, ptw, monkeypatch):
        d = DialogConfirmRunRequest(None, user, ptw, [approved_ic(id=1)])
        qtbot.addWidget(d)
        closed = rejected_spy(d)
        seen = capture(monkeypatch, run_module, 'warning', 'information')
        calls = []
        monkeypatch.setattr(ClientRequests, 'unlinkPTWFromIC', sync_stub(calls, result=('server says no', None)))
        answer(monkeypatch, run_module, run_module.QMessageBox.StandardButton.No)
        buttons(d, 'Unlink')[0].click()
        assert calls == [] and seen == []
        answer(monkeypatch, run_module, run_module.QMessageBox.StandardButton.Yes)
        buttons(d, 'Unlink')[0].click()
        assert calls == [(user, 1, 42)]
        assert seen == [('warning', 'Unlink Failed', 'server says no')]
        assert closed == []


# =========================================================================================
# DialogSelectHeldICs
# =========================================================================================

class TestDialogSelectHeldICs:
    @pytest.fixture
    def ics(self):
        return [active_ic(id=3), active_ic(id=1, type='Electrical'), approved_ic(id=2)]

    def cell(self, dlg, ic_id, col=0):
        for row in range(dlg.tbl.rowCount()):
            if dlg.tbl.item(row, 1).text() == str(ic_id):
                return dlg.tbl.item(row, col)
        raise AssertionError(ic_id)

    def test_selection_mode_prechecks_held_and_collects_the_choice(self, qtbot, ics):
        d = DialogSelectHeldICs(None, ics, held=['1'], selectable=True)
        qtbot.addWidget(d)
        assert d.tbl.rowCount() == 3
        assert self.cell(d, 3, 2).text() == 'Mechanical' and self.cell(d, 3, 3).text() == 'Active'
        assert self.cell(d, 2, 3).text() == 'Approved'
        assert d.getHeldICIds() == ['1']
        assert self.cell(d, 3).flags() & Qt.ItemFlag.ItemIsUserCheckable
        self.cell(d, 3).setCheckState(Qt.CheckState.Checked)
        assert set(d.getHeldICIds()) == {'1', '3'}
        buttons(d, 'Hold All')[0].click()
        assert set(d.getHeldICIds()) == {'1', '2', '3'}
        buttons(d, 'Release All')[0].click()
        assert d.getHeldICIds() == []
        assert d.action is None
        d.accept()
        assert d.result() == QDialog.DialogCode.Accepted

    def test_review_mode_records_the_ia_decision(self, qtbot, ics):
        d = DialogSelectHeldICs(None, ics, held=['3', '2'], review_mode=True)
        qtbot.addWidget(d)
        assert set(d.getHeldICIds()) == {'2', '3'}
        assert not (self.cell(d, 3).flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert buttons(d, 'Hold All') == [] and buttons(d, 'Release All') == []
        box = d.findChild(QDialogButtonBox)
        assert box.button(QDialogButtonBox.StandardButton.Yes).text() == 'Accept'
        box.button(QDialogButtonBox.StandardButton.No).click()
        assert d.action == 'reject' and d.result() == QDialog.DialogCode.Accepted

        d2 = DialogSelectHeldICs(None, ics, held=[], review_mode=True)
        qtbot.addWidget(d2)
        d2.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Yes).click()
        assert d2.action == 'accept'
        d3 = DialogSelectHeldICs(None, ics, review_mode=True)
        qtbot.addWidget(d3)
        d3.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).click()
        assert d3.action is None

    def test_view_only_and_non_selectable_modes_lock_the_checkboxes(self, qtbot, ics):
        d = DialogSelectHeldICs(None, ics, held=['1'], view_only=True)
        qtbot.addWidget(d)
        box = d.findChild(QDialogButtonBox)
        assert [box.standardButton(b) for b in box.buttons()] == [QDialogButtonBox.StandardButton.Close]
        assert not (self.cell(d, 1).flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert d.getHeldICIds() == ['1']
        d2 = DialogSelectHeldICs(None, ics, held=['1'], selectable=False)
        qtbot.addWidget(d2)
        assert not (self.cell(d2, 1).flags() & Qt.ItemFlag.ItemIsEnabled)
        assert buttons(d2, 'Hold All') == []


# =========================================================================================
# DialogUser
# =========================================================================================

class TestDialogUser:
    @pytest.fixture
    def errors(self, monkeypatch):
        return capture(monkeypatch, user_module, 'critical')

    @pytest.fixture
    def admin(self):
        return make_user('admin', UserRoles.ADMIN, UserDepartments.IT)

    def test_new_user_gets_a_generated_password_and_editable_username(self, qtbot, admin, errors):
        target = User()
        d = DialogUser(None, readonly=False, isNew=True, loggedUser=admin, toEditUser=target, label='New User')
        qtbot.addWidget(d)
        assert d.txtUsername.isEnabled() and d.txtPassword.isReadOnly()
        assert len(d.txtPassword.text()) == 16                  # secrets.token_urlsafe(12)
        assert d.txtRole.currentData() == 'User' and d.txtDepartment.currentData() == 'Turbo'   # first entries
        assert d.btns.button(QDialogButtonBox.StandardButton.Ok).isEnabled()

    def test_live_username_collision_disables_ok(self, qtbot, admin, errors, known_users):
        d = DialogUser(None, False, True, admin, User(), 'New User')
        qtbot.addWidget(d)
        d.txtUsername.setText('coord')
        assert not d.btns.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        assert d.lblUserExists.text() == 'Username already exists'
        assert d.txtUsername.property('error') == 'True'
        d.txtUsername.setText('coord2')
        assert d.btns.button(QDialogButtonBox.StandardButton.Ok).isEnabled() and d.lblUserExists.text() == ''

    @pytest.mark.parametrize('username, name, expected', [
        ('  ', 'Someone', "Username can't by empty!"),
        ('coord', 'Someone', 'Username already exists!'),
        ('newbie', '  ', "Name can't be empty!"),
    ])
    def test_collect_data_rejects_invalid_input(self, qtbot, admin, errors, known_users, username, name, expected):
        d = DialogUser(None, False, True, admin, User(), 'New User')
        qtbot.addWidget(d)
        d.txtUsername.setText(username); d.txtName.setText(name)
        d.collectData()
        assert errors == [('critical', 'Error', expected)]
        assert d.result() != QDialog.DialogCode.Accepted

    def test_collect_data_writes_every_field_onto_the_user(self, qtbot, admin, errors):
        target = User()
        d = DialogUser(None, False, True, admin, target, 'New User')
        qtbot.addWidget(d)
        d.txtUsername.setText(' newbie ')
        d.txtName.setText('New Bie')
        d.txtRole.setCurrentIndex(d.txtRole.findData('Isolator'))
        d.txtDepartment.setCurrentIndex(d.txtDepartment.findData('Elec'))
        d.txtEmail.setText('n@x.com ')
        d.txtExt.setText('1234')
        d.collectData()
        assert errors == [] and d.result() == QDialog.DialogCode.Accepted
        assert (target.getUsername(), target.getName(), target.getRole(), target.getDepartment()) == ('newbie', 'New Bie', 'Isolator', 'Elec')
        assert (target.getEmail(), target.getExt()) == ('n@x.com', '1234')
        assert target.getPassword() == d.txtPassword.text()

    def test_edit_mode_prefills_and_locks_the_username(self, qtbot, admin, errors, known_users):
        target = known_users['hse']
        target.setRole(str(target.getRole())).setExt('77')      # roles arrive from the server as plain strings
        d = DialogUser(None, False, False, admin, target, 'Edit User')
        qtbot.addWidget(d)
        assert not d.txtUsername.isEnabled() and d.txtUsername.text() == 'hse'
        assert (d.txtName.text(), d.txtRole.currentData(), d.txtDepartment.currentData(), d.txtExt.text()) == ('Hse', 'HSE Engineer', 'HSE', '77')
        assert d.btns.button(QDialogButtonBox.StandardButton.Ok).isEnabled()    # own username is never a collision
        d.txtName.setText('Renamed')
        d.collectData()
        assert target.getName() == 'Renamed' and target.getPassword() == 'pw'    # password untouched when editing

    def test_readonly_disables_fields_and_accepts_without_touching_the_user(self, qtbot, admin, errors, known_users):
        target = known_users['hse']
        d = DialogUser(None, True, False, admin, target, 'View User')
        qtbot.addWidget(d)
        assert d.txtName.isReadOnly() and not d.txtRole.isEnabled() and not d.txtDepartment.isEnabled() and d.txtEmail.isReadOnly()
        d.txtName.setText('Changed anyway')
        d.collectData()
        assert d.result() == QDialog.DialogCode.Accepted
        assert target.getName() == 'Hse'


# =========================================================================================
# DialogSettings
# =========================================================================================

class FakeQSettings:
    """In-memory stand-in for QSettings so tests never touch the real user config."""
    store = {}

    def __init__(self, *args):
        pass

    def value(self, key, default=None, type=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


class TestDialogSettings:
    @pytest.fixture(autouse=True)
    def fake_settings(self, monkeypatch):
        FakeQSettings.store = {}
        monkeypatch.setattr(settings_module, 'QSettings', FakeQSettings)
        return FakeQSettings.store

    @pytest.fixture
    def errors(self, monkeypatch):
        return capture(monkeypatch, settings_module, 'critical')

    def test_prefills_profile_theme_language_and_close_behavior(self, qtbot, errors, fake_settings):
        u = make_user('coord', str(UserRoles.COORDINATOR), UserDepartments.PROD).setTheme('dark').setLanguage('ar')
        u.setEmail('c@x.com').setExt('55')
        fake_settings[SETTINGS_CLOSE_BEHAVIOR_KEY] = 'tray'
        d = DialogSettings(None, u)
        qtbot.addWidget(d)
        assert d.txtUsername.text() == 'coord' and not d.txtUsername.isEnabled()
        assert not d.txtRole.isEnabled() and not d.txtDepartment.isEnabled()
        assert d.txtRole.currentData() == 'Coordinator' and d.txtDepartment.currentData() == 'Prod'
        assert (d.txtName.text(), d.txtEmail.text(), d.txtExt.text()) == ('Coord', 'c@x.com', '55')
        assert d.txtPassword.text() == '' and d.txtPassword.echoMode() == QLineEdit.EchoMode.Password
        assert d.cmbTheme.currentData() == 'Dark' and d.cmbLanguage.currentData() == 'Arabic'
        assert d.cmbCloseBehavior.currentText() == 'Minimize to tray'
        assert (d.new_theme, d.new_language) == ('dark', 'ar')

    def test_unset_preferences_show_the_defaults(self, qtbot, errors, user):
        d = DialogSettings(None, user)
        qtbot.addWidget(d)
        assert d.cmbTheme.currentData() == 'Default (System)' and d.cmbLanguage.currentData() == 'Default (System)'
        assert d.cmbCloseBehavior.currentText() == 'Always ask'

    def test_short_password_is_rejected_before_anything_changes(self, qtbot, errors, user, fake_settings):
        d = DialogSettings(None, user)
        qtbot.addWidget(d)
        d.txtPassword.setText('short7!')
        d.txtName.setText('Renamed')
        d.collectData()
        assert errors == [('critical', 'Error', 'Password must be at least 8 characters!')]
        assert user.getPassword() == 'pw' and user.getName() == 'User Turbo'
        assert fake_settings == {} and d.result() != QDialog.DialogCode.Accepted

    def test_blank_name_is_rejected_and_nothing_is_persisted(self, qtbot, errors, user, fake_settings):
        d = DialogSettings(None, user)
        qtbot.addWidget(d)
        d.txtName.setText('')
        d.collectData()
        assert errors == [('critical', 'Error', "Name can't be empty!")]
        assert fake_settings == {} and d.result() != QDialog.DialogCode.Accepted

    def test_collect_data_applies_profile_preferences_and_close_behavior(self, qtbot, errors, user, fake_settings):
        d = DialogSettings(None, user)
        qtbot.addWidget(d)
        d.txtPassword.setText('longenough')
        d.txtName.setText('Turbo Tech')
        d.txtEmail.setText('t@x.com'); d.txtExt.setText('9')
        d.cmbTheme.setCurrentIndex(d.cmbTheme.findData('Light'))
        d.cmbLanguage.setCurrentIndex(d.cmbLanguage.findData('English'))
        d.cmbCloseBehavior.setCurrentText('Exit completely')
        d.collectData()
        assert errors == [] and d.result() == QDialog.DialogCode.Accepted
        assert (user.getPassword(), user.getName(), user.getEmail(), user.getExt()) == ('longenough', 'Turbo Tech', 't@x.com', '9')
        assert user.getDepartment() == 'Turbo'
        assert (d.new_theme, d.new_language) == ('light', 'en')
        assert fake_settings == {SETTINGS_CLOSE_BEHAVIOR_KEY: 'exit'}

    def test_blank_password_means_keep_current(self, qtbot, errors, user, fake_settings):
        d = DialogSettings(None, user)
        qtbot.addWidget(d)
        d.cmbTheme.setCurrentIndex(d.cmbTheme.findData('Default (System)'))
        d.collectData()
        assert user.getPassword() is None            # the caller treats None as "no password change"
        assert d.new_theme is None and fake_settings == {SETTINGS_CLOSE_BEHAVIOR_KEY: ''}


# =========================================================================================
# DialogChangePassword
# =========================================================================================

class TestDialogChangePassword:
    @pytest.fixture
    def errors(self, monkeypatch):
        return capture(monkeypatch, pw_module, 'critical')

    def test_has_no_cancel_and_names_the_user(self, qtbot, errors):
        d = DialogChangePassword(None, 'coord')
        qtbot.addWidget(d)
        assert d.lblInfo.text() == 'Your password must be changed before you can continue, coord.'
        assert [d.btns.standardButton(b) for b in d.btns.buttons()] == [QDialogButtonBox.StandardButton.Ok]
        assert d.btns.button(QDialogButtonBox.StandardButton.Ok).text() == 'Change Password'
        assert not hasattr(d, 'newPassword')

    @pytest.mark.parametrize('new, confirm, expected', [
        ('short', 'short', 'Password must be at least 8 characters!'),
        ('longenough', 'longenouhg', 'Passwords do not match.'),
    ])
    def test_validation_blocks_and_explains(self, qtbot, errors, new, confirm, expected):
        d = DialogChangePassword(None, 'coord')
        qtbot.addWidget(d)
        d.boxNewPassword.setText(new); d.boxConfirmPassword.setText(confirm)
        d.btns.button(QDialogButtonBox.StandardButton.Ok).click()
        assert errors == [('critical', 'Error', expected)]
        assert not hasattr(d, 'newPassword') and d.result() != QDialog.DialogCode.Accepted

    def test_matching_password_is_stored_and_accepted(self, qtbot, errors):
        d = DialogChangePassword(None, 'coord')
        qtbot.addWidget(d)
        d.boxNewPassword.setText('longenough'); d.boxConfirmPassword.setText('longenough')
        d.btns.button(QDialogButtonBox.StandardButton.Ok).click()
        assert errors == [] and d.result() == QDialog.DialogCode.Accepted
        assert d.newPassword == 'longenough'


# =========================================================================================
# DialogPtwAlarms
# =========================================================================================

class FakeMainWindow(QWidget):
    """Just enough of MainWindow for DialogPtwAlarms: the logged user, the alarm interval and
    the two request methods it delegates to. Requests are recorded and answered by the test."""
    _PTW_ALARM_REPEAT_MINUTES = 7

    def __init__(self, user):
        super().__init__()
        self.loggedUser = user
        self.holds = []      # (ptw, callback)
        self.closes = []

    def requestToHldPTW(self, row, ptw, callback=None):
        self.holds.append((ptw, callback))

    def requestToClsPTW(self, row, ptw, callback=None):
        self.closes.append((ptw, callback))


class TestDialogPtwAlarms:
    @pytest.fixture
    def mw(self, qtbot, user):
        w = FakeMainWindow(user)
        qtbot.addWidget(w)
        return w

    @pytest.fixture
    def ptws(self):
        return [PTW(ptw_payload(id=1, description='Old one')), PTW(ptw_payload(id=2, description='Older')),
                PTW(ptw_payload(id=3, description='Shift over'))]

    def row_buttons(self, dlg, ptw_id):
        for box in dlg.findChildren(QLineEdit):
            if box.text().startswith(f'PTW #{ptw_id} '):
                return {b.text(): b for b in box.parentWidget().findChildren(QPushButton)}
        raise AssertionError(ptw_id)

    def test_sections_list_each_ptw_with_its_actions(self, qtbot, mw, ptws):
        d = DialogPtwAlarms(mw, ptws[:2], ptws[2:])
        qtbot.addWidget(d)
        assert any(l.text() == 'This reminder repeats every 7 minutes for anything still unresolved below.' for l in d.findChildren(QLabel))
        toggles = [t.text() for t in d.findChildren(alarms_module.QToolButton)]
        assert toggles == ['Exceeded 14-shift validity — needs closing (2)', 'Run cycle shift ended — needs hold/close (1)']
        assert [b.text() for b in d.findChildren(QLineEdit)] == ['PTW #1 — Old one', 'PTW #2 — Older', 'PTW #3 — Shift over']
        assert set(self.row_buttons(d, 1)) == {'View', 'Close'}
        assert set(self.row_buttons(d, 3)) == {'View', 'Hold', 'Close'}
        assert d.btnCloseAll is not None and d.btnCloseAll.isEnabled()
        assert set(d._validityCloseButtons) == {1, 2}

    def test_empty_sections_show_none_and_no_close_all(self, qtbot, mw):
        d = DialogPtwAlarms(mw, [], [])
        qtbot.addWidget(d)
        assert [l.text() for l in d.findChildren(QLabel) if l.text() == 'None.'] == ['None.', 'None.']
        assert d.btnCloseAll is None and d.findChildren(QLineEdit) == []

    def test_collapsing_a_section_hides_its_rows(self, qtbot, mw, ptws):
        d = DialogPtwAlarms(mw, ptws[:2], [])
        qtbot.addWidget(d)
        d.show()
        toggle = d.findChildren(alarms_module.QToolButton)[0]
        row = d.findChildren(QLineEdit)[0]
        assert toggle.isChecked() and row.isVisible()
        toggle.click()
        assert not row.isVisible()
        toggle.click()
        assert row.isVisible()

    def test_close_and_hold_go_through_the_main_window_and_disable_on_success(self, qtbot, mw, ptws):
        d = DialogPtwAlarms(mw, ptws[:2], ptws[2:])
        qtbot.addWidget(d)
        self.row_buttons(d, 1)['Close'].click()
        assert [p.id for p, _ in mw.closes] == [1]
        mw.closes[-1][1](None, None)
        assert not self.row_buttons(d, 1)['Close'].isEnabled()
        assert d.btnCloseAll.isEnabled()                    # #2 still open
        self.row_buttons(d, 2)['Close'].click()
        mw.closes[-1][1](None, None)
        assert not d.btnCloseAll.isEnabled()                # every validity row now actioned

        self.row_buttons(d, 3)['Hold'].click()
        assert [p.id for p, _ in mw.holds] == [3]
        mw.holds[-1][1](None, None)
        assert not self.row_buttons(d, 3)['Hold'].isEnabled() and not self.row_buttons(d, 3)['Close'].isEnabled()

    def test_failed_request_warns_and_keeps_the_row_actionable(self, qtbot, mw, ptws, monkeypatch):
        seen = capture(monkeypatch, alarms_module, 'warning')
        d = DialogPtwAlarms(mw, ptws[:1], [])
        qtbot.addWidget(d)
        self.row_buttons(d, 1)['Close'].click()
        mw.closes[-1][1]('nope', None)
        assert seen == [('warning', 'Fail', 'nope')]
        assert self.row_buttons(d, 1)['Close'].isEnabled() and d.btnCloseAll.isEnabled()

    def test_close_all_confirms_once_then_requests_each_open_row_directly(self, qtbot, mw, ptws, user, monkeypatch):
        d = DialogPtwAlarms(mw, ptws[:2], [])
        qtbot.addWidget(d)
        self.row_buttons(d, 1)['Close'].click()
        mw.closes[-1][1](None, None)                       # #1 already actioned - Close All must skip it
        questions = []
        monkeypatch.setattr(alarms_module.QMessageBox, 'question',
                            staticmethod(lambda *a, **k: (questions.append(a[2]), alarms_module.QMessageBox.StandardButton.Yes)[1]))
        calls = []
        monkeypatch.setattr(ClientRequests, 'requestToClsPTW', sync_stub(calls))
        d.btnCloseAll.click()
        assert questions == ['Request closing all 1 PTW(s) listed above?']
        assert len(calls) == 1 and calls[0][:3] == (user, 2, 'user_turbo') and calls[0][4] is None
        datetime.strptime(calls[0][3], '%d/%m/%Y %H:%M:%S')
        assert not self.row_buttons(d, 2)['Close'].isEnabled() and not d.btnCloseAll.isEnabled()
        # nothing left: a second click asks nothing and sends nothing
        d.btnCloseAll.click()
        assert len(questions) == 1 and len(calls) == 1

    def test_close_all_declined_sends_nothing(self, qtbot, mw, ptws, monkeypatch):
        d = DialogPtwAlarms(mw, ptws[:2], [])
        qtbot.addWidget(d)
        answer(monkeypatch, alarms_module, alarms_module.QMessageBox.StandardButton.No)
        calls = []
        monkeypatch.setattr(ClientRequests, 'requestToClsPTW', sync_stub(calls))
        d.btnCloseAll.click()
        assert calls == [] and d.btnCloseAll.isEnabled()


# =========================================================================================
# DialogEquipmentStatus
# =========================================================================================

class TestDialogEquipmentStatus:
    def test_summary_comes_from_the_live_ic_and_every_candidate_is_listed(self, qtbot, known_users):
        live_item = IC.IsolationItem('XV-7227A', 'MC-A 1nd Stage ASV', 'close').setLockNum('L1').setLockBoxNum('B1')
        live = active_ic(id=5, location='Scarab', execution_department='Elec', items=[])
        live.items = [live_item]
        old_item = IC.IsolationItem('XV-7227A', 'older desc', 'open')
        old = approved_ic(id=2, requestor='ghost', deisolate_isolator='iso', isolate_isolator='iso', type='Electrical')
        old.items = [old_item]
        assert old.getStatus() == IC.Status.CLOSED
        row = _EquipmentRow('XV-7227A', [(live, live_item), (old, old_item)])
        views = []
        d = DialogEquipmentStatus(None, row, lambda r, ic: views.append((r, ic)), lambda r, ic: None)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'Equipment — XV-7227A'
        labels = [l.text() for l in d.findChildren(QLabel)]
        for expected in ('XV-7227A', 'MC-A 1nd Stage ASV', 'Active', 'Scarab', 'Elec', 'L1', 'B1'):
            assert expected in labels
        assert d.tbl.rowCount() == 2
        assert [d.tbl.item(0, c).text() for c in range(7)] == ['5', 'Active', 'Mechanical', 'User Turbo', 'MC-A 1nd Stage ASV', 'L1', 'B1']
        assert [d.tbl.item(1, c).text() for c in range(7)] == ['2', 'Closed', 'Electrical', 'ghost', 'older desc', '', '']
        assert d.tbl.item(1, 0).background().color() == old.backgroundColor()
        d._onDoubleClicked(1, 0)
        assert views == [(1, old)]

    def test_close_button_rejects(self, qtbot):
        item = IC.IsolationItem('T-1', 'd', 'open')
        ic = approved_ic(id=1)
        ic.items = [item]
        d = DialogEquipmentStatus(None, _EquipmentRow('T-1', [(ic, item)]), lambda *a: None, lambda *a: None)
        qtbot.addWidget(d)
        closed = rejected_spy(d)
        d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Close).click()
        assert closed == [1]
