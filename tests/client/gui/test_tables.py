"""client/tables/: the list/table widgets that back every role window's tabs.

Each table is built stand-alone (no role window) inside a small host widget that
provides the `window()._refreshOverlay` the tables reach for around server calls.
Server calls are stubbed on `ClientRequests` and answer synchronously; blocking
dialogs (QMessageBox / QFileDialog / QMenu.exec / preview dialogs) are patched in the
table's own module.
"""

import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from freezegun import freeze_time
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QWidget, QDialog, QPushButton, QTextEdit

from GlobalData import globalData
from models.PTW import PTW, Attachment, RiskAssessment, RiskItem
from models.Isolation import IC, Isolation
from models.User import UserRoles, UserDepartments
from network.clientRequests import ClientRequests
from conftest import make_user
from ptw_factory import ptw_payload, make_ic, ic_approval

from tables import TablePTWs as ptws_module
from tables import TableUsers as users_module
from tables import TableAttachments as attachments_module
from tables import TableBackups as backups_module
from tables.TablePTWs import TablePTWs
from tables.TableICs import TableICs
from tables.TableUsers import TableUsers
from tables.TableRisks import TableRisks
from tables.TableEquipmentStatus import TableEquipmentStatus, _EquipmentRow
from tables.TableAttachments import TableAttachments
from tables.TableIsolations import TablePTWIsolations
from tables.TableIsolationItems import TableIsolationItems
from tables.TableBackups import TableBackups, _formatBytes, _formatAge
from widgets import TabServerLogs as logs_module
from widgets.TabServerLogs import TabServerLogs, _setColoredText

pytestmark = pytest.mark.gui

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TEST_DATA = os.path.join(ROOT, 'test_data')


# ---- shared helpers -----------------------------------------------------------------

class _FakeOverlay:
    """Stand-in for RefreshOverlay: counts showBusy/hideBusy instead of dimming."""

    def __init__(self):
        self.shown = 0
        self.hidden = 0

    def showBusy(self):
        self.shown += 1

    def hideBusy(self):
        self.hidden += 1


@pytest.fixture
def host(qtbot):
    """A shown top-level widget carrying a fake `_refreshOverlay`, to parent tables to."""
    w = QWidget()
    w._refreshOverlay = _FakeOverlay()
    w.resize(900, 600)
    qtbot.addWidget(w)
    w.show()
    return w


def sync_stub(result, calls=None):
    """A ClientRequests replacement that records its args and answers `result` synchronously."""
    calls = calls if calls is not None else []

    def stub(*args, callback=None, **kwargs):
        calls.append((args, kwargs))
        if callback is not None:
            callback(*result)
        return result
    stub.calls = calls
    return staticmethod(stub)


def column_texts(tbl, col):
    return [tbl.item(r, col).text() for r in range(tbl.rowCount())]


def visible_rows(tbl):
    return [r for r in range(tbl.rowCount()) if not tbl.isRowHidden(r)]


def row_center(tbl, row):
    return tbl.visualRect(tbl.model().index(row, 0)).center()


@pytest.fixture
def captured_menu(monkeypatch):
    """Patch QMenu.exec in the PTW/IC table modules so a context menu is captured instead of shown."""
    menus = []

    def fake_exec(menu, *a, **k):
        menus.append(menu)
        return None
    monkeypatch.setattr(ptws_module.QMenu, 'exec', fake_exec)
    return menus


def ptw(id, fast_track=False, **over):
    return PTW(ptw_payload(id=id, fast_track=fast_track, **over))


# ====================================================================================
# TablePTWs
# ====================================================================================

