"""DialogIC (new + read-only view), DialogIsolationItem, DialogIsolation,
DialogCompleteIsolation and DialogDefinePsicTerms: widget <-> model mapping, mode-driven
locking, and validation on accept - all headless, no network."""

from datetime import datetime

import pytest
from freezegun import freeze_time
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton

from GlobalData import globalData
from models.PTW import PTW
from models.Isolation import IC, Isolation, PSIC_REASONS, PSIC_TAG_SAMPLES
from models.User import UserRoles, UserDepartments
from network.clientRequests import ClientRequests
from widgets.UiUtils import TimelineEntry
from dialogs import DialogIC as ic_module
from dialogs import DialogIsolationItem as item_module
from dialogs import DialogIsolation as isolation_module
from dialogs import DialogDefinePsicTerms as psic_module
from dialogs.DialogIC import DialogIC
from dialogs.DialogIsolationItem import DialogIsolationItem
from dialogs.DialogIsolation import DialogIsolation
from dialogs.DialogCompleteIsolation import DialogCompleteIsolation
from dialogs.DialogDefinePsicTerms import DialogDefinePsicTerms
from conftest import make_user
from ptw_factory import ptw_payload, full_chain, running_cycle, make_ic, ic_approval

pytestmark = pytest.mark.gui


def set_combo(combo, data):
    idx = combo.findData(data)
    assert idx >= 0, data
    combo.setCurrentIndex(idx)


def button(widget, text) -> QPushButton:
    found = [b for b in widget.findChildren(QPushButton) if b.text() == text]
    assert found, f"no button {text!r}"
    return found[0]


def sync_stub(recorded, result=(None, None)):
    """A ClientRequests replacement that records its args and answers the callback at once."""
    def stub(*args, callback=None, **kwargs):
        recorded.append(args)
        if callback is not None:
            callback(*result)
        return result
    return staticmethod(stub)


@pytest.fixture
def messages(monkeypatch):
    """Capture every QMessageBox call made from DialogIC's module: (kind, title, text)."""
    seen = []
    for kind in ('warning', 'information', 'critical'):
        monkeypatch.setattr(ic_module.QMessageBox, kind,
                            staticmethod(lambda *a, _k=kind, **k: seen.append((_k, a[1], a[2]))))
    return seen


@pytest.fixture
def answer_yes(monkeypatch):
    monkeypatch.setattr(ic_module.QMessageBox, 'question',
                        staticmethod(lambda *a, **k: ic_module.QMessageBox.StandardButton.Yes))


def new_item(tag='XV-7227A', description='MC-A 1nd Stage ASV', state=IC.IsolationItem.States.CLOSE):
    return IC.IsolationItem(tag=tag, description=description, state=str(state))


# =========================================================================================
# DialogIC - new mode
# =========================================================================================

@pytest.fixture
def new_ic(qtbot, user, messages):
    globalData.allUsers[user.getUsername()] = user          # the logged user is always in the directory
    dlg = DialogIC(None, user, IC(), new=True, readOnly=False, title='New IC')
    qtbot.addWidget(dlg)
    return dlg


