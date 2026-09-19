"""MainWindow action handlers, driven the way a context-menu option would drive them.

Each test puts records in the right state into `globalData`, builds the role window, calls
the handler with `(row, record)`, and asserts the exact `ClientRequests` call that leaves -
with every confirmation prompt replaced by a double (see mw_helpers) so the outcome is
scripted: confirmed, cancelled, or a canned value collected. Also: the PA alarm poll, IC
SSE patching, and the theme / language / logout footer actions.
"""

from datetime import timedelta

import pytest
from freezegun import freeze_time
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from GlobalData import globalData
from models.PTW import PTW
from models.Isolation import IC
from models.User import UserRoles, UserDepartments
from conftest import make_user
from ptw_factory import make_ptw, approved_ptw, approval, running_cycle, COORD, ISSUING, HSE
from mw_helpers import (record_requests, only_call, install_prompts, FakeMessageBox, FakeInputDialog, fake_dialog,
                        ACCEPTED, REJECTED, ic_in, ISSUING_OK, FROZEN, FROZEN_TS, NOW)

pytestmark = pytest.mark.gui

YES, NO = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No


def put_ptw(ptw):
    globalData.allPTWs[ptw.id] = ptw
    return ptw


def put_ic(ic):
    globalData.ics[ic.id] = ic
    return ic


def waiting_run(pid, pa='user_turbo'):
    return approved_ptw(approved_at=NOW - timedelta(hours=3), id=pid, run_cycles=[dict(run_pa=pa, run_pa_timestamp='x')])


def running(pid, **cycle_over):
    cycle = running_cycle(NOW - timedelta(hours=1))
    cycle.update(cycle_over)
    return approved_ptw(approved_at=NOW - timedelta(hours=3), id=pid, run_cycles=[cycle])


@pytest.fixture
def prompts(monkeypatch):
    install_prompts(monkeypatch)
    return FakeMessageBox


@pytest.fixture
def windows(offline_window):
    """Role window factory keyed by role; the User is user_turbo / Turbo."""
    from windows.UserMainWindow import UserMainWindow
    from windows.IssuingMainWindow import IssuingMainWindow
    from windows.CoordinatorMainWindow import CoordinatorMainWindow
    from windows.IsolatorMainWindow import IsolatorMainWindow
    from windows.GasTesterMainWindow import GasTesterMainWindow

    def build(role):
        if role == UserRoles.USER:
            return offline_window(UserMainWindow, make_user())
        if role == UserRoles.ISSUING:
            return offline_window(IssuingMainWindow, make_user('issuing', UserRoles.ISSUING, UserDepartments.PROD))
        if role == UserRoles.COORDINATOR:
            return offline_window(CoordinatorMainWindow, make_user('coord', UserRoles.COORDINATOR, UserDepartments.PROD))
        if role == UserRoles.ISOLATOR:
            return offline_window(IsolatorMainWindow, make_user('iso', UserRoles.ISOLATOR, UserDepartments.PROD))
        if role == UserRoles.GAS_TESTER:
            return offline_window(GasTesterMainWindow, make_user('gas', UserRoles.GAS_TESTER, UserDepartments.PROD))
        raise KeyError(role)
    return build


# ---- run cycle: request / accept / reject --------------------------------------------------------