class TestTablePTWs:
    @pytest.fixture
    def table(self, host, user):
        t = TablePTWs(host, user, 'Requested PTWs')
        t.resize(900, 500)
        t.show()
        return t

    def test_add_renders_a_row_per_ptw_with_translated_cells_and_real_values(self, table, known_users):
        table.addPTWToGUI(ptw(7, location='Scarab', type='Hot'))
        assert table.tbl.rowCount() == 1 and table.ptwsData[0].id == 7
        assert table.tbl.item(0, table._idCol).text() == '7'
        assert table.tbl.item(0, table._idCol).data(Qt.ItemDataRole.UserRole) == 7
        # F.T. column keeps its text empty (the badge is a cell widget) and stashes Yes/No
        ft = table.tbl.item(0, table._ftCol)
        assert ft.text() == '' and ft.data(Qt.ItemDataRole.UserRole) == 'No'
        assert table.tbl.cellWidget(0, table._ftCol) is not None
        # requestor is resolved to the display name through globalData.allUsers
        assert table.tbl.item(0, table.summeryFields.index('requestor')).text() == 'User Turbo'
        loc = table.tbl.item(0, table.summeryFields.index('location'))
        assert loc.text() == 'Scarab' and loc.data(Qt.ItemDataRole.UserRole) == 'Scarab'
        assert table.tbl.item(0, 2).background().color() == PTW.backgroundColorForType('Hot')

    def test_ptw_to_record_falls_back_to_the_username_when_unknown(self, table):
        rec = table.ptwToRecord(ptw(3, fast_track=True, requestor='ghost'))
        assert rec[table._idCol] == '3' and rec[table._ftCol] == 'Yes'
        assert rec[table.summeryFields.index('requestor')] == 'ghost'

    def test_fast_track_rows_are_bold_and_badged(self, table):
        table.addPTWToGUI(ptw(1, fast_track=True))
        table.addPTWToGUI(ptw(2))
        assert table.tbl.item(0, 2).font().bold() and not table.tbl.item(1, 2).font().bold()
        assert table.tbl.cellWidget(0, table._ftCol).findChildren(QWidget)  # the bolt badge
        assert not table.tbl.cellWidget(1, table._ftCol).findChildren(QWidget)

    def test_sort_orders_fast_track_first_then_by_numeric_id(self, table):
        for p in (ptw(10), ptw(2), ptw(1, fast_track=True), ptw(11, fast_track=True)):
            table.addPTWToGUI(p)
        table.sort()
        assert column_texts(table.tbl, 0) == ['1', '11', '2', '10']
        assert [p.id for p in table.ptwsData] == [1, 11, 2, 10]

    def test_id_column_sorts_numerically_not_lexically(self, table):
        for i in (9, 10, 100, 2):
            table.addPTWToGUI(ptw(i))
        table.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        assert column_texts(table.tbl, 0) == ['2', '9', '10', '100']
        assert [p.id for p in table.ptwsData] == [2, 9, 10, 100]     # header sort resyncs ptwsData

    def test_update_in_place_rewrites_the_row(self, table):
        table.addPTWToGUI(ptw(5, equipment='P-1'))
        table.updatePTWInGUI(0, ptw(5, equipment='K-9', fast_track=True))
        assert table.tbl.rowCount() == 1
        assert table.tbl.item(0, table.summeryFields.index('equipment')).text() == 'K-9'
        assert table.tbl.item(0, table._ftCol).data(Qt.ItemDataRole.UserRole) == 'Yes'
        assert table.ptwsData[0].equipment == 'K-9'

    def test_update_ptw_round_trips_through_the_server(self, table, monkeypatch):
        table.addPTWToGUI(ptw(5, equipment='P-1'))
        monkeypatch.setattr(ClientRequests, 'updatePTW', sync_stub((None, None)))
        table.updatePTW(0, ptw(5, equipment='K-9'))
        assert ClientRequests.updatePTW.calls[0][0][1].equipment == 'K-9'
        assert table.tbl.item(0, table.summeryFields.index('equipment')).text() == 'K-9'

    def test_update_ptw_failure_warns_and_keeps_the_row(self, table, monkeypatch):
        table.addPTWToGUI(ptw(5, equipment='P-1'))
        monkeypatch.setattr(ClientRequests, 'updatePTW', sync_stub(('boom', None)))
        warned = []
        monkeypatch.setattr(ptws_module.QMessageBox, 'warning', staticmethod(lambda *a: warned.append(a)))
        table.updatePTW(0, ptw(5, equipment='K-9'))
        assert warned and warned[0][2] == 'boom'
        assert table.tbl.item(0, table.summeryFields.index('equipment')).text() == 'P-1'

    def test_remove_by_id_and_clear(self, table):
        for i in (1, 2, 3):
            table.addPTWToGUI(ptw(i))
        assert table.removePTWById(2) is True
        assert column_texts(table.tbl, 0) == ['1', '3'] and [p.id for p in table.ptwsData] == [1, 3]
        assert table.removePTWById(42) is False
        table.filterColumn('location', {'Phase VII'})
        table.clear()
        assert table.tbl.rowCount() == 0 and table.ptwsData == []
        assert all(c._model.rowCount() == 1 and not c.isFiltering() for c in table._filterCombos)

    def test_filter_bar_hides_non_matching_rows_and_show_all_restores(self, table):
        table.addPTWToGUI(ptw(1, location='Scarab'))
        table.addPTWToGUI(ptw(2, location='Phase VII'))
        table.addPTWToGUI(ptw(3, location='Scarab', fast_track=True))
        assert not table._filterBar.isVisible()
        table.filterColumn('location', {'Scarab'})
        assert table._filterBtn.isChecked() and table._filterBar.isVisible()
        assert visible_rows(table.tbl) == [0, 2]
        # a second column narrows further (filters are ANDed)
        table.filterColumn('fast_track', {'Yes'})
        assert visible_rows(table.tbl) == [2]
        table._filterBtn.setChecked(False)
        assert visible_rows(table.tbl) == [0, 1, 2]

    def test_filter_combos_are_populated_from_the_real_cell_values(self, table):
        table.addPTWToGUI(ptw(1, location='Scarab', type='Hot'))
        table.addPTWToGUI(ptw(12, location='Simian', type='Cold'))
        table._filterBtn.setChecked(True)
        by_field = dict(zip(table.summeryFields, table._filterCombos))
        assert by_field['location'].checkedItems() == {'Scarab', 'Simian'}
        assert by_field['type'].checkedItems() == {'Hot', 'Cold'}
        assert by_field['id'].checkedItems() == {1, 12}                 # ints, from UserRole
        assert by_field['fast_track'].checkedItems() == {'No'}

    def test_rows_added_while_filtering_are_filtered_too(self, table):
        table.addPTWToGUI(ptw(1, location='Scarab'))
        table.addPTWToGUI(ptw(2, location='Phase VII'))
        table.filterColumn('location', {'Scarab'})
        table.addPTWToGUI(ptw(3, location='Phase VII'))       # an unchecked value: stays hidden
        table.addPTWToGUI(ptw(4, location='Simian'))          # a brand-new value: checked by default, shown
        assert visible_rows(table.tbl) == [0, 3]
        assert dict(zip(table.summeryFields, table._filterCombos))['location'].checkedItems() == {'Scarab', 'Simian'}

    def test_filter_column_ignores_unknown_fields(self, table):
        table.addPTWToGUI(ptw(1))
        table.filterColumn('nonsense', {'x'})
        assert not table._filterBtn.isChecked() and visible_rows(table.tbl) == [0]

    def test_context_menu_shows_only_options_visible_for_the_row(self, table, captured_menu):
        table.addPTWToGUI(ptw(1, fast_track=True))
        table.addPTWToGUI(ptw(2))
        table.addOptions([
            TablePTWs.MenuOption('View', lambda r, p: None, QIcon()),
            TablePTWs.MenuOption('Only FT', lambda r, p: None, QIcon(), visibleFor=lambda p: p.fast_track),
        ])
        table.showContextMenu(row_center(table.tbl, 0))
        assert [a.text() for a in captured_menu[-1].actions()] == ['View', 'Only FT']
        table.showContextMenu(row_center(table.tbl, 1))
        assert [a.text() for a in captured_menu[-1].actions()] == ['View']

    def test_context_menu_outside_rows_shows_nothing(self, table, captured_menu):
        table.addOption(TablePTWs.MenuOption('View', lambda r, p: None, QIcon()))
        table.showContextMenu(table.tbl.rect().bottomRight())
        assert captured_menu == []

    def test_triggered_action_runs_over_the_selection_filtered_by_visible_for(self, table, captured_menu):
        for p in (ptw(1, fast_track=True), ptw(2), ptw(3, fast_track=True)):
            table.addPTWToGUI(p)
        per_row, batched = [], []
        table.addOptions([
            TablePTWs.MenuOption('Each', lambda r, p: per_row.append((r, p.id)), QIcon(), visibleFor=lambda p: p.fast_track),
            TablePTWs.MenuOption('All', lambda rows, ps: batched.append((rows, [p.id for p in ps])), QIcon(), allAtOnce=True),
        ])
        table.tbl.selectAll()
        table.showContextMenu(row_center(table.tbl, 0))
        actions = {a.text(): a for a in captured_menu[-1].actions()}
        actions['Each'].trigger()
        assert per_row == [(2, 3), (0, 1)]              # reverse row order, non-FT row 1 excluded
        actions['All'].trigger()
        assert batched == [([0, 1, 2], [1, 2, 3])]

    def test_double_click_invokes_the_first_option(self, table):
        table.addPTWToGUI(ptw(8))
        seen = []
        table.addOptions([TablePTWs.MenuOption('View', lambda r, p: seen.append((r, p.id)), QIcon()),
                          TablePTWs.MenuOption('Other', lambda r, p: seen.append('wrong'), QIcon())])
        table.doubleClickHandler(0, 3)
        assert seen == [(0, 8)]
        table.options.clear()
        table.doubleClickHandler(0, 3)          # no options registered: silently ignored
        assert seen == [(0, 8)]


