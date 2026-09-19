"""IC-side MainWindow action handlers, and the cross-cutting bits that don't belong to a
single PTW action: the isolate/de-isolate cycle, PTW<->IC linking, the PA run-cycle/validity
alarm poll, IC SSE patching, and the theme/language/logout footer actions.

Same doubles as `test_main_window_actions.py` (see `mw_helpers`): every confirmation dialog
is replaced so the outcome is scripted, and `ClientRequests` methods are replaced with
recorders that hand the callback a canned reply.
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


# ---- IC approval ----------------------------------------------------------------------------------------

class TestIcApproval:
    def test_issuing_accept_with_the_psic_box_unticked(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7))
        w = windows(UserRoles.ISSUING)
        assert [x.id for x in w.tabUnderReviewICs.icsData] == [7]
        log = record_requests(monkeypatch, 'updateApprovalIC')
        with freeze_time(FROZEN):
            w.acceptIC(0, ic)
        user, args, kwargs = only_call(log, 'updateApprovalIC')
        assert user is w.loggedUser and args[0] == 7
        a = args[1]
        assert (a.action, a.username, a.timestamp, a.comment) == (IC.ApprovalActions.APPROVED, 'issuing', FROZEN_TS, None)
        assert kwargs == {'mark_psic': False}
        assert prompts.shown == [dict(title='Accept IC #7', text='Are you sure you want to approve IC #7? This is irreversible',
                                      checkbox='Protective System IC (PSIC)')]

    def test_issuing_accept_ticking_the_psic_box_flags_the_ic(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7))
        w = windows(UserRoles.ISSUING)
        prompts.on_exec = lambda box: box.checkBox().setChecked(True)
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)
        _, _, kwargs = only_call(log, 'updateApprovalIC')
        assert kwargs == {'mark_psic': True}

    def test_issuing_accept_declined(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7))
        w = windows(UserRoles.ISSUING)
        prompts.exec_result = NO
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)
        assert log == []

    def test_issuing_is_warned_about_a_tag_already_isolated_elsewhere(self, windows, prompts, monkeypatch):
        put_ic(ic_in(IC.Status.ACTIVE, id=9, items=[{'tag': 'V-101'}]))
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7, items=[{'tag': 'V-101'}, {'tag': 'V-102'}]))
        w = windows(UserRoles.ISSUING)
        prompts.exec_result = NO                       # 'Approve anyway?' -> No
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)
        assert log == []
        (warn,) = prompts.shown
        assert warn['title'] == 'Possible Duplicate Isolation' and warn['checkbox'] is None
        assert 'Tag "V-101" — already Active on IC #9' in warn['text']
        assert 'V-102' not in warn['text']

    def test_issuing_may_approve_the_duplicate_anyway(self, windows, prompts, monkeypatch):
        put_ic(ic_in(IC.Status.ACTIVE, id=9, items=[{'tag': 'V-101'}]))
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7, items=[{'tag': 'V-101'}]))
        w = windows(UserRoles.ISSUING)
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)                              # Yes to the warning, Yes to the approval
        assert [b['title'] for b in prompts.shown] == ['Possible Duplicate Isolation', 'Accept IC #7']
        _, args, kwargs = only_call(log, 'updateApprovalIC')
        assert args[0] == 7 and kwargs == {'mark_psic': False}

    def test_closed_or_unapproved_ics_do_not_count_as_tag_conflicts(self, windows, prompts, monkeypatch):
        put_ic(ic_in(IC.Status.CLOSED, id=9, items=[{'tag': 'V-101'}]))
        put_ic(ic_in(IC.Status.REQUESTED, id=10, items=[{'tag': 'V-101'}]))
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7, items=[{'tag': 'V-101'}]))
        w = windows(UserRoles.ISSUING)
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)
        assert [b['title'] for b in prompts.shown] == ['Accept IC #7']
        only_call(log, 'updateApprovalIC')

    def test_coordinator_approving_a_psic_supplies_its_terms(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7, is_psic=True, approvals=[ISSUING_OK]))
        w = windows(UserRoles.COORDINATOR)
        assert [x.id for x in w.tabUnderReviewICs.icsData] == [7]
        terms = {'psic_reasons': ['Maintenance'], 'psic_moc_number': 'MOC-1', 'psic_system_description': 'ESD loop',
                 'psic_isolation_method': 'Bypass', 'psic_control_measures': 'Watch'}
        fake_dialog(monkeypatch, 'DialogDefinePsicTerms', getTerms=terms)
        log = record_requests(monkeypatch, 'updateApprovalIC')
        with freeze_time(FROZEN):
            w.acceptIC(0, ic)
        _, args, kwargs = only_call(log, 'updateApprovalIC')
        assert args[0] == 7 and args[1].action == IC.ApprovalActions.APPROVED and args[1].username == 'coord'
        assert kwargs == {'psic_terms': terms}
        assert prompts.shown == []                     # the terms dialog's OK is the confirmation

    def test_coordinator_cancelling_the_psic_terms_sends_nothing(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7, is_psic=True, approvals=[ISSUING_OK]))
        w = windows(UserRoles.COORDINATOR)
        fake_dialog(monkeypatch, 'DialogDefinePsicTerms', result=REJECTED, getTerms={})
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.acceptIC(0, ic)
        assert log == []

    def test_request_edits_on_an_ic(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('wrong tag numbers')
        log = record_requests(monkeypatch, 'updateApprovalIC')
        with freeze_time(FROZEN):
            w.requestEditsIC(0, ic)
        _, args, kwargs = only_call(log, 'updateApprovalIC')
        a = args[1]
        assert args[0] == 7 and kwargs == {}
        assert (a.action, a.username, a.timestamp, a.comment) == (IC.ApprovalActions.RETURNED, 'issuing', FROZEN_TS, 'wrong tag numbers')

    def test_request_edits_on_an_ic_cancelled(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.REQUESTED, id=7))
        w = windows(UserRoles.ISSUING)
        FakeInputDialog.answer('', ok=False)
        log = record_requests(monkeypatch, 'updateApprovalIC')
        w.requestEditsIC(0, ic)
        assert log == []


# ---- isolate / de-isolate cycle ----------------------------------------------------------------------------

SIMPLE_IC_ACTIONS = [
    # handler,             role,                 IC status to act on,             request,             extra args after icId
    ('requestIsolateIC',   UserRoles.USER,       IC.Status.APPROVED,              'requestIsolateIC',   ()),
    ('confirmIsolateIC',   UserRoles.ISSUING,    IC.Status.ISOLATE_CONFIRMING,    'confirmIsolateIC',   (True,)),
    ('returnIsolateIC',    UserRoles.ISSUING,    IC.Status.ISOLATE_CONFIRMING,    'confirmIsolateIC',   (False,)),
    ('requestDeisolateIC', UserRoles.USER,       IC.Status.ACTIVE,                'requestDeisolateIC', ()),
    ('confirmDeisolateIC', UserRoles.ISSUING,    IC.Status.DEISOLATE_CONFIRMING,  'confirmDeisolateIC', (True,)),
    ('returnDeisolateIC',  UserRoles.ISSUING,    IC.Status.DEISOLATE_CONFIRMING,  'confirmDeisolateIC', (False,)),
    ('executeDeisolateIC', UserRoles.ISOLATOR,   IC.Status.CLOSING,               'executeDeisolateIC', ()),
]


class TestIsolationCycle:
    @pytest.mark.parametrize('handler, role, status, req, extra', SIMPLE_IC_ACTIONS, ids=[a[0] for a in SIMPLE_IC_ACTIONS])
    def test_confirmed_action_sends_exactly_one_request(self, windows, prompts, monkeypatch, handler, role, status, req, extra):
        ic = put_ic(ic_in(status, id=7))
        w = windows(role)
        log = record_requests(monkeypatch, req)
        getattr(w, handler)(0, ic)
        user, args, kwargs = only_call(log, req)
        assert user is w.loggedUser
        assert args == (7,) + extra and kwargs == {}
        assert len(prompts.questions) == 1 and '#7' in prompts.questions[0][0]

    @pytest.mark.parametrize('handler, role, status, req, extra', SIMPLE_IC_ACTIONS, ids=[a[0] for a in SIMPLE_IC_ACTIONS])
    def test_declined_action_sends_nothing(self, windows, prompts, monkeypatch, handler, role, status, req, extra):
        ic = put_ic(ic_in(status, id=7))
        w = windows(role)
        prompts.exec_result = NO
        log = record_requests(monkeypatch, req)
        getattr(w, handler)(0, ic)
        assert log == []

    def test_execute_isolation_with_items_sends_the_lock_details_from_the_dialog(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.PENDING, id=7, items=[{'tag': 'V-1'}, {'tag': 'V-2'}]))
        w = windows(UserRoles.ISOLATOR)
        assert [x.id for x in w.tabPendingICs.icsData] == [7]
        locked = [IC.IsolationItem('V-1').setLockNum('L1').setLockBoxNum('B1'), IC.IsolationItem('V-2').setLockNum('L2').setLockBoxNum('B1')]
        dlg = fake_dialog(monkeypatch, 'DialogCompleteIsolation', getItems=locked)
        log = record_requests(monkeypatch, 'executeIsolateIC')
        w.executeIsolateIC(0, ic)
        user, args, _ = only_call(log, 'executeIsolateIC')
        assert user is w.loggedUser and args == (7, locked)
        (dlg_args, _), = dlg.instances
        assert dlg_args[1] is ic.items
        assert prompts.questions == []                 # the items dialog replaces the yes/no prompt

    def test_execute_isolation_without_items_just_confirms(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.PENDING, id=7))
        w = windows(UserRoles.ISOLATOR)
        dlg = fake_dialog(monkeypatch, 'DialogCompleteIsolation', getItems=['nope'])
        log = record_requests(monkeypatch, 'executeIsolateIC')
        w.executeIsolateIC(0, ic)
        _, args, _ = only_call(log, 'executeIsolateIC')
        assert args == (7, []) and dlg.instances == []
        assert prompts.questions == [('Complete Isolation #7', 'Confirm that isolation for IC #7 has been physically carried out?')]

    def test_execute_isolation_cancelled_in_the_items_dialog(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.PENDING, id=7, items=[{'tag': 'V-1'}]))
        w = windows(UserRoles.ISOLATOR)
        fake_dialog(monkeypatch, 'DialogCompleteIsolation', result=REJECTED, getItems=[])
        log = record_requests(monkeypatch, 'executeIsolateIC')
        w.executeIsolateIC(0, ic)
        assert log == []


# ---- linking ----------------------------------------------------------------------------------------------

class TestLinking:
    def test_link_ic_to_ptw_parses_the_ic_number(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer(' 12 ')
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkICToPTW(0, ptw)
        user, args, _ = only_call(log, 'linkPTWToIC')
        assert user is w.loggedUser and args == (12, 1)          # (icId, ptwId) - same endpoint from either side
        assert FakeInputDialog.calls == [('Link PTW #1 to IC', 'IC #:')]

    def test_link_ic_to_ptw_rejects_a_non_numeric_ic(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('IC-12')
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkICToPTW(0, ptw)
        assert log == [] and prompts.warnings == [('Invalid IC #', 'IC # must be a number.')]

    def test_link_ic_to_ptw_refuses_a_duplicate(self, windows, prompts, monkeypatch):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1, linked_ics=['12']))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('12')
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkICToPTW(0, ptw)
        assert log == [] and prompts.warnings == [('Already Linked', 'IC #12 is already linked to this PTW.')]

    @pytest.mark.parametrize('text, ok', [('', True), ('   ', True), ('12', False)])
    def test_link_ic_to_ptw_blank_or_cancelled(self, windows, prompts, monkeypatch, text, ok):
        ptw = put_ptw(approved_ptw(approved_at=NOW - timedelta(hours=3), id=1))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer(text, ok)
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkICToPTW(0, ptw)
        assert log == [] and prompts.warnings == []

    def test_link_ptw_to_ic_sends_the_trimmed_ptw_number(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.APPROVED, id=7))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer(' 3 ')
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkPTWToIC(0, ic)
        user, args, _ = only_call(log, 'linkPTWToIC')
        assert user is w.loggedUser and args == (7, '3')
        assert FakeInputDialog.calls == [('Link IC #7 to PTW', 'PTW #:')]

    def test_link_ptw_to_ic_refuses_a_duplicate(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.APPROVED, id=7))
        ic.linked_ptws = ['3']
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('3')
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkPTWToIC(0, ic)
        assert log == [] and prompts.warnings == [('Already Linked', 'PTW #3 is already linked to this IC.')]

    def test_link_ptw_to_ic_cancelled(self, windows, prompts, monkeypatch):
        ic = put_ic(ic_in(IC.Status.APPROVED, id=7))
        w = windows(UserRoles.USER)
        FakeInputDialog.answer('3', ok=False)
        log = record_requests(monkeypatch, 'linkPTWToIC')
        w.linkPTWToIC(0, ic)
        assert log == []


# ---- PA alarms -------------------------------------------------------------------------------------------------

def alarm_fixtures():
    """PTWs for user_turbo's department in each alarm state, plus the ones that must be ignored."""
    validity_expired = put_ptw(approved_ptw(approved_at=NOW - timedelta(days=10), id=1))                 # approved, idle, 14 shifts gone
    shift_expired = put_ptw(approved_ptw(approved_at=NOW - timedelta(days=2), id=2,
                                         run_cycles=[running_cycle(NOW - timedelta(days=1))]))          # still RUNNING past its shift
    both = put_ptw(approved_ptw(approved_at=NOW - timedelta(days=10), id=3,
                                run_cycles=[running_cycle(NOW - timedelta(days=9))]))
    put_ptw(approved_ptw(approved_at=NOW - timedelta(days=2), id=4, run_cycles=[running_cycle(NOW - timedelta(hours=1))]))  # healthy run
    closing = running_cycle(NOW - timedelta(days=1)); closing.update(stop_pa='u', stop_pa_request='Close')
    put_ptw(approved_ptw(approved_at=NOW - timedelta(days=10), id=5, run_cycles=[closing]))              # close already requested
    put_ptw(approved_ptw(approved_at=NOW - timedelta(days=10), id=6, department='Mech', requestor='user_mech'))  # other department
    put_ptw(make_ptw(id=7))                                                                              # not approved at all
    return validity_expired, shift_expired, both