class TestDialogICNew:
    def test_defaults_come_from_the_logged_user(self, new_ic, user):
        d = new_ic
        assert d.boxId.text() == ''
        assert d.typeCombo.currentData() == 'Mechanical'
        assert d.boxRequestorDepartment.text() == user.getDepartment() == 'Turbo'
        assert d.boxExecutionDepartment.currentData() == 'Turbo'
        assert d.boxRequestor.text() == user.getName()
        assert d.boxIsolateAsap.currentData() == 'No'
        assert d.boxLongTerm.currentData() == 'No'
        assert not d.boxLongTermReason.isEnabled()
        assert d.typeCombo.isEnabled() and d.boxLocation.isEnabled() and not d.boxEquipment.isReadOnly()
        # only the four editable tabs: no History / PTW Linkage on a brand-new IC
        assert d.stack.count() == 4
        assert not hasattr(d, 'tabHistory') and not hasattr(d, 'tabLinkage')

    def test_psic_section_is_hidden_when_creating(self, new_ic):
        d = new_ic
        d.stack.setCurrentWidget(d.tabPsic)
        # the PSIC controls are built but their container is hidden; the explanatory note shows instead
        assert not d.boxIsPsic.isVisibleTo(d)
        assert not d.boxPsicSystemDescription.isVisibleTo(d)
        notes = [l for l in d.tabPsic.findChildren(QLabel) if l.text().startswith('PSIC is set by Issuing')]
        assert len(notes) == 1 and notes[0].isVisibleTo(d)

    def test_self_type_locks_execution_department_to_the_requestors(self, new_ic):
        d = new_ic
        set_combo(d.boxExecutionDepartment, 'Prod')
        set_combo(d.typeCombo, 'Self')
        assert d.boxExecutionDepartment.currentData() == 'Turbo'
        assert not d.boxExecutionDepartment.isEnabled()
        set_combo(d.typeCombo, 'Electrical')
        assert d.boxExecutionDepartment.isEnabled()

    def test_tab_bar_recolors_with_the_type(self, new_ic):
        d = new_ic
        assert IC.backgroundColorForType('Mechanical').name() in d.tabsContainer.styleSheet()
        set_combo(d.typeCombo, 'Electrical')
        assert IC.backgroundColorForType('Electrical').name() in d.tabsContainer.styleSheet()
        assert IC.backgroundColorForType('Mechanical').name() not in d.tabsContainer.styleSheet()

    def test_long_term_yes_enables_its_reason_box(self, new_ic):
        d = new_ic
        set_combo(d.boxLongTerm, 'Yes')
        assert d.boxLongTermReason.isEnabled()
        set_combo(d.boxLongTerm, 'No')
        assert not d.boxLongTermReason.isEnabled()

    def test_fab_offers_new_item_only_on_the_items_tab(self, new_ic):
        d = new_ic
        assert d.stack.currentWidget() is d.tabBasicInfo
        assert d.btnFAB.isHidden()
        d.stack.setCurrentWidget(d.tabItems)
        assert not d.btnFAB.isHidden()
        assert d.btnFAB.toolTip() == 'New Isolation Item [Ctrl+N]'
        assert d._fabCallback == d.itemsTable.newItemDialog
        d.stack.setCurrentWidget(d.tabPsic)
        assert d.btnFAB.isHidden()

    def test_adding_items_feeds_the_table_and_the_psic_tag_combo(self, new_ic):
        d = new_ic
        assert d.itemsTable.tbl.rowCount() == 0 and d.psicTagCombo.count() == 0
        d.itemsTable.addItem(new_item('XV-7227A'))
        d.itemsTable.addItem(new_item('1M1', 'BC-A Enclosure Lighting', IC.IsolationItem.States.OPEN))
        assert d.itemsTable.tbl.rowCount() == 2
        assert [d.psicTagCombo.itemText(i) for i in range(d.psicTagCombo.count())] == ['XV-7227A', '1M1']
        assert d.itemsTable.tbl.item(1, 2).text() == 'open'
        # the table edits the IC's own item list in place
        assert [i.tag for i in d.ic.items] == ['XV-7227A', '1M1']

    @pytest.mark.parametrize('setup, expected', [
        (lambda d: None, 'Please enter the equipment.'),
        (lambda d: d.boxEquipment.setText('P-1'), 'Please enter a reason for the isolation.'),
        (lambda d: (d.boxEquipment.setText('P-1'), d.boxReason.setPlainText('why'), set_combo(d.boxLongTerm, 'Yes')),
         'Please enter a reason to isolate for long term'),
        (lambda d: (d.boxEquipment.setText('P-1'), d.boxReason.setPlainText('why')),
         'Please add at least one isolation item.'),
    ])
    def test_accept_blocks_on_the_first_missing_field(self, new_ic, messages, setup, expected):
        d = new_ic
        setup(d)
        d.accept()
        assert d.result() != QDialog.DialogCode.Accepted
        assert messages == [('warning', 'Invalid Input', expected)]

    def test_accept_writes_the_form_back_and_stamps_the_requestor(self, new_ic, messages, user):
        d = new_ic
        set_combo(d.typeCombo, 'Electrical')
        set_combo(d.boxExecutionDepartment, 'Elec')
        set_combo(d.boxLocation, 'Scarab')
        set_combo(d.boxIsolateAsap, 'Yes')
        set_combo(d.boxLongTerm, 'Yes')
        d.boxEquipment.setText('  K-201 ')
        d.boxReason.setPlainText('Motor swap')
        d.boxLongTermReason.setPlainText('Spares on order')
        d.itemsTable.addItem(new_item('1M1', 'BC-A Enclosure Lighting'))
        with freeze_time('2026-09-19 08:30:00'):
            d.accept()
        assert messages == []
        assert d.result() == QDialog.DialogCode.Accepted
        ic = d.getIC()
        assert (ic.type, ic.location, ic.equipment, ic.reason) == ('Electrical', 'Scarab', 'K-201', 'Motor swap')
        assert ic.isolate_asap is True and ic.long_term is True and ic.long_term_reason == 'Spares on order'
        assert ic.requestor == user.getUsername() and ic.requestor_department == 'Turbo'
        assert ic.execution_department == 'Elec'
        assert ic.requestor_timestamp == '19/09/2026 08:30:00'
        assert ic.is_psic is False and ic.psic_reasons == []
        # the NOT NULL psic_* columns get real empty strings, never None
        assert (ic.psic_moc_number, ic.psic_system_description, ic.psic_isolation_method, ic.psic_control_measures) == ('', '', '', '')
        assert [i.tag for i in ic.items] == ['1M1']

    def test_self_type_accept_executes_in_own_department(self, new_ic, messages):
        d = new_ic
        set_combo(d.typeCombo, 'Self')
        d.boxEquipment.setText('P-1'); d.boxReason.setPlainText('why')
        d.itemsTable.addItem(new_item())
        d.accept()
        assert messages == [] and d.result() == QDialog.DialogCode.Accepted
        assert d.ic.type == 'Self' and d.ic.execution_department == 'Turbo'