# ====================================================================================
# TableICs
# ====================================================================================

def ic_with_status(id, status: IC.Status, **over) -> IC:
    """Build an IC whose getStatus() is `status` by setting the minimal execution fields."""
    fields = dict(id=id)
    if status == IC.Status.REQUESTED:
        pass
    elif status == IC.Status.RETURNED:
        fields['approvals'] = [ic_approval(UserRoles.ISSUING, action=IC.ApprovalActions.RETURNED)]
    elif status == IC.Status.APPROVED:
        fields['approvals'] = [ic_approval(UserRoles.ISSUING)]
    elif status == IC.Status.ISOLATE_CONFIRMING:
        fields.update(isolate_requestor='user_turbo')
    elif status == IC.Status.PENDING:
        fields.update(isolate_requestor='user_turbo', isolate_issuing_action='Approved')
    elif status == IC.Status.ACTIVE:
        fields.update(isolate_isolator='isolator')
    elif status == IC.Status.DEISOLATE_CONFIRMING:
        fields.update(isolate_isolator='isolator', deisolate_requestor='user_turbo')
    elif status == IC.Status.CLOSING:
        fields.update(isolate_isolator='isolator', deisolate_requestor='user_turbo', deisolate_issuing_action='Approved')
    elif status == IC.Status.SANCTIONED:
        fields.update(isolate_isolator='isolator', sanction_isolator='isolator')
    elif status == IC.Status.CLOSED:
        fields.update(isolate_isolator='isolator', deisolate_isolator='isolator')
    fields.update(over)
    return make_ic(**fields)


class TestTableICs:
    @pytest.fixture
    def table(self, host, user):
        t = TableICs(host, user, 'ICs')
        t.resize(900, 500)
        t.show()
        return t

    @pytest.mark.parametrize('status', list(IC.Status))
    def test_status_column_shows_the_derived_status(self, table, status):
        ic = ic_with_status(1, status)
        assert ic.getStatus() == status                      # the builder really produced that state
        table.addICToGUI(ic)
        cell = table.tbl.item(0, table.summeryFields.index('status'))
        assert cell.text() == status.value and cell.data(Qt.ItemDataRole.UserRole) == status.value

    def test_row_cells_resolve_requestor_and_long_term(self, table, known_users):
        table.addICToGUI(make_ic(id=4, long_term=True, type='Electrical', is_psic=False))
        assert table.tbl.item(0, 0).text() == '4' and table.tbl.item(0, 0).data(Qt.ItemDataRole.UserRole) == 4
        assert table.tbl.item(0, table.summeryFields.index('requestor')).text() == 'User Turbo'
        lt = table.tbl.item(0, table._ltCol)
        assert lt.text() == '' and lt.data(Qt.ItemDataRole.UserRole) == 'Yes'
        assert table.tbl.cellWidget(0, table._ltCol).findChildren(QWidget)
        assert table.tbl.item(0, 2).background().color() == IC.backgroundColorForType('Electrical')

    def test_psic_rows_use_the_psic_color(self, table):
        table.addICToGUI(make_ic(id=1, type='Mechanical', is_psic=True))
        assert table.tbl.item(0, 2).background().color() == IC.backgroundColorForType('Mechanical', isPsic=True)

    def test_sort_update_remove_keep_ics_data_in_row_order(self, table):
        for i in (10, 2, 1):
            table.addICToGUI(make_ic(id=i))
        table.sort()
        assert column_texts(table.tbl, 0) == ['1', '2', '10']
        assert [c.id for c in table.icsData] == [1, 2, 10]
        table.updateICInGUI(1, make_ic(id=2, equipment='V-77'))
        assert table.tbl.item(1, table.summeryFields.index('equipment')).text() == 'V-77'
        assert table.removeICById(10) and not table.removeICById(10)
        assert [c.id for c in table.icsData] == [1, 2] and table.tbl.rowCount() == 2

    def test_filter_by_status_and_context_menu_options(self, table, captured_menu):
        table.addICToGUI(ic_with_status(1, IC.Status.ACTIVE))
        table.addICToGUI(ic_with_status(2, IC.Status.CLOSED))
        table.filterColumn('status', {'Active'})
        assert visible_rows(table.tbl) == [0]
        seen = []
        table.addOptions([
            TablePTWs.MenuOption('View', lambda r, c: seen.append(('view', r, c.id)), QIcon()),
            TablePTWs.MenuOption('De-isolate', lambda r, c: None, QIcon(), visibleFor=lambda c: c.getStatus() == IC.Status.ACTIVE),
        ])
        table.showContextMenu(row_center(table.tbl, 0))
        assert [a.text() for a in captured_menu[-1].actions()] == ['View', 'De-isolate']
        table._filterBtn.setChecked(False)                    # unhide row 1 so it has a visual rect to click
        table.showContextMenu(row_center(table.tbl, 1))
        assert [a.text() for a in captured_menu[-1].actions()] == ['View']
        table.doubleClickHandler(1, 0)
        assert seen == [('view', 1, 2)]


# ====================================================================================
# TableUsers
# ====================================================================================