class TestRunRequest:
    def test_confirmed_run_request_names_the_pa_and_the_moment(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        confirm = fake_dialog(monkeypatch, 'DialogConfirmRunRequest')
        log = record_requests(monkeypatch, 'requestToRunPTW')
        with freeze_time(FROZEN):
            w.requestToRunPTW(0, ptw)
        user, args, kwargs = only_call(log, 'requestToRunPTW')
        assert user is w.loggedUser
        assert args == (1, 'user_turbo', FROZEN_TS)
        # the dialog was shown for this PTW with its (here: none) linked ICs
        (dlg_args, _), = confirm.instances
        assert dlg_args[2] is ptw and dlg_args[3] == []

    def test_run_request_dialog_lists_the_linked_ics_from_the_cache(self, windows, prompts, monkeypatch):
        ic7 = put_ic(ic_in(IC.Status.ACTIVE, id=7))
        put_ic(ic_in(IC.Status.ACTIVE, id=8))
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1, linked_ics=['7', '99']))
        w = windows(UserRoles.USER)
        confirm = fake_dialog(monkeypatch, 'DialogConfirmRunRequest')
        record_requests(monkeypatch, 'requestToRunPTW')
        w.requestToRunPTW(0, ptw)
        (dlg_args, _), = confirm.instances
        assert dlg_args[3] == [ic7]                      # unknown id 99 silently dropped, 8 not linked

    def test_cancelled_run_request_sends_nothing(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        fake_dialog(monkeypatch, 'DialogConfirmRunRequest', result=REJECTED)
        log = record_requests(monkeypatch, 'requestToRunPTW')
        w.requestToRunPTW(0, ptw)
        assert log == []

    def test_a_pa_already_on_another_ptw_is_refused_before_any_dialog(self, windows, prompts, monkeypatch):
        put_ptw(waiting_run(5, pa='user_turbo'))
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        confirm = fake_dialog(monkeypatch, 'DialogConfirmRunRequest')
        log = record_requests(monkeypatch, 'requestToRunPTW')
        w.requestToRunPTW(0, ptw)
        assert log == [] and confirm.instances == []
        assert prompts.warnings == [('Not Allowed', 'You are already the PA for PTW# 5.')]


class TestRunResponse:
    @pytest.mark.parametrize('handler, accepted', [('runAcceptTW', True), ('runRejectTW', False)])
    def test_response_carries_the_ia_flag_and_comment(self, windows, prompts, monkeypatch, handler, accepted):
        ptw = put_ptw(waiting_run(6))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('checked on site')
        log = record_requests(monkeypatch, 'runResponsePTW')
        with freeze_time(FROZEN):
            getattr(w, handler)(0, ptw)
        user, args, kwargs = only_call(log, 'runResponsePTW')
        assert user is w.loggedUser
        assert args == (6, 'issuing', FROZEN_TS, accepted, 'checked on site')

    def test_blank_comment_is_sent_as_none(self, windows, prompts, monkeypatch):
        ptw = put_ptw(waiting_run(6))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('')
        log = record_requests(monkeypatch, 'runResponsePTW')
        w.runAcceptTW(0, ptw)
        _, args, _ = only_call(log, 'runResponsePTW')
        assert args[3] is True and args[4] is None

    @pytest.mark.parametrize('handler', ['runAcceptTW', 'runRejectTW'])
    def test_cancelling_the_comment_prompt_sends_nothing(self, windows, prompts, monkeypatch, handler):
        ptw = put_ptw(waiting_run(6))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('typed then cancelled', ok=False)
        log = record_requests(monkeypatch, 'runResponsePTW')
        getattr(w, handler)(0, ptw)
        assert log == []

    def test_server_error_from_the_response_is_shown_as_a_failure(self, windows, prompts, monkeypatch):
        from network.clientRequests import ClientRequests
        ptw = put_ptw(waiting_run(6))
        w = windows(UserRoles.ISSUING)
        monkeypatch.setattr(ClientRequests, 'runResponsePTW', staticmethod(lambda *a, callback=None, **k: callback('PTW 6 is not waiting', None)))
        w.runAcceptTW(0, ptw)
        assert prompts.warnings == [('Fail', 'PTW 6 is not waiting')]


# ---- hold ------------------------------------------------------------------------------------------

class TestHoldRequest:
    def test_hold_with_linked_ics_sends_the_ones_the_pa_chose_to_keep_held(self, windows, prompts, monkeypatch):
        ic7, ic8 = put_ic(ic_in(IC.Status.ACTIVE, id=7)), put_ic(ic_in(IC.Status.ACTIVE, id=8))
        ptw = put_ptw(running(2, run_pa='user_turbo'))
        ptw.linked_ics = ['7', '8']
        w = windows(UserRoles.USER)
        select = fake_dialog(monkeypatch, 'DialogSelectHeldICs', getHeldICIds=['7'])
        FakeInputDialog.answer('pump swap paused')
        log = record_requests(monkeypatch, 'requestToHldPTW')
        with freeze_time(FROZEN):
            w.requestToHldPTW(0, ptw)
        user, args, kwargs = only_call(log, 'requestToHldPTW')
        assert args == (2, 'user_turbo', FROZEN_TS, 'pump swap paused', ['7'])
        (dlg_args, dlg_kwargs), = select.instances
        assert dlg_args[1] == [ic7, ic8] and dlg_kwargs['selectable'] is True

    def test_hold_without_linked_ics_skips_the_selection_dialog(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(2))
        w = windows(UserRoles.USER)
        select = fake_dialog(monkeypatch, 'DialogSelectHeldICs', getHeldICIds=['should not be asked'])
        FakeInputDialog.answer('')
        log = record_requests(monkeypatch, 'requestToHldPTW')
        w.requestToHldPTW(0, ptw)
        _, args, _ = only_call(log, 'requestToHldPTW')
        assert args[3] is None and args[4] == []
        assert select.instances == []

    def test_cancelling_the_ic_selection_aborts_before_the_comment(self, windows, prompts, monkeypatch):
        put_ic(ic_in(IC.Status.ACTIVE, id=7))
        ptw = put_ptw(running(2))
        ptw.linked_ics = ['7']
        w = windows(UserRoles.USER)
        fake_dialog(monkeypatch, 'DialogSelectHeldICs', result=REJECTED, getHeldICIds=['7'])
        log = record_requests(monkeypatch, 'requestToHldPTW')
        w.requestToHldPTW(0, ptw)
        assert log == [] and FakeInputDialog.calls == []

    def test_cancelling_the_comment_aborts_the_hold(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(2))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'requestToHldPTW')
        w.requestToHldPTW(0, ptw)
        assert log == []