# =========================================================================================
# DialogIC - read-only view of an existing IC
# =========================================================================================

def viewed_ic(**over) -> IC:
    data = dict(id=9, items=[dict(tag='XV-7227A', description='MC-A 1nd Stage ASV', state='close', lock_num='L7', lock_box_num='B2')],
                requestor_timestamp='01/09/2026 08:00:00', reason='Gasket replacement', location='Scarab',
                long_term=True, long_term_reason='Spares late')
    data.update(over)
    return make_ic(**data)


@pytest.fixture
def view(qtbot, known_users, messages):
    def build(ic, viewer='user_turbo', linked=()):
        ic.linked_ptws = [str(p) for p in linked]
        dlg = DialogIC(None, known_users[viewer], ic, new=False, readOnly=True, title=f'IC #{ic.id}')
        qtbot.addWidget(dlg)
        return dlg
    return build


class TestDialogICView:
    def test_fields_are_populated_and_locked(self, view):
        d = view(viewed_ic())
        assert d.boxId.text() == '9'
        assert d.boxRequestor.text() == 'User Turbo'                 # resolved through globalData.allUsers
        assert d.boxRequestTime.text() == '01/09/2026 08:00:00'
        assert d.boxLocation.currentData() == 'Scarab' and not d.boxLocation.isEnabled()
        assert d.boxEquipment.text() == 'P-101' and d.boxEquipment.isReadOnly()
        assert d.boxReason.toPlainText() == 'Gasket replacement' and d.boxReason.isReadOnly()
        assert d.boxLongTerm.currentData() == 'Yes' and not d.boxLongTerm.isEnabled()
        assert d.boxLongTermReason.toPlainText() == 'Spares late'
        assert d.boxLongTermReason.isReadOnly() and d.boxLongTermReason.isEnabled()   # readable, not editable
        assert not d.typeCombo.isEnabled() and not d.boxExecutionDepartment.isEnabled()
        assert not d.boxIsPsic.isEnabled()
        assert d.itemsTable.tbl.rowCount() == 1 and d.itemsTable.tbl.item(0, 3).text() == 'L7'
        assert d.stack.count() == 6 and hasattr(d, 'tabHistory') and hasattr(d, 'tabLinkage')

    def test_readonly_accept_never_validates(self, view, messages):
        d = view(viewed_ic(equipment=''))
        d.accept()
        assert messages == [] and d.result() == QDialog.DialogCode.Accepted

    def test_unknown_requestor_falls_back_to_the_username(self, view):
        d = view(viewed_ic(requestor='ghost'))
        assert d.boxRequestor.text() == 'ghost'

    def test_psic_view_shows_terms_readably_but_locked(self, view):
        ic = viewed_ic(is_psic=True, psic_reasons=['ESD', 'Other'], psic_moc_number='MOC-12',
                       psic_system_description='sys', psic_isolation_method='meth', psic_control_measures='ctl')
        d = view(ic)
        assert d.boxIsPsic.isChecked()
        assert {r for r, b in d.psicReasonCheckboxes.items() if b.isChecked()} == {'ESD', 'Other'}
        assert all(not b.isEnabled() for b in d.psicReasonCheckboxes.values())
        assert not d.psicTagCombo.isEnabled() and not d.btnPsicAutofill.isEnabled()
        assert d.boxPsicMocNumber.text() == 'MOC-12' and d.boxPsicMocNumber.isReadOnly()
        for box, text in ((d.boxPsicSystemDescription, 'sys'), (d.boxPsicIsolationMethod, 'meth'), (d.boxPsicControlMeasures, 'ctl')):
            assert box.toPlainText() == text and box.isReadOnly() and box.isEnabled()
        assert IC.backgroundColorForType('Mechanical', True).name() in d.tabsContainer.styleSheet()
        # the PSIC editable section is visible in view mode, the "new" note is not
        d.stack.setCurrentWidget(d.tabPsic)
        assert d.boxIsPsic.isVisibleTo(d)
        notes = [l for l in d.tabPsic.findChildren(QLabel) if l.text().startswith('PSIC is set by Issuing')]
        assert len(notes) == 1 and not notes[0].isVisibleTo(d)

    def test_history_tab_lists_request_approvals_and_pending_stages(self, view):
        ic = viewed_ic(is_psic=True, approvals=[ic_approval(UserRoles.ISSUING)])
        d = view(ic)
        entries = d.tabHistory.findChildren(TimelineEntry)
        texts = [l.text() for l in d.tabHistory.findChildren(QLabel)]
        # approval pane: Requested + 1 approval + 5 pending PSIC stages; isolation pane: 6 fixed stage rows
        assert len(entries) == 7 + 6
        assert any('<b>Requested</b> by User Turbo at 01/09/2026 08:00:00' in t for t in texts)
        assert any(t.startswith('<b>Approved</b> by Issuing Issuing at') for t in texts)
        assert [t for t in texts if t.startswith('<b>Pending</b>')] == [
            '<b>Pending</b> Coordinator', '<b>Pending</b> PDH', '<b>Pending</b> PGM', '<b>Pending</b> SOD', '<b>Pending</b> DFGM']
        assert '<b>Isolate Requested</b> — Pending' in texts

    def test_history_shows_a_returned_isolate_confirmation_in_orange(self, view):
        ic = viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)], isolate_requestor='user_turbo',
                       isolate_requestor_timestamp='02/09/2026 09:00:00', isolate_issuing='issuing',
                       isolate_issuing_timestamp='02/09/2026 09:05:00', isolate_issuing_action='Returned')
        d = view(ic)
        labels = {l.text(): l for l in d.tabHistory.findChildren(QLabel)}
        returned = labels['<b>Isolate Returned</b> by Issuing at 02/09/2026 09:05:00']
        assert 'color: #ffa500' in returned.styleSheet()
        assert 'color: #008000' in labels['<b>Isolate Requested</b> by User Turbo at 02/09/2026 09:00:00'].styleSheet()

    def test_linkage_rows_reflect_ptw_status_and_unlink_eligibility(self, view):
        approved = PTW(ptw_payload(id=42, approvals=full_chain('Cold')))
        running = PTW(ptw_payload(id=43, approvals=full_chain('Cold'),
                                  run_cycles=[running_cycle(datetime(2026, 9, 1, 8, 0), ia='issuing')]))
        globalData.allPTWs.update({42: approved, 43: running})
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]), linked=(42, 43, 99))
        fields = [w.text() for w in d.tabLinkage.findChildren(ic_module.QLineEdit)]
        assert fields == ['PTW #42 — Not Running', 'PTW #43 — Running', 'PTW #99']
        unlinks = [b for b in d.tabLinkage.findChildren(QPushButton) if b.text() == 'Unlink']
        assert [b.isEnabled() for b in unlinks] == [True, False, False]

    def test_linkage_placeholder_and_no_unlink_button_for_other_roles(self, view):
        d = view(viewed_ic(), viewer='hse')
        assert [l.text() for l in d.tabLinkage.findChildren(QLabel)][-1] == 'No linked PTWs.'
        globalData.allPTWs[42] = PTW(ptw_payload(id=42, approvals=full_chain('Cold')))
        d2 = view(viewed_ic(), viewer='hse', linked=(42,))
        assert [b.text() for b in d2.tabLinkage.findChildren(QPushButton)] == ['View']

    def test_fab_links_a_ptw_only_while_the_ic_is_not_winding_down(self, view):
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]))
        d.stack.setCurrentWidget(d.tabLinkage)
        assert not d.btnFAB.isHidden() and d.btnFAB.toolTip() == 'Link to PTW [Ctrl+N]'
        d.stack.setCurrentWidget(d.tabItems)          # read-only items tab: no "add item" FAB
        assert d.btnFAB.isHidden()
        closed = viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)], isolate_isolator='iso', deisolate_isolator='iso')
        assert closed.getStatus() == IC.Status.CLOSED
        d2 = view(closed)
        d2.stack.setCurrentWidget(d2.tabLinkage)
        assert d2.btnFAB.isHidden()

    def test_link_new_ptw_rejects_duplicates_and_otherwise_calls_the_server(self, view, messages, monkeypatch):
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]), linked=(42,))
        closed = []
        d.rejected.connect(lambda: closed.append(1))
        monkeypatch.setattr(ic_module.QInputDialog, 'getText', staticmethod(lambda *a, **k: (' 42 ', True)))
        d._linkNewPTW()
        assert messages == [('warning', 'Already Linked', 'PTW #42 is already linked to this IC.')]
        assert closed == []

        calls = []
        monkeypatch.setattr(ClientRequests, 'linkPTWToIC', sync_stub(calls))
        monkeypatch.setattr(ic_module.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('77', True)))
        d._linkNewPTW()
        assert calls == [(d.loggedUser, 9, '77')]
        assert messages[-1] == ('information', 'Linked', 'PTW #77 has been linked. Reopen this IC to see the updated linkage.')
        assert closed == [1]       # closed so the caller reopens with fresh linkage

    def test_link_new_ptw_cancelled_or_blank_does_nothing(self, view, messages, monkeypatch):
        d = view(viewed_ic())
        calls = []
        monkeypatch.setattr(ClientRequests, 'linkPTWToIC', sync_stub(calls))
        monkeypatch.setattr(ic_module.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('5', False)))
        d._linkNewPTW()
        monkeypatch.setattr(ic_module.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('   ', True)))
        d._linkNewPTW()
        assert calls == [] and messages == []

    def test_unlink_after_confirmation_reports_and_closes(self, view, messages, answer_yes, monkeypatch):
        globalData.allPTWs[42] = PTW(ptw_payload(id=42, approvals=full_chain('Cold')))
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]), linked=(42,))
        closed = []
        d.rejected.connect(lambda: closed.append(1))
        calls = []
        monkeypatch.setattr(ClientRequests, 'unlinkPTWFromIC', sync_stub(calls))
        button(d.tabLinkage, 'Unlink').click()
        assert calls == [(d.loggedUser, 9, '42')]
        assert messages == [('information', 'Unlinked', 'PTW #42 has been unlinked. Reopen this IC to see the updated linkage.')]
        assert closed == [1]

    def test_unlink_failure_is_reported_and_dialog_stays_open(self, view, messages, answer_yes, monkeypatch):
        globalData.allPTWs[42] = PTW(ptw_payload(id=42, approvals=full_chain('Cold')))
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]), linked=(42,))
        closed = []
        d.rejected.connect(lambda: closed.append(1))
        monkeypatch.setattr(ClientRequests, 'unlinkPTWFromIC', sync_stub([], result=('boom', None)))
        button(d.tabLinkage, 'Unlink').click()
        assert messages == [('warning', 'Unlink Failed', 'boom')]
        assert closed == []

    def test_unlink_declined_at_the_prompt_sends_nothing(self, view, messages, monkeypatch):
        globalData.allPTWs[42] = PTW(ptw_payload(id=42, approvals=full_chain('Cold')))
        d = view(viewed_ic(approvals=[ic_approval(UserRoles.ISSUING)]), linked=(42,))
        monkeypatch.setattr(ic_module.QMessageBox, 'question',
                            staticmethod(lambda *a, **k: ic_module.QMessageBox.StandardButton.No))
        calls = []
        monkeypatch.setattr(ClientRequests, 'unlinkPTWFromIC', sync_stub(calls))
        button(d.tabLinkage, 'Unlink').click()
        assert calls == [] and messages == []

    def test_view_of_a_missing_linked_ptw_warns(self, view, messages):
        d = view(viewed_ic(), linked=(99,))
        button(d.tabLinkage, 'View').click()
        assert messages == [('warning', 'PTW Not Found', 'PTW #99 could not be found (it may be archived).')]