class TestTableUsers:
    @pytest.fixture
    def table(self, host):
        admin = make_user('admin', UserRoles.ADMIN, UserDepartments.IT)
        t = TableUsers(host, admin, 'Users')
        t.resize(900, 500)
        t.show()
        return t

    def test_add_update_remove_users(self, table):
        table.addUserToGUI(make_user('bob', UserRoles.USER, UserDepartments.MECH))
        table.addUserToGUI(make_user('amy', UserRoles.ISSUING, UserDepartments.PROD).setIsActive(False))
        assert column_texts(table.tbl, 0) == ['bob', 'amy']
        status_col = table.summeryFields.index('is_active')
        assert column_texts(table.tbl, status_col) == ['Active', 'Inactive']
        assert table.tbl.item(1, status_col).data(Qt.ItemDataRole.UserRole) == 'Inactive'
        role = table.tbl.item(1, table.summeryFields.index('role'))
        assert role.text() == 'Issuing' and role.data(Qt.ItemDataRole.UserRole) == 'Issuing'
        # header sort keeps self.users aligned with the rows
        table.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        assert [u.username for u in table.users] == ['amy', 'bob']
        table.clear()
        assert table.tbl.rowCount() == 0 and table.users == []

    def test_filter_column_by_department(self, table):
        table.addUserToGUI(make_user('bob', department=UserDepartments.MECH))
        table.addUserToGUI(make_user('amy', department=UserDepartments.PROD))
        table.addUserToGUI(make_user('cid', department=UserDepartments.MECH))
        table.filterColumn('department', {'Mech'})
        assert visible_rows(table.tbl) == [0, 2]
        assert dict(zip(table.summeryFields, table._filterCombos))['department'].checkedItems() == {'Mech'}

    def test_toggle_active_updates_the_row_after_the_server_confirms(self, table, host, monkeypatch):
        table.addUserToGUI(make_user('bob'))
        monkeypatch.setattr(users_module.QMessageBox, 'question',
                            staticmethod(lambda *a, **k: users_module.QMessageBox.StandardButton.Yes))
        monkeypatch.setattr(ClientRequests, 'setUserActive', sync_stub((None, None)))
        table.toggleActive(0)
        args = ClientRequests.setUserActive.calls[0][0]
        assert args[1:] == ('bob', False)
        assert not table.users[0].getIsActive()
        assert table.tbl.item(0, table.summeryFields.index('is_active')).text() == 'Inactive'
        assert (host._refreshOverlay.shown, host._refreshOverlay.hidden) == (1, 1)

    def test_toggle_active_declined_does_not_call_the_server(self, table, monkeypatch):
        table.addUserToGUI(make_user('bob'))
        monkeypatch.setattr(users_module.QMessageBox, 'question',
                            staticmethod(lambda *a, **k: users_module.QMessageBox.StandardButton.No))
        monkeypatch.setattr(ClientRequests, 'setUserActive', sync_stub((None, None)))
        table.toggleActive(0)
        assert ClientRequests.setUserActive.calls == [] and table.users[0].getIsActive()

    @pytest.fixture
    def import_dialogs(self, monkeypatch):
        """Drive the import flow headless: file picker -> the CSV fixture, preview dialogs accepted and recorded."""
        previews = []

        class FakePreview:
            def __init__(self, parent, title, headers, rows, mode='confirm', summary=None, onExport=None):
                self.title, self.headers, self.rows, self.mode, self.summary = title, headers, rows, mode, summary
                previews.append(self)

            def exec(self):
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(users_module, 'DialogUsersPreview', FakePreview)
        monkeypatch.setattr(users_module.QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (os.path.join(TEST_DATA, 'test_users_import.csv'), '')))
        return previews

    def test_import_from_csv_previews_then_adds_every_valid_row(self, table, import_dialogs, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'addNewUser', sync_stub((None, None)))
        table.importUsersFromExcel()
        confirm, result = import_dialogs
        assert confirm.mode == 'confirm' and len(confirm.rows) == 17
        assert confirm.headers[-2:] == ['Password', 'Status']
        assert all(r[-1] == 'Ready to import' for r in confirm.rows)
        sent = [c[0][1] for c in ClientRequests.addNewUser.calls]
        assert [u.getUsername() for u in sent][:3] == ['u', 's', 'y']
        assert len(sent) == 17 and table.tbl.rowCount() == 17
        assert result.mode == 'result' and result.summary == '17 of 17 user(s) imported successfully.'
        assert all(r[-1] == 'Success' for r in result.rows)
        # roles/departments are normalized to the enum spelling and shown translated
        row_y = [u for u in table.users if u.username == 'y'][0]
        assert (row_y.role, row_y.department) == ('Issuing', 'Prod')

    def test_import_skips_existing_usernames_and_reports_server_failures(self, table, import_dialogs, monkeypatch):
        globalData.allUsers['u'] = make_user('u')

        def add(user_, newUser, callback=None):
            callback('duplicate email' if newUser.getUsername() == 's' else None, None)
        monkeypatch.setattr(ClientRequests, 'addNewUser', staticmethod(add))
        table.importUsersFromExcel()
        confirm, result = import_dialogs
        statuses = {r[0]: r[-1] for r in result.rows}
        assert statuses['u'] == "Skipped: Username 'u' already exists"
        assert statuses['s'] == 'Failed: duplicate email'
        assert statuses['y'] == 'Success'
        assert result.summary == '15 of 16 user(s) imported successfully.'
        assert table.tbl.rowCount() == 15 and 'u' not in [u.username for u in table.users]

    def test_import_cancelled_at_the_file_picker_does_nothing(self, table, monkeypatch):
        monkeypatch.setattr(users_module.QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: ('', '')))
        monkeypatch.setattr(ClientRequests, 'addNewUser', sync_stub((None, None)))
        table.importUsersFromExcel()
        assert ClientRequests.addNewUser.calls == [] and table.tbl.rowCount() == 0


# ====================================================================================
# TableRisks
# ====================================================================================

def risk(title, n=1):
    return RiskAssessment(title=title, risks=[RiskItem('h%d' % i, 'e', '3B', 'c', '1A', 'Low') for i in range(n)])