class TestHoldTakeAction:
    def waiting_hold(self, held=('7',)):
        ptw = put_ptw(running(3, stop_pa='user_turbo', stop_pa_request='Hold', held_ics=list(held)))
        assert ptw.running_status == PTW.RunningStatus.WAITING_HLD_CONFIRM
        return ptw

    @pytest.mark.parametrize('action, accepted', [('accept', True), ('reject', False)])
    def test_review_decision_becomes_the_hold_response(self, windows, prompts, monkeypatch, action, accepted):
        put_ic(ic_in(IC.Status.ACTIVE, id=7))
        ptw = self.waiting_hold()
        ptw.linked_ics = ['7']
        w = windows(UserRoles.ISSUING)
        review = fake_dialog(monkeypatch, 'DialogSelectHeldICs', action=action)
        FakeInputDialog.answer('noted')
        log = record_requests(monkeypatch, 'hldResponsePTW')
        with freeze_time(FROZEN):
            w.hldTakeAction(0, ptw)
        user, args, _ = only_call(log, 'hldResponsePTW')
        assert user is w.loggedUser
        assert args == (3, 'issuing', FROZEN_TS, accepted, 'noted')
        (dlg_args, dlg_kwargs), = review.instances
        assert dlg_kwargs['held'] == ['7'] and dlg_kwargs['review_mode'] is True and dlg_kwargs['selectable'] is False
        assert [ic.id for ic in dlg_args[1]] == [7]

    def test_refused_when_the_ptw_is_not_waiting_for_hold_confirmation(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(3))
        w = windows(UserRoles.ISSUING)
        review = fake_dialog(monkeypatch, 'DialogSelectHeldICs', action='accept')
        log = record_requests(monkeypatch, 'hldResponsePTW')
        w.hldTakeAction(0, ptw)
        assert log == [] and review.instances == []
        assert prompts.warnings == [('Not Allowed', 'PTW# 3 is not waiting for hold confirmation.')]

    def test_closing_the_review_without_a_decision_sends_nothing(self, windows, prompts, monkeypatch):
        ptw = self.waiting_hold()
        w = windows(UserRoles.ISSUING)
        fake_dialog(monkeypatch, 'DialogSelectHeldICs', result=REJECTED, action='accept')
        log = record_requests(monkeypatch, 'hldResponsePTW')
        w.hldTakeAction(0, ptw)
        fake_dialog(monkeypatch, 'DialogSelectHeldICs', result=ACCEPTED, action=None)     # accepted, but no verdict
        w.hldTakeAction(0, ptw)
        assert log == [] and FakeInputDialog.calls == []

    def test_cancelling_the_comment_after_deciding_sends_nothing(self, windows, prompts, monkeypatch):
        ptw = self.waiting_hold()
        w = windows(UserRoles.ISSUING)
        fake_dialog(monkeypatch, 'DialogSelectHeldICs', action='reject')
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'hldResponsePTW')
        w.hldTakeAction(0, ptw)
        assert log == []