# =========================================================================================
# DialogIsolationItem
# =========================================================================================

@pytest.fixture
def item_warnings(monkeypatch):
    seen = []
    monkeypatch.setattr(item_module.QMessageBox, 'warning', staticmethod(lambda *a, **k: seen.append(a[2])))
    return seen


class TestDialogIsolationItem:
    def test_new_item_defaults_to_first_library_tag_without_autofilling(self, qtbot, item_warnings):
        d = DialogIsolationItem(None)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'New Isolation Item'
        assert d.boxTag.currentText() == 'XV-7227A'
        assert d.boxDescription.toPlainText() == ''          # signal wired after the initial selection
        assert d.stateCombo.currentData() == 'open'
        assert d.boxLockNum.isReadOnly() and d.boxLockBoxNum.isReadOnly()
        assert d.getItem() is None

    def test_picking_a_library_tag_autofills_the_description(self, qtbot, item_warnings):
        d = DialogIsolationItem(None)
        qtbot.addWidget(d)
        d.boxTag.setCurrentIndex(d.boxTag.findText('1M1'))
        assert d.boxDescription.toPlainText() == 'BC-A Enclosure Lighting'
        # a free-typed tag leaves whatever is there alone
        d.boxTag.setCurrentText('CUSTOM-1')
        d.boxTag.itemSelected.emit('CUSTOM-1')
        assert d.boxDescription.toPlainText() == 'BC-A Enclosure Lighting'

    def test_accept_requires_tag_and_description(self, qtbot, item_warnings):
        d = DialogIsolationItem(None)
        qtbot.addWidget(d)
        d.boxTag.setCurrentText('')
        d.accept()
        assert item_warnings == ['Please select a tag or enter a new one.']
        d.boxTag.setCurrentText('CUSTOM-1')
        d.accept()
        assert item_warnings[-1] == 'Please enter a description.'
        assert d.getItem() is None and d.result() != QDialog.DialogCode.Accepted

    def test_accept_builds_the_item_with_blank_locks(self, qtbot, item_warnings):
        d = DialogIsolationItem(None)
        qtbot.addWidget(d)
        d.boxTag.setCurrentText('CUSTOM-1')
        d.boxDescription.setPlainText('Custom valve')
        set_combo(d.stateCombo, 'close')
        d.accept()
        assert item_warnings == [] and d.result() == QDialog.DialogCode.Accepted
        item = d.getItem()
        assert (item.tag, item.description, item.state, item.lock_num, item.lock_box_num) == ('CUSTOM-1', 'Custom valve', 'close', '', '')

    def test_editing_keeps_the_isolators_lock_numbers(self, qtbot, item_warnings):
        original = new_item('1M1', 'BC-A Enclosure Lighting', IC.IsolationItem.States.OPEN).setLockNum('L9').setLockBoxNum('B1')
        d = DialogIsolationItem(None, item=original)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'Edit Isolation Item'
        assert (d.boxTag.currentText(), d.boxDescription.toPlainText(), d.stateCombo.currentData()) == ('1M1', 'BC-A Enclosure Lighting', 'open')
        assert (d.boxLockNum.text(), d.boxLockBoxNum.text()) == ('L9', 'B1')
        d.boxDescription.setPlainText('Edited')
        d.accept()
        item = d.getItem()
        assert item is not original
        assert (item.description, item.lock_num, item.lock_box_num) == ('Edited', 'L9', 'B1')
        assert original.description == 'BC-A Enclosure Lighting'

    def test_readonly_locks_fields_hides_cancel_and_accepts_freely(self, qtbot, item_warnings):
        d = DialogIsolationItem(None, item=new_item(), readonly=True)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'View Isolation Item'
        assert not d.boxTag.isEnabled() and d.boxDescription.isReadOnly() and not d.stateCombo.isEnabled()
        cancel = d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel.isHidden()
        d.boxDescription.setPlainText('')
        d.accept()
        assert item_warnings == [] and d.result() == QDialog.DialogCode.Accepted and d.getItem() is None