class TestTableRisks:
    def test_set_risk_assessments_rebuilds_the_list(self, qtbot, user):
        t = TableRisks(None, user, 'Generic Risks', readonly=False, selectable=False)
        qtbot.addWidget(t)
        t.setRiskAssessmentsInGUI({'Lifting': risk('Lifting'), 'Welding': risk('Welding')})
        assert t.lstRisks.count() == 2
        titles = [t.lstRisks.itemWidget(t.lstRisks.item(i)).riskTitle for i in range(2)]
        assert titles == ['Lifting', 'Welding']
        t.setRiskAssessmentsInGUI({'Only': risk('Only')})
        assert t.lstRisks.count() == 1
        t.clear()
        assert t.lstRisks.count() == 0 and t.risks == {}

    def test_record_widget_controls_follow_readonly_and_selectable(self, qtbot, user):
        editable = TableRisks(None, user, readonly=False, selectable=False, risks={'A': risk('A')})
        picker = TableRisks(None, user, readonly=True, selectable=True, risks={'A' * 60: risk('A' * 60)})
        qtbot.addWidget(editable)
        qtbot.addWidget(picker)
        rec = editable.lstRisks.itemWidget(editable.lstRisks.item(0))
        assert rec.layout().indexOf(rec.btnEdit) >= 0 and rec.layout().indexOf(rec.btnCheck) == -1
        rec = picker.lstRisks.itemWidget(picker.lstRisks.item(0))
        assert rec.layout().indexOf(rec.btnEdit) == -1 and rec.layout().indexOf(rec.btnCheck) >= 0
        label = [w for w in rec.findChildren(QWidget) if hasattr(w, 'text') and w.text().startswith('AAA')][0]
        assert label.text() == 'A' * 50 + '...'

    def test_checkbox_and_selection_stay_in_sync_in_the_picker(self, qtbot, user):
        t = TableRisks(None, user, readonly=True, selectable=True)
        qtbot.addWidget(t)
        t.setRiskAssessmentsInGUI({'A': risk('A', 2), 'B': risk('B'), 'C': risk('C')})
        t.checkRisk('B')
        rec_b = t.lstRisks.itemWidget(t.lstRisks.item(1))
        assert rec_b.btnCheck.isChecked() and t.lstRisks.item(1).isSelected()
        rec_a = t.lstRisks.itemWidget(t.lstRisks.item(0))
        rec_a.btnCheck.click()                                   # clicking the box selects the row
        assert t.lstRisks.item(0).isSelected()
        assert {r.title for r in t.getSelectedRiskAssessments()} == {'A', 'B'}
        rec_a.btnCheck.click()                                   # and unchecking deselects it
        assert not t.lstRisks.item(0).isSelected()
        assert [r.title for r in t.getSelectedRiskAssessments()] == ['B']

    def test_non_selectable_table_never_reports_a_selection(self, qtbot, user):
        t = TableRisks(None, user, readonly=False, selectable=False, risks={'A': risk('A')})
        qtbot.addWidget(t)
        t.checkRisk('A')
        assert t.getSelectedRiskAssessments() == []


# ====================================================================================
# TableEquipmentStatus
# ====================================================================================

def item(tag, description='desc', state='OPEN', lock='', box=''):
    return dict(tag=tag, description=description, state=state, lock_num=lock, lock_box_num=box)


class TestTableEquipmentStatus:
    @pytest.fixture
    def table(self, host, user):
        t = TableEquipmentStatus(host, user, 'Equipment')
        t.show()
        return t

    def test_refresh_rolls_up_one_row_per_tag_picking_the_most_live_ic(self, table):
        closed = ic_with_status(1, IC.Status.CLOSED, location='Scarab', items=[item('V-1', 'old desc', lock='L1'), item('V-2')])
        active = ic_with_status(2, IC.Status.ACTIVE, location='Simian', execution_department='Mech',
                                items=[item('V-1', 'new desc', lock='L9', box='B2'), item('', 'no tag')])
        requested = ic_with_status(3, IC.Status.REQUESTED, items=[item('a-0')])
        table.refresh({1: closed, 2: active, 3: requested})
        assert column_texts(table.tbl, 0) == ['a-0', 'V-1', 'V-2']            # casefold-sorted by tag, blank tag dropped
        v1 = table.rowsData[1]
        assert isinstance(v1, _EquipmentRow) and v1.ic is active and v1.item.description == 'new desc'
        assert [c[0].id for c in v1.candidates] == [2, 1] and v1.allIcIds == [1, 2]
        assert table.rowToRecord(v1) == ['V-1', 'new desc', 'Active', 'Simian', 'Mech', 'L9', 'B2', '#1, #2']
        status = table.tbl.item(1, table.summeryFields.index('status'))
        assert status.text() == 'Active' and status.data(Qt.ItemDataRole.UserRole) == 'Active'
        assert table.tbl.item(2, table.summeryFields.index('status')).text() == 'Closed'
        assert table.tbl.item(1, 0).background().color() == active.backgroundColor()

    def test_same_priority_ties_go_to_the_newest_ic(self, table):
        older = ic_with_status(4, IC.Status.PENDING, items=[item('T-1', 'older')])
        newer = ic_with_status(9, IC.Status.PENDING, items=[item('T-1', 'newer')])
        table.refresh({9: newer, 4: older})
        assert table.rowsData[0].ic is newer and table.rowsData[0].item.description == 'newer'

    def test_refresh_replaces_previous_rows_and_reapplies_filters(self, table):
        table.refresh({1: ic_with_status(1, IC.Status.ACTIVE, items=[item('A'), item('B')])})
        table.refresh({2: ic_with_status(2, IC.Status.ACTIVE, items=[item('C')]),
                       3: ic_with_status(3, IC.Status.CLOSED, items=[item('D')])})
        assert column_texts(table.tbl, 0) == ['C', 'D']
        table._filterBtn.setChecked(True)
        dict(zip(table.summeryFields, table._filterCombos))['status'].setCheckedOnly({'Active'})
        assert visible_rows(table.tbl) == [0]
        table.refresh({3: ic_with_status(3, IC.Status.CLOSED, items=[item('D')]),
                       5: ic_with_status(5, IC.Status.ACTIVE, items=[item('E')])})
        assert column_texts(table.tbl, 0) == ['D', 'E'] and visible_rows(table.tbl) == [1]

    def test_double_click_and_menu_receive_the_aggregated_row(self, table, captured_menu):
        table.refresh({1: ic_with_status(1, IC.Status.ACTIVE, items=[item('A')])})
        seen = []
        table.addOption(TablePTWs.MenuOption('Open', lambda r, data: seen.append((r, data.tag, data.ic.id)), QIcon()))
        table.doubleClickHandler(0, 2)
        table.showContextMenu(row_center(table.tbl, 0))
        captured_menu[-1].actions()[0].trigger()
        assert seen == [(0, 'A', 1), (0, 'A', 1)]
        table.clear()
        assert table.tbl.rowCount() == 0 and table.rowsData == []


# ====================================================================================
# TableAttachments
# ====================================================================================