class TestPtwAlarms:
    def test_user_is_alarmed_for_own_department_only_with_the_two_lists(self, windows):
        v, s, both = alarm_fixtures()
        w = windows(UserRoles.USER)
        shown = []
        w._showPtwAlarms = lambda validity, shift: shown.append(([p.id for p in validity], [p.id for p in shift]))
        with freeze_time(FROZEN):
            w._checkPtwAlarms()
        assert shown == [([1, 3], [2, 3])]

    def test_nothing_shown_when_nothing_is_overdue(self, windows):
        put_ptw(approved_ptw(approved_at=NOW - timedelta(days=2), id=4, run_cycles=[running_cycle(NOW - timedelta(hours=1))]))
        w = windows(UserRoles.USER)
        shown = []
        w._showPtwAlarms = lambda *lists: shown.append(lists)
        with freeze_time(FROZEN):
            w._checkPtwAlarms()
        assert shown == []

    def test_non_user_roles_are_never_alarmed(self, offline_window):
        from windows.IssuingMainWindow import IssuingMainWindow
        from windows.GuestMainWindow import GuestMainWindow
        alarm_fixtures()
        for cls, user in ((IssuingMainWindow, make_user('issuing', UserRoles.ISSUING, UserDepartments.PROD)),
                          (GuestMainWindow, make_user('guest', UserRoles.GUEST, UserDepartments.TURBO))):
            w = offline_window(cls, user)
            shown = []
            w._showPtwAlarms = lambda *lists: shown.append(lists)
            with freeze_time(FROZEN):
                w._checkPtwAlarms()
            assert shown == [], cls.__name__

    def test_dismissing_the_popup_snoozes_the_next_checks(self, windows, monkeypatch):
        alarm_fixtures()
        w = windows(UserRoles.USER)
        popup = fake_dialog(monkeypatch, 'DialogPtwAlarms')
        with freeze_time(FROZEN) as clock:
            w._checkPtwAlarms()
            assert len(popup.instances) == 1
            (args, _), = popup.instances
            assert [p.id for p in args[1]] == [1, 3] and [p.id for p in args[2]] == [2, 3]
            assert w._ptwAlarmSnoozeUntil == NOW + timedelta(minutes=w._PTW_ALARM_REPEAT_MINUTES)
            assert w._ptwAlarmDialogOpen is False

            clock.tick(timedelta(minutes=w._PTW_ALARM_REPEAT_MINUTES - 1))
            w._checkPtwAlarms()
            assert len(popup.instances) == 1                      # snoozed

            clock.tick(timedelta(minutes=1))
            w._checkPtwAlarms()
            assert len(popup.instances) == 2                      # still unresolved -> nagged again

    def test_no_second_popup_while_one_is_open(self, windows):
        alarm_fixtures()
        w = windows(UserRoles.USER)
        shown = []
        w._showPtwAlarms = lambda *lists: shown.append(lists)
        w._ptwAlarmDialogOpen = True
        with freeze_time(FROZEN):
            w._checkPtwAlarms()
        assert shown == []

    def test_alarm_poll_is_armed_at_construction(self, windows):
        w = windows(UserRoles.USER)
        assert w._ptwAlarmTimer.isActive() and w._ptwAlarmTimer.interval() == w._PTW_ALARM_CHECK_INTERVAL_MS