# =========================================================================================
# DialogIsolation (PTW's declarative isolation tag)
# =========================================================================================

@pytest.fixture
def isolation_warnings(monkeypatch):
    seen = []
    monkeypatch.setattr(isolation_module.QMessageBox, 'warning', staticmethod(lambda *a, **k: seen.append(a[2])))
    return seen


class TestDialogIsolation:
    def test_tags_are_scoped_to_the_type_and_autofill_the_description(self, qtbot, isolation_warnings):
        d = DialogIsolation(None)
        qtbot.addWidget(d)
        assert d.typeCombo.currentData() == 'Mechanical'
        assert d.boxTag.currentText() == 'XV-7227A'
        assert d.boxDescription.toPlainText() == 'MC-A 1nd Stage ASV'
        mech = [d.boxTag.itemText(i) for i in range(d.boxTag.count())]
        assert set(mech) == {t for t, iso in PTW.ALL_ISOLATIONS.items() if iso.type == Isolation.Types.MECHANICAL}
        set_combo(d.typeCombo, 'Electrical')
        elec = [d.boxTag.itemText(i) for i in range(d.boxTag.count())]
        assert '1M1' in elec and 'XV-7227A' not in elec
        assert d.boxDescription.toPlainText() == PTW.ALL_ISOLATIONS[elec[0]].description

    def test_unknown_tag_clears_the_description(self, qtbot, isolation_warnings):
        d = DialogIsolation(None)
        qtbot.addWidget(d)
        d.boxTag.setCurrentText('NEW-TAG')
        d.boxTag.itemSelected.emit('NEW-TAG')
        assert d.boxDescription.toPlainText() == ''

    def test_accept_validates_then_builds_the_isolation(self, qtbot, isolation_warnings):
        d = DialogIsolation(None)
        qtbot.addWidget(d)
        set_combo(d.typeCombo, 'Other')
        d.boxTag.setCurrentText('')
        d.accept()
        assert isolation_warnings == ['Please select a tag or enter a new one.']
        d.boxTag.setCurrentText('NEW-TAG')
        d.boxDescription.setPlainText('')
        d.accept()
        assert isolation_warnings[-1] == 'Please enter a description.'
        assert d.getIsolation() is None
        d.boxDescription.setPlainText('Hand valve')
        d.accept()
        iso = d.getIsolation()
        assert d.result() == QDialog.DialogCode.Accepted
        assert (iso.type, iso.tag, iso.description) == ('Other', 'NEW-TAG', 'Hand valve')