# ---- close -------------------------------------------------------------------------------------------

class TestClose:
    def test_close_request_carries_pa_and_comment(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(2))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('job done')
        log = record_requests(monkeypatch, 'requestToClsPTW')
        with freeze_time(FROZEN):
            w.requestToClsPTW(0, ptw)
        user, args, _ = only_call(log, 'requestToClsPTW')
        assert user is w.loggedUser and args == (2, 'user_turbo', FROZEN_TS, 'job done')

    def test_close_request_cancelled(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(2))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'requestToClsPTW')
        w.requestToClsPTW(0, ptw)
        assert log == []

    @pytest.mark.parametrize('handler, accepted', [('clsAcceptPTW', True), ('clsRejectPTW', False)])
    def test_close_response(self, windows, prompts, monkeypatch, handler, accepted):
        ptw = put_ptw(running(4, stop_pa='user_turbo', stop_pa_request='Close'))
        assert ptw.running_status == PTW.RunningStatus.WAITING_CLS_CONFIRM
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('ok')
        log = record_requests(monkeypatch, 'clsResponsePTW')
        with freeze_time(FROZEN):
            getattr(w, handler)(0, ptw)
        _, args, _ = only_call(log, 'clsResponsePTW')
        assert args == (4, 'issuing', FROZEN_TS, accepted, 'ok')

    def test_close_response_cancelled(self, windows, prompts, monkeypatch):
        ptw = put_ptw(running(4, stop_pa='user_turbo', stop_pa_request='Close'))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'clsResponsePTW')
        w.clsAcceptPTW(0, ptw)
        w.clsRejectPTW(0, ptw)
        assert log == []


# ---- gas test ---------------------------------------------------------------------------------------

class TestGasTest:
    READINGS = [{'gas': g, 'percentage': 0.0} for g in PTW.GAS_TEST_TYPES]

    def test_one_reading_is_recorded_for_every_selected_ptw_in_one_request(self, windows, prompts, monkeypatch):
        ptws = [put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=i)) for i in (11, 12, 13)]
        w = windows(UserRoles.GAS_TESTER)
        dlg = fake_dialog(monkeypatch, 'DialogGasTest', getReadings=self.READINGS, getComment='calm wind')
        log = record_requests(monkeypatch, 'recordGasTestPTW')
        with freeze_time(FROZEN):
            w.recordGasTestPTW([0, 1, 2], ptws)
        user, args, _ = only_call(log, 'recordGasTestPTW')
        assert user is w.loggedUser
        assert args == ([11, 12, 13], self.READINGS, FROZEN_TS, 'calm wind')
        (dlg_args, _), = dlg.instances
        assert dlg_args[1] == ptws                          # the dialog is opened once, for the whole batch

    def test_cancelled_gas_test_dialog_records_nothing(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=11))
        w = windows(UserRoles.GAS_TESTER)
        fake_dialog(monkeypatch, 'DialogGasTest', result=REJECTED, getReadings=self.READINGS, getComment=None)
        log = record_requests(monkeypatch, 'recordGasTestPTW')
        w.recordGasTestPTW([0], [ptw])
        assert log == []

    def test_empty_selection_opens_no_dialog(self, windows, prompts, monkeypatch):
        w = windows(UserRoles.GAS_TESTER)
        dlg = fake_dialog(monkeypatch, 'DialogGasTest', getReadings=self.READINGS, getComment=None)
        log = record_requests(monkeypatch, 'recordGasTestPTW')
        w.recordGasTestPTW([], [])
        assert log == [] and dlg.instances == []


# ---- approval chain: accept / request edits / delete / archive ------------------------------------------