class TestTableAttachments:
    def test_lists_attached_docs_and_missing_required_ones(self, qtbot, user):
        attachs = [Attachment('/tmp/msds.pdf', 'MSDS.pdf', uploaded=True), Attachment('/tmp/x.pdf', 'Photo.pdf', uploaded=False)]
        t = TableAttachments(None, user, ptwId=5, attachments=attachs, readonly=False)
        qtbot.addWidget(t)
        assert t.optionalLst.count() == 2 and t.missingLst.count() == 0
        t.setRequiredAttachs(['MSDS', 'JSA'])
        assert t.missingLst.count() == 1
        assert t.missingLst.itemWidget(t.missingLst.item(0)).title == 'JSA'
        assert t.getAttachments() is attachs

    def test_readonly_hides_upload_and_delete_controls(self, qtbot, user):
        ro = TableAttachments(None, user, ptwId=5, attachments=[Attachment('', 'A.pdf', True)], readonly=True)
        rw = TableAttachments(None, user, ptwId=5, attachments=[Attachment('', 'A.pdf', True)], readonly=False)
        qtbot.addWidget(ro)
        qtbot.addWidget(rw)
        for t in (ro, rw):
            t.setRequiredAttachs(['JSA'])
        ro_rec = ro.optionalLst.itemWidget(ro.optionalLst.item(0))
        rw_rec = rw.optionalLst.itemWidget(rw.optionalLst.item(0))
        assert ro_rec.layout().indexOf(ro_rec.btnDelete) == -1 and rw_rec.layout().indexOf(rw_rec.btnDelete) >= 0
        ro_req = ro.missingLst.itemWidget(ro.missingLst.item(0))
        rw_req = rw.missingLst.itemWidget(rw.missingLst.item(0))
        assert ro_req.layout().indexOf(ro_req.btnUpload) == -1 and rw_req.layout().indexOf(rw_req.btnUpload) >= 0

    def test_delete_moves_a_satisfied_requirement_back_to_missing(self, qtbot, user):
        t = TableAttachments(None, user, ptwId=5, attachments=[Attachment('/l/m.pdf', 'MSDS.pdf', True)], readonly=False)
        qtbot.addWidget(t)
        t.setRequiredAttachs(['MSDS'])
        assert t.missingLst.count() == 0
        t.optionalLst.itemWidget(t.optionalLst.item(0)).btnDelete.click()
        assert t.getAttachments() == [] and t.optionalLst.count() == 0
        assert t.missingLst.count() == 1

    def test_upload_stages_a_local_file_named_after_the_requirement(self, qtbot, user, monkeypatch):
        t = TableAttachments(None, user, ptwId=5, attachments=[], readonly=False)
        qtbot.addWidget(t)
        t.setRequiredAttachs(['JSA'])

        class FakeFileDialog:
            FileMode = attachments_module.QFileDialog.FileMode

            def __init__(self, *a, **k):
                pass

            def setFileMode(self, mode):
                pass

            def exec(self):
                return True

            def selectedFiles(self):
                return ['/home/me/scan 01.PNG']
        monkeypatch.setattr(attachments_module, 'QFileDialog', FakeFileDialog)
        t.missingLst.itemWidget(t.missingLst.item(0)).btnUpload.click()
        [staged] = t.getAttachments()
        assert (staged.localPath, staged.remoteName, staged.uploaded) == ('/home/me/scan 01.PNG', 'JSA.PNG', False)
        assert t.missingLst.count() == 0 and t.optionalLst.count() == 1

    def test_view_opens_staged_files_locally_and_uploaded_ones_from_the_server(self, host, user, monkeypatch):
        from reports.ReportGenerator import ReportGenerator
        opened = []
        monkeypatch.setattr(ReportGenerator, 'openPDF', staticmethod(lambda path: opened.append(path)))
        staged = Attachment('/local/jsa.pdf', 'JSA.pdf', uploaded=False)
        remote = Attachment('', 'MSDS.pdf', uploaded=True)
        t = TableAttachments(host, user, ptwId=5, refPtwId=3, attachments=[staged, remote], readonly=True)
        t.viewAttachment(staged)
        assert opened == ['/local/jsa.pdf']

        fetches = []

        def get(user_, ptwId, name, callback=None):
            fetches.append((ptwId, name))
            if ptwId == 5:
                callback('missing', None)
            else:
                callback(None, f'/cache/{ptwId}/{name}')
        monkeypatch.setattr(ClientRequests, 'getPtwAttachment', staticmethod(get))
        t.viewAttachment(remote)
        assert fetches == [(5, 'MSDS.pdf'), (3, 'MSDS.pdf')]        # falls back to the reference PTW
        assert opened[-1] == '/cache/3/MSDS.pdf'
        assert host._refreshOverlay.shown == host._refreshOverlay.hidden == 1

    @pytest.mark.xfail(strict=True, reason="Known bug: client/tables/TableAttachments.py:88 `attachments: list[Attachment] = []` "
                                           "is a shared mutable default, so attachments staged in one widget built without an "
                                           "explicit list leak into every later one; each instance should start with its own empty list")
    def test_default_attachment_lists_are_independent_between_instances(self, qtbot, user):
        first = TableAttachments(None, user, ptwId=1, readonly=False)
        qtbot.addWidget(first)
        first.addAttachment(Attachment('/l/a.pdf', 'A.pdf', False))
        second = TableAttachments(None, user, ptwId=2, readonly=False)
        qtbot.addWidget(second)
        assert second.getAttachments() == [] and second.optionalLst.count() == 0


# ====================================================================================
# TablePTWIsolations / TableIsolationItems
# ====================================================================================

class TestTablePTWIsolations:
    def test_get_isolations_round_trips_the_live_list(self, qtbot):
        isolations = [Isolation('Mechanical', 'V-1', 'inlet'), Isolation('Electrical', 'MOV-2', 'motor')]
        t = TablePTWIsolations(None, isolations, readonly=False)
        qtbot.addWidget(t)
        assert t.tbl.rowCount() == 2 and column_texts(t.tbl, 1) == ['V-1', 'MOV-2']
        assert column_texts(t.tbl, 0) == ['Mechanical', 'Electrical']
        t.addIsolation(Isolation('Self', 'ESD-3', 'trip'))
        assert t.getIsolations() is isolations and [i.tag for i in isolations] == ['V-1', 'MOV-2', 'ESD-3']
        assert t.tbl.rowCount() == 3
        t.tbl.selectRow(0)
        t.deleteSelectedRows()
        assert [i.tag for i in t.getIsolations()] == ['MOV-2', 'ESD-3'] and t.tbl.rowCount() == 2
        t.clear()
        assert isolations == [] and t.tbl.rowCount() == 0

    def test_readonly_table_has_no_context_menu(self, qtbot):
        ro = TablePTWIsolations(None, [], readonly=True)
        rw = TablePTWIsolations(None, [], readonly=False)
        qtbot.addWidget(ro)
        qtbot.addWidget(rw)
        assert ro.tbl.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu
        assert rw.tbl.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