# =========================================================================================
# DialogCompleteIsolation
# =========================================================================================

class TestDialogCompleteIsolation:
    def test_only_lock_columns_are_editable_and_edits_stay_on_copies(self, qtbot):
        items = [new_item('XV-7227A'), new_item('1M1', 'BC-A Enclosure Lighting', IC.IsolationItem.States.OPEN).setLockNum('OLD')]
        d = DialogCompleteIsolation(None, items)
        qtbot.addWidget(d)
        assert d.tbl.rowCount() == 2
        assert [d.tbl.item(1, c).text() for c in range(5)] == ['1M1', 'BC-A Enclosure Lighting', 'open', 'OLD', '']
        for col in range(5):
            editable = bool(d.tbl.item(0, col).flags() & Qt.ItemFlag.ItemIsEditable)
            assert editable == (col in (3, 4)), col
        d.tbl.item(0, 3).setText('L1'); d.tbl.item(0, 4).setText('BOX-A')
        d.tbl.item(1, 3).setText('L2')
        result = d.getItems()
        assert [(i.tag, i.lock_num, i.lock_box_num) for i in result] == [('XV-7227A', 'L1', 'BOX-A'), ('1M1', 'L2', '')]
        assert all(r is not o for r, o in zip(result, items))
        assert (items[0].lock_num, items[1].lock_num) == ('', 'OLD')          # caller's list untouched

    def test_empty_item_list_builds_an_empty_table(self, qtbot):
        d = DialogCompleteIsolation(None, [])
        qtbot.addWidget(d)
        assert d.tbl.rowCount() == 0 and d.getItems() == []