# ---- SSE events for ICs -------------------------------------------------------------------------------------------

def patch_get_ic(monkeypatch, expected_id, result):
    from network.clientRequests import ClientRequests
    asked = []

    def fake_get(loggedUser, icId, callback=None):
        asked.append(icId)
        assert icId == expected_id
        callback(None, result)

    monkeypatch.setattr(ClientRequests, 'getICById', staticmethod(fake_get))
    return asked


class TestIcSseEvents:
    def test_updated_ic_moves_between_tabs_and_replaces_the_cached_object(self, windows, monkeypatch):
        put_ic(ic_in(IC.Status.APPROVED, id=7))
        w = windows(UserRoles.USER)
        assert [x.id for x in w.tabApprovedICs.icsData] == [7]
        fresh = ic_in(IC.Status.ISOLATE_CONFIRMING, id=7)
        asked = patch_get_ic(monkeypatch, 7, fresh)

        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 7, 'action': 'isolate requested', 'by': 'user_turbo'})

        assert asked == [7]
        assert w.tabApprovedICs.icsData == []
        assert w.tabIsolateConfirmingICs.icsData == [fresh]
        assert globalData.ics[7] is fresh
        assert w.statusBar().currentMessage() == 'IC #7 isolate requested by user_turbo'

    def test_deleted_ic_is_removed_from_its_tab_and_the_cache(self, windows, monkeypatch):
        put_ic(ic_in(IC.Status.APPROVED, id=7))
        put_ic(ic_in(IC.Status.APPROVED, id=8))
        w = windows(UserRoles.USER)
        patch_get_ic(monkeypatch, 7, None)                     # server no longer has it
        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 7, 'action': 'deleted', 'by': 'user_turbo'})
        assert [x.id for x in w.tabApprovedICs.icsData] == [8]
        assert 7 not in globalData.ics and 8 in globalData.ics

    def test_network_error_leaves_tabs_and_cache_untouched(self, windows, monkeypatch):
        from network.clientRequests import ClientRequests
        old = put_ic(ic_in(IC.Status.APPROVED, id=7))
        w = windows(UserRoles.USER)
        monkeypatch.setattr(ClientRequests, 'getICById', staticmethod(lambda u, i, callback=None: callback('timeout', None)))
        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 7, 'action': 'isolate requested', 'by': 'x'})
        assert w.tabApprovedICs.icsData == [old] and globalData.ics[7] is old

    def test_issuing_sees_a_new_ic_land_in_under_review(self, windows, monkeypatch):
        w = windows(UserRoles.ISSUING)
        fresh = ic_in(IC.Status.REQUESTED, id=7)
        patch_get_ic(monkeypatch, 7, fresh)
        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 7, 'action': 'created', 'by': 'user_turbo'})
        assert w.tabUnderReviewICs.icsData == [fresh] and w.tabRequestedICs.icsData == []

    def test_isolator_ignores_work_queued_for_another_execution_department(self, windows, monkeypatch):
        w = windows(UserRoles.ISOLATOR)                        # Prod
        mine = ic_in(IC.Status.PENDING, id=7, execution_department='Prod')
        theirs = ic_in(IC.Status.PENDING, id=8, execution_department='Mech')
        patch_get_ic(monkeypatch, 7, mine)
        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 7, 'action': 'isolate confirmed', 'by': 'issuing'})
        patch_get_ic(monkeypatch, 8, theirs)
        w._onSSEEvent('ic', {'object': 'IC', 'object_id': 8, 'action': 'isolate confirmed', 'by': 'issuing'})
        assert [x.id for x in w.tabPendingICs.icsData] == [7]
        assert set(globalData.ics) == {7, 8}                   # cached (for equipment status), just not queued

    def test_ptw_event_never_fetches_an_ic(self, windows, monkeypatch):
        from network.clientRequests import ClientRequests
        w = windows(UserRoles.USER)
        monkeypatch.setattr(ClientRequests, 'getICById', staticmethod(lambda *a, **k: pytest.fail('IC fetched for a PTW event')))
        monkeypatch.setattr(ClientRequests, 'getPTWById', staticmethod(lambda u, i, callback=None: callback(None, None)))
        w._onSSEEvent('ptw', {'object': 'PTW', 'object_id': 1, 'action': 'updated', 'by': 'x'})