class TestTableIsolationItems:
    @staticmethod
    def make(tag, state='OPEN', desc='d'):
        return IC.IsolationItem(tag, desc, state).setLockNum('L1').setLockBoxNum('B1')

    def test_rows_show_every_field_and_add_emits_items_changed(self, qtbot):
        items = [self.make('V-1'), self.make('V-2', 'CLOSE')]
        t = TableIsolationItems(None, items, readonly=False)
        qtbot.addWidget(t)
        assert [t.tbl.item(0, c).text() for c in range(5)] == ['V-1', 'd', 'OPEN', 'L1', 'B1']
        with qtbot.waitSignal(t.itemsChanged, timeout=1000):
            t.addItem(self.make('V-3'))
        assert t.getItems() is items and len(items) == 3 and t.tbl.rowCount() == 3

    def test_delete_selected_emits_only_when_something_was_deleted(self, qtbot):
        items = [self.make('V-1'), self.make('V-2'), self.make('V-3')]
        t = TableIsolationItems(None, items, readonly=False)
        qtbot.addWidget(t)
        fired = []
        t.itemsChanged.connect(lambda: fired.append(1))
        t.deleteSelectedRows()
        assert fired == [] and len(items) == 3
        t.tbl.selectRow(0)
        t.tbl.selectionModel().select(t.tbl.model().index(2, 0), t.tbl.selectionModel().SelectionFlag.Select | t.tbl.selectionModel().SelectionFlag.Rows)
        t.deleteSelectedRows()
        assert fired == [1] and [i.tag for i in items] == ['V-2'] and t.tbl.rowCount() == 1

    def test_double_click_resolves_the_item_even_after_sorting(self, qtbot, monkeypatch):
        items = [self.make('A-1'), self.make('B-2'), self.make('C-3')]
        t = TableIsolationItems(None, items, readonly=False)
        qtbot.addWidget(t)
        opened = []
        monkeypatch.setattr(t, 'editItemDialog', lambda existing: opened.append(existing.tag))
        t.tbl.sortItems(0, Qt.SortOrder.DescendingOrder)
        assert column_texts(t.tbl, 0) == ['C-3', 'B-2', 'A-1']
        t._onCellDoubleClicked(0, 1)
        assert opened == ['C-3']
        assert t.tbl.item(0, 0).data(Qt.ItemDataRole.UserRole) is items[2]


# ====================================================================================
# TableBackups
# ====================================================================================

NOW = datetime(2026, 9, 19, 12, 0, 0)


def backup(name, age: timedelta, complete=True, dump=1024, files=2048):
    created = NOW - age
    return dict(name=name, created=created.isoformat(), complete=complete,
                dumpSizeBytes=dump, filesSizeBytes=files, totalSizeBytes=dump + files)


class TestTableBackups:
    @pytest.mark.parametrize('n, text', [(0, '0 B'), (None, '0 B'), (512, '512 B'), (1536, '1.5 KB'),
                                         (1048576, '1.0 MB'), (5 * 1024 ** 4, '5.0 TB')])
    def test_format_bytes(self, n, text):
        assert _formatBytes(n) == text

    @freeze_time(NOW)
    @pytest.mark.parametrize('age, text', [(timedelta(seconds=10), 'just now'), (timedelta(minutes=5), '5m ago'),
                                           (timedelta(hours=3), '3h ago'), (timedelta(hours=47), '47h ago'),
                                           (timedelta(days=3), '3d ago')])
    def test_format_age(self, age, text):
        assert _formatAge(NOW - age) == text

    @pytest.fixture
    def table(self, host):
        t = TableBackups(host, make_user('admin', UserRoles.ADMIN, UserDepartments.IT))
        t.show()
        return t

    @freeze_time(NOW)
    def test_populate_renders_ages_sizes_and_completeness(self, table):
        summary = dict(retentionDays=14, freeBytes=10 * 1024 ** 3, lastBackupAt=(NOW - timedelta(hours=2)).isoformat(),
                       backups=[backup('b-new', timedelta(hours=2)),
                                backup('b-old', timedelta(days=10), complete=False, dump=0, files=0)])
        table._populate(summary)
        assert table.tbl.rowCount() == 2
        rows = {table.tbl.item(r, 0).data(Qt.ItemDataRole.UserRole): [table.tbl.item(r, c).text() for c in range(7)]
                for r in range(2)}
        assert rows['b-new'] == ['2026-09-19 10:00:00', '2h ago', '1.0 KB', '2.0 KB', '3.0 KB', 'Complete', '14d']
        assert rows['b-old'] == ['2026-09-09 12:00:00', '10d ago', '0 B', '0 B', '0 B', 'Incomplete', '4d']
        incomplete_row = [r for r in range(2) if table.tbl.item(r, 0).data(Qt.ItemDataRole.UserRole) == 'b-old'][0]
        assert table.tbl.item(incomplete_row, 5).foreground().color() == QColor(backups_module._CRIT_COLOR)
        assert table._statusLabel.text() == 'Last backup: 2h ago  ·  2 backup(s)  ·  3.0 KB used  ·  10.0 GB free'
        assert backups_module._OK_COLOR in table._statusLabel.styleSheet()

    @freeze_time(NOW)
    @pytest.mark.parametrize('hours, color', [(1, backups_module._OK_COLOR), (40, backups_module._WARN_COLOR),
                                              (80, backups_module._CRIT_COLOR)])
    def test_status_color_follows_the_last_backup_age(self, table, hours, color):
        table._populate(dict(retentionDays=14, lastBackupAt=(NOW - timedelta(hours=hours)).isoformat(),
                             backups=[backup('b', timedelta(hours=hours))]))
        assert color in table._statusLabel.styleSheet()

    def test_populate_without_backups_reports_none(self, table):
        table._populate({'backups': [], 'retentionDays': 14})
        assert table.tbl.rowCount() == 0 and table._statusLabel.text() == 'No backups yet'
        assert backups_module._CRIT_COLOR in table._statusLabel.styleSheet()

    @freeze_time(NOW)
    def test_refresh_fetches_and_populates(self, table, host, monkeypatch):
        summary = dict(retentionDays=7, lastBackupAt=NOW.isoformat(), backups=[backup('b', timedelta(0))])
        monkeypatch.setattr(ClientRequests, 'getBackups', sync_stub((None, summary)))
        table.refresh()
        assert table.tbl.rowCount() == 1 and table.retentionDays == 7
        assert table.tbl.item(0, 6).text() == '7d'
        assert host._refreshOverlay.shown == host._refreshOverlay.hidden == 1

    def test_refresh_failure_warns_and_shows_the_error(self, table, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'getBackups', sync_stub(('server down', None)))
        warned = []
        monkeypatch.setattr(backups_module.QMessageBox, 'warning', staticmethod(lambda *a: warned.append(a[2])))
        table.refresh()
        assert warned == ['Failed to refresh backups: server down']
        assert table._statusLabel.text() == 'server down' and table.tbl.rowCount() == 0