class TestPtwApproval:
    def test_accept_records_an_approved_action_by_the_viewer(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=1))
        w = windows(UserRoles.COORDINATOR)
        log = record_requests(monkeypatch, 'updateApprovalPTW')
        with freeze_time(FROZEN):
            w.acceptPTW(0, ptw)
        user, args, _ = only_call(log, 'updateApprovalPTW')
        assert user is w.loggedUser and args[0] == 1
        a = args[1]
        assert (a.action, a.username, a.timestamp, a.comment) == (PTW.ApprovalActions.APPROVED, 'coord', FROZEN_TS, None)
        assert prompts.questions == [('Accept PTW#1', 'Are you sure you want to approve request for PTW#1? This is irreversible')]

    def test_accept_declined(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=1))
        w = windows(UserRoles.COORDINATOR)
        prompts.exec_result = NO
        log = record_requests(monkeypatch, 'updateApprovalPTW')
        w.acceptPTW(0, ptw)
        assert log == []

    def test_request_edits_records_a_returned_action_with_the_mandatory_comment(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=1))
        w = windows(UserRoles.COORDINATOR)
        FakeInputDialog.answer('missing MoS step')
        log = record_requests(monkeypatch, 'updateApprovalPTW')
        with freeze_time(FROZEN):
            w.requestEditsPTW(0, ptw)
        _, args, _ = only_call(log, 'updateApprovalPTW')
        a = args[1]
        assert args[0] == 1
        assert (a.action, a.username, a.timestamp, a.comment) == (PTW.ApprovalActions.RETURNED, 'coord', FROZEN_TS, 'missing MoS step')

    def test_request_edits_cancelled_sends_nothing(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=1))
        w = windows(UserRoles.COORDINATOR)
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'updateApprovalPTW')
        w.requestEditsPTW(0, ptw)
        assert log == []

    def test_request_edits_insists_on_a_non_empty_comment(self, windows, prompts, monkeypatch):
        """getComment() re-prompts after an empty OK until text is typed or the prompt is cancelled."""
        ptw = put_ptw(make_ptw(id=1))
        w = windows(UserRoles.COORDINATOR)
        answers = iter([('', True), ('', True), ('now with text', True)])

        def scripted(parent, title, label, *a, **k):
            return next(answers)

        monkeypatch.setattr(FakeInputDialog, 'getMultiLineText', staticmethod(scripted))
        log = record_requests(monkeypatch, 'updateApprovalPTW')
        w.requestEditsPTW(0, ptw)
        assert prompts.warnings == [('Not Allowed', 'Empty comment not allowed')] * 2
        _, args, _ = only_call(log, 'updateApprovalPTW')
        assert args[1].comment == 'now with text'

    def test_delete_goes_through_the_current_tab_and_drops_the_row(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=4, approvals=[approval(*COORD, action='Returned')]))
        w = windows(UserRoles.USER)
        tab = w.tabReturnedPTWs
        assert [p.id for p in tab.ptwsData] == [4]
        w.stack.setCurrentWidget(tab)
        log = record_requests(monkeypatch, 'deletePTW')
        w.deletePTW(0, ptw)
        user, args, _ = only_call(log, 'deletePTW')
        assert user is w.loggedUser and args == (4,)
        assert tab.ptwsData == [] and tab.tbl.rowCount() == 0
        assert prompts.questions == [('Delete PTW', "Are you sure you want to delete PTW# '4'?")]

    def test_delete_declined_keeps_the_row(self, windows, prompts, monkeypatch):
        ptw = put_ptw(make_ptw(id=4, approvals=[approval(*COORD, action='Returned')]))
        w = windows(UserRoles.USER)
        w.stack.setCurrentWidget(w.tabReturnedPTWs)
        prompts.exec_result = NO
        log = record_requests(monkeypatch, 'deletePTW')
        w.deletePTW(0, ptw)
        assert log == [] and [p.id for p in w.tabReturnedPTWs.ptwsData] == [4]

    def test_archive_is_one_bulk_request_of_ids(self, windows, prompts, monkeypatch):
        ptws = [put_ptw(running(i, stop_pa='u', stop_pa_request='Close', stop_ia='i', stop_ia_action='Approved', stop_ia_timestamp='x')) for i in (21, 22)]
        w = windows(UserRoles.USER)
        assert [p.id for p in w.tabClosedPTWs.ptwsData] == [21, 22]
        log = record_requests(monkeypatch, 'archivePTWs')
        w.archivePTWs([0, 1], ptws)
        user, args, _ = only_call(log, 'archivePTWs')
        assert user is w.loggedUser and args == ([21, 22],)