# ---- footer: theme / language / logout ----------------------------------------------------------------------------

def expected_theme_toggle():
    is_dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return 'light' if is_dark else 'dark'


class TestFooterActions:
    def test_theme_change_deferred_saves_the_preference_asynchronously(self, windows, prompts, monkeypatch):
        w = windows(UserRoles.USER)
        prompts.click_label = 'Later'
        log = record_requests(monkeypatch, 'updateTheme')
        emitted = []
        w.on_logout.connect(lambda: emitted.append(1))
        w.toggleTheme()
        user, args, _ = only_call(log, 'updateTheme')
        assert user is w.loggedUser and args == (expected_theme_toggle(),)
        assert w.loggedUser.getTheme() == expected_theme_toggle()
        assert emitted == [] and w._ptwAlarmTimer.isActive()
        (box,) = prompts.shown
        assert box['title'] == 'Switch Theme' and 'requires a full-application restart' in box['text']

    def test_theme_change_cancelled_changes_nothing(self, windows, prompts, monkeypatch):
        w = windows(UserRoles.USER)
        prompts.click_label = 'Cancel Change'
        log = record_requests(monkeypatch, 'updateTheme')
        w.toggleTheme()
        assert log == [] and w.loggedUser.getTheme() is None

    def test_theme_change_with_restart_saves_then_logs_out(self, windows, prompts, monkeypatch, qtbot):
        w = windows(UserRoles.USER)
        prompts.click_label = 'Restart Now'
        log = record_requests(monkeypatch, 'updateTheme')
        with qtbot.waitSignal(w.on_logout, timeout=1000):
            w.toggleTheme()
        user, args, _ = only_call(log, 'updateTheme')
        assert args == (expected_theme_toggle(),)
        assert w._forceClose and not w._ptwAlarmTimer.isActive()

    def test_language_toggles_english_to_arabic_and_saves_it(self, windows, prompts, monkeypatch):
        w = windows(UserRoles.USER)
        assert w.language == 'en'
        prompts.click_label = 'Later'
        log = record_requests(monkeypatch, 'updateLanguage')
        w.chgLanguage()
        user, args, _ = only_call(log, 'updateLanguage')
        assert user is w.loggedUser and args == ('ar',)
        assert w.loggedUser.getLanguage() == 'ar' and w.language == 'ar'
        assert w.btnLanguage.toolTip() == 'Switch to English'
        (box,) = prompts.shown
        assert box['title'] == 'Switch Language' and 'Arabic' in box['text']

    def test_language_toggle_cancelled(self, windows, prompts, monkeypatch):
        w = windows(UserRoles.USER)
        prompts.click_label = 'Cancel Change'
        log = record_requests(monkeypatch, 'updateLanguage')
        w.chgLanguage()
        assert log == [] and w.language == 'en' and w.loggedUser.getLanguage() is None

    def test_language_toggle_flips_back_from_arabic(self, offline_window, prompts, monkeypatch):
        from windows.UserMainWindow import UserMainWindow
        user = make_user()
        user.setLanguage('ar')
        w = offline_window(UserMainWindow, user)
        assert w.language == 'ar'
        prompts.click_label = 'Later'
        log = record_requests(monkeypatch, 'updateLanguage')
        w.chgLanguage()
        _, args, _ = only_call(log, 'updateLanguage')
        assert args == ('en',) and w.language == 'en'

    def test_logout_stops_sse_and_timers_hides_the_tray_and_emits(self, windows, qtbot):
        w = windows(UserRoles.USER)
        stopped = []
        w._sseListener.stop = lambda: stopped.append(1)
        assert w._ptwAlarmTimer.isActive() and w._fabProximityTimer.isActive()
        with qtbot.waitSignal(w.on_logout, timeout=1000):
            w.logout()
        assert stopped == [1]
        assert not w._ptwAlarmTimer.isActive() and not w._fabProximityTimer.isActive()
        assert not w._trayIcon.isVisible()
        assert w._forceClose is True                       # closeEvent bypassed the tray prompt

    def test_guest_cannot_open_settings(self, offline_window, prompts, monkeypatch):
        from windows.GuestMainWindow import GuestMainWindow
        w = offline_window(GuestMainWindow, make_user('guest', UserRoles.GUEST, ''))
        settings = fake_dialog(monkeypatch, 'DialogSettings')
        w.dlgSettings()
        assert settings.instances == []
        assert prompts.warnings == [('Access Denied', 'Guest users cannot access settings.')]

    def test_settings_saved_updates_the_shared_logged_user_in_place(self, windows, prompts, monkeypatch, qtbot):
        w = windows(UserRoles.USER)
        before = w.loggedUser

        class Settings:
            instances = []

            def __init__(self, parent, user):
                Settings.instances.append(user)
                user.setName('Renamed Turbo')
                self.new_theme = before.getTheme()
                self.new_language = before.getLanguage()

            def exec(self):
                return ACCEPTED

        import windows.MainWindow as MW
        monkeypatch.setattr(MW, 'DialogSettings', Settings)
        log = record_requests(monkeypatch, 'updateUser')
        w.dlgSettings()
        user, args, _ = only_call(log, 'updateUser')
        assert user is before and args[0] is Settings.instances[0] and args[0] is not before   # a copy is edited
        assert w.loggedUser is before and before.getName() == 'Renamed Turbo'                  # then merged back in place
        assert prompts.shown == []                                                              # no theme/language prompt
        # the welcome banner re-fetch is answered on the event loop by the offline stub
        qtbot.waitUntil(lambda: 'RENAMED TURBO' in w.btnWelcomeName.text(), timeout=2000)