# ====================================================================================
# TabServerLogs
# ====================================================================================

LOG = "\n".join([
    "2026-09-19 10:00:00 [INFO    ] server started",
    "2026-09-19 10:00:01 [DEBUG   ] cache warm",
    "2026-09-19 10:00:02 [ERROR   ] boom",
    "Traceback (most recent call last):",
    "  ValueError: nope",
    "2026-09-19 10:00:03 [WARNING ] careful",
    "2026-09-19 10:00:04 [CRITICAL] dying",
])


class TestTabServerLogs:
    def test_set_colored_text_filters_by_level_and_keeps_continuation_lines(self, qtbot):
        edit = QTextEdit()
        qtbot.addWidget(edit)
        _setColoredText(edit, LOG, set(logs_module.LOG_LEVELS))
        assert edit.toPlainText().splitlines() == LOG.splitlines()
        _setColoredText(edit, LOG, {'ERROR', 'CRITICAL'})
        assert edit.toPlainText().splitlines() == ['2026-09-19 10:00:02 [ERROR   ] boom',
                                                   'Traceback (most recent call last):',
                                                   '  ValueError: nope',
                                                   '2026-09-19 10:00:04 [CRITICAL] dying']
        # each line carries its level's color
        block = edit.document().firstBlock()
        assert block.begin().fragment().charFormat().foreground().color() == QColor(logs_module._LEVEL_COLORS['ERROR'][0])
        assert block.begin().fragment().charFormat().fontWeight() == logs_module.QFont.Weight.Bold
        _setColoredText(edit, LOG, set())
        assert edit.toPlainText() == ''

    def test_lines_without_a_level_tag_are_always_shown(self, qtbot):
        edit = QTextEdit()
        qtbot.addWidget(edit)
        _setColoredText(edit, "2026-09-19 10:00:00 untagged line\n2026-09-19 10:00:01 [DEBUG   ] x", {'INFO'})
        assert edit.toPlainText() == '2026-09-19 10:00:00 untagged line'

    @pytest.fixture
    def tab(self, host):
        t = TabServerLogs(host, make_user('admin', UserRoles.ADMIN, UserDepartments.IT))
        t.show()
        return t

    def test_level_filter_defaults_to_every_level(self, tab):
        assert tab._levelFilter.checkedItems() == set(logs_module.LOG_LEVELS)
        assert [tab._levelFilter._model.item(i).text() for i in range(1, 6)] == logs_module.LOG_LEVELS   # unsorted

    def test_refresh_builds_a_collapsed_panel_per_file_and_loads_lazily(self, tab, host, monkeypatch, qtbot):
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub((None, ['client.log', 'server.log'])))
        fetched = []

        def get_log(user_, fn, callback=None):
            fetched.append(fn)
            callback(None, LOG if fn == 'server.log' else 'not a log line')
        monkeypatch.setattr(ClientRequests, 'getLog', staticmethod(get_log))
        tab.refresh()
        assert list(tab._contentEdits) == ['client.log', 'server.log']
        assert fetched == [] and not tab._contentEdits['server.log'].isVisible()
        toggles = [b for b in tab._container.findChildren(QPushButton) if b.isCheckable()]
        assert len(toggles) == 2
        toggles[1].setChecked(True)
        assert fetched == ['server.log'] and tab._rawContent['server.log'] == LOG
        edit = tab._contentEdits['server.log']
        qtbot.waitUntil(edit.isVisible, timeout=2000)       # the layout shows newly inserted panels on the event loop
        assert edit.toPlainText() == LOG
        toggles[1].setChecked(False)
        qtbot.waitUntil(lambda: not edit.isVisible(), timeout=2000)
        toggles[1].setChecked(True)                    # re-expanding re-renders from the cache
        assert fetched == ['server.log']
        assert host._refreshOverlay.shown == host._refreshOverlay.hidden == 2

    def test_level_filter_rerenders_loaded_panels(self, tab, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub((None, ['server.log'])))
        monkeypatch.setattr(ClientRequests, 'getLog', sync_stub((None, LOG)))
        tab.refresh()
        [toggle] = [b for b in tab._container.findChildren(QPushButton) if b.isCheckable()]
        toggle.setChecked(True)
        tab._levelFilter.setCheckedOnly({'WARNING'})
        assert tab._contentEdits['server.log'].toPlainText() == '2026-09-19 10:00:03 [WARNING ] careful'
        tab._levelFilter.setCheckedOnly({'INFO', 'DEBUG'})
        assert tab._contentEdits['server.log'].toPlainText().splitlines() == LOG.splitlines()[:2]

    def test_refresh_with_no_files_or_an_error(self, tab, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub((None, [])))
        tab.refresh()
        assert tab._statusLabel.text() == 'No log files found.' and tab._contentEdits == {}
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub(('offline', None)))
        warned = []
        monkeypatch.setattr(logs_module.QMessageBox, 'warning', staticmethod(lambda *a: warned.append(a[2])))
        tab.refresh()
        assert tab._statusLabel.text() == 'offline' and warned == ['Failed to refresh logs: offline']

    def test_refresh_discards_previous_panels(self, tab, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub((None, ['a.log', 'b.log'])))
        tab.refresh()
        monkeypatch.setattr(ClientRequests, 'getLogFiles', sync_stub((None, ['c.log'])))
        tab.refresh()
        assert list(tab._contentEdits) == ['c.log'] and tab._rawContent == {}
        assert tab._containerLayout.count() == 2          # one panel + the trailing stretch