# =========================================================================================
# DialogDefinePsicTerms
# =========================================================================================

@pytest.fixture
def psic_messages(monkeypatch):
    seen = []
    for kind in ('warning', 'information'):
        monkeypatch.setattr(psic_module.QMessageBox, kind,
                            staticmethod(lambda *a, _k=kind, **k: seen.append((_k, a[1], a[2]))))
    return seen


class TestDialogDefinePsicTerms:
    def test_prefills_from_the_ic(self, qtbot, psic_messages):
        ic = make_ic(id=9, items=[dict(tag='XV-3615E', description='x', state='close'), dict(tag='Z-1', description='y', state='open')],
                     psic_reasons=['Gas Detection'], psic_moc_number='MOC-1', psic_system_description='sys')
        d = DialogDefinePsicTerms(None, ic)
        qtbot.addWidget(d)
        assert d.windowTitle() == 'Define PSIC Terms — IC #9'
        assert [d.tagCombo.itemText(i) for i in range(d.tagCombo.count())] == ['XV-3615E', 'Z-1']
        assert d.boxMocNumber.text() == 'MOC-1'
        assert {r for r, b in d.reasonCheckboxes.items() if b.isChecked()} == {'Gas Detection'}
        assert set(d.reasonCheckboxes) == set(PSIC_REASONS)
        assert d.boxSystemDescription.toPlainText() == 'sys' and d.boxIsolationMethod.toPlainText() == ''

    def test_autofill_from_a_known_tag_overwrites_reasons_and_fields(self, qtbot, psic_messages):
        ic = make_ic(id=9, items=[dict(tag='SDV-6514', description='x', state='close')], psic_reasons=['Other'],
                     psic_control_measures='old text')
        d = DialogDefinePsicTerms(None, ic)
        qtbot.addWidget(d)
        d.btnAutofill.click()
        sample = PSIC_TAG_SAMPLES['SDV-6514']
        assert psic_messages == []
        assert {r for r, b in d.reasonCheckboxes.items() if b.isChecked()} == set(sample['reasons']) == {'ESD', 'Fire Protection'}
        assert d.boxSystemDescription.toPlainText() == sample['system_description']
        assert d.boxIsolationMethod.toPlainText() == sample['isolation_method']
        assert d.boxControlMeasures.toPlainText() == sample['control_measures']

    def test_autofill_explains_when_there_is_nothing_to_fill_from(self, qtbot, psic_messages):
        d = DialogDefinePsicTerms(None, make_ic(id=9, items=[]))
        qtbot.addWidget(d)
        d.btnAutofill.click()
        assert psic_messages == [('information', 'No Tag Selected', 'Add an isolation item first, then pick its tag to autofill from.')]
        d2 = DialogDefinePsicTerms(None, make_ic(id=9, items=[dict(tag='Z-1', description='y', state='open')]))
        qtbot.addWidget(d2)
        d2.btnAutofill.click()
        assert psic_messages[-1] == ('information', 'No Sample Data',
                                     "No sample isolation data is defined yet for tag 'Z-1'. Please fill in the fields manually.")

    def test_accept_requires_a_reason_and_all_three_fields(self, qtbot, psic_messages):
        d = DialogDefinePsicTerms(None, make_ic(id=9))
        qtbot.addWidget(d)
        d.accept()
        assert psic_messages == [('warning', 'Invalid Input', 'Please select at least one PSIC reason.')]
        d.reasonCheckboxes['ESD'].setChecked(True)
        d.boxSystemDescription.setPlainText('sys'); d.boxIsolationMethod.setPlainText('meth')
        d.boxControlMeasures.setPlainText('   ')
        d.accept()
        assert psic_messages[-1][2].startswith('Please fill in the system to be isolated')
        assert d.result() != QDialog.DialogCode.Accepted

    def test_get_terms_strips_and_lists_checked_reasons_in_canonical_order(self, qtbot, psic_messages):
        d = DialogDefinePsicTerms(None, make_ic(id=9))
        qtbot.addWidget(d)
        d.reasonCheckboxes['Other'].setChecked(True)
        d.reasonCheckboxes['ESD'].setChecked(True)
        d.boxMocNumber.setText('  MOC-7 ')
        d.boxSystemDescription.setPlainText(' sys ')
        d.boxIsolationMethod.setPlainText('meth')
        d.boxControlMeasures.setPlainText('ctl\n')
        d.accept()
        assert d.result() == QDialog.DialogCode.Accepted
        assert d.getTerms() == {
            'psic_reasons': ['ESD', 'Other'], 'psic_moc_number': 'MOC-7',
            'psic_system_description': 'sys', 'psic_isolation_method': 'meth', 'psic_control_measures': 'ctl',
        }
