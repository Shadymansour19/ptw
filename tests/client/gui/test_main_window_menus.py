"""Per-role right-click menus on the PTW / IC tabs, and the `visibleFor` predicates that
hide an option for a record in the wrong state.

MENU_SNAPSHOT is the current role -> reachable tab -> registered options (in registration
order - the first one is also the double-click action). It is derived from the
`addOptions(...)` lines of each `client/windows/*MainWindow.py`; when a role's menu changes
on purpose, update the snapshot in the same commit.
"""

from datetime import timedelta

import pytest
from PyQt6.QtWidgets import QMenu

from GlobalData import globalData
from models.PTW import PTW
from models.Isolation import IC
from models.User import UserRoles, UserDepartments
from conftest import make_user
from ptw_factory import make_ptw, approved_ptw, running_cycle, full_chain
from test_role_windows import _window_classes, build_role_window
from tables.TablePTWs import TablePTWs
from tables.TableICs import TableICs
import tables.TablePTWs as TP
import tables.TableICs as TI
from mw_helpers import ic_in, ALL_IC_STATUSES, NOW, record_requests, install_prompts, FakeInputDialog, only_call

pytestmark = pytest.mark.gui

VIEW_PRINT_EXPORT = ['optionViewPTW', 'optionViewRequestorPTW', 'optionPrintPTW', 'optionExportPTW']
IC_VIEW_PRINT = ['optionViewIC', 'optionPrintIC']
IC_VIEW_PRINT_LINK = IC_VIEW_PRINT + ['optionLinkPTWToIC']
REVIEW = ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestEditsPTW', 'optionAcceptPTW', 'optionPrintPTW', 'optionExportPTW']
WATCH_PA = ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionPrintPTW', 'optionExportPTW']
CLOSED = ['optionViewPTW', 'optionViewRequestorPTW', 'optionPrintPTW', 'optionArchivePTW', 'optionExportPTW']
ARCHIVED = ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW']
LINKABLE_APPROVED = ['optionViewPTW', 'optionViewRequestorPTW', 'optionLinkICToPTW', 'optionPrintPTW', 'optionExportPTW']
IC_REVIEW_LINK = ['optionViewIC', 'optionPrintIC', 'optionAcceptIC', 'optionRequestEditsIC', 'optionLinkPTWToIC']

MENU_SNAPSHOT = {
    UserRoles.USER: {
        'tabRequestedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabUnderReviewPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionAcceptPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabMeetingPTWs': VIEW_PRINT_EXPORT,
        'tabReturnedPTWs': ['optionViewPTW', 'optionEditPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionDltPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabApprovedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionRunRequestPTW', 'optionLinkICToPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabWaitingRunConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabRunningPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionRequestPTW', 'optionClsRequestPTW', 'optionHldRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabWaitingClsConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabWaitingHldConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'viewHeldICsOption', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabHeldPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'viewHeldICsOption', 'optionRequestPTW', 'optionRunRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabClosedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionArchivePTW', 'optionExportPTW'],
        'tabArchivedPTWs': ARCHIVED,
        'tabRequestedICs': IC_VIEW_PRINT_LINK,
        'tabApprovedICs': ['optionViewIC', 'optionPrintIC', 'optionRequestIsolateIC', 'optionLinkPTWToIC'],
        'tabIsolateConfirmingICs': IC_VIEW_PRINT_LINK,
        'tabPendingICs': IC_VIEW_PRINT_LINK,
        'tabActiveICs': ['optionViewIC', 'optionPrintIC', 'optionRequestDeisolateIC', 'optionLinkPTWToIC'],
        'tabDeisolateConfirmingICs': IC_VIEW_PRINT,
        'tabClosingICs': IC_VIEW_PRINT,
        'tabSanctionedICs': IC_VIEW_PRINT,
        'tabClosedICs': IC_VIEW_PRINT,
    },
    UserRoles.GUEST: {
        'tabRequestedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabReturnedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabApprovedPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestPTW', 'optionPrintPTW', 'optionExportPTW'],
    },
    UserRoles.COORDINATOR: {
        'tabUnderReviewPTWs': REVIEW,
        'tabMeetingPTWs': VIEW_PRINT_EXPORT,
        'tabReturnedPTWs': VIEW_PRINT_EXPORT,
        'tabApprovedPTWs': LINKABLE_APPROVED,
        'tabRunningPTWs': WATCH_PA,
        'tabHeldPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'viewHeldICsOption', 'optionPrintPTW', 'optionExportPTW'],
        'tabClosedPTWs': CLOSED,
        'tabArchivedPTWs': ARCHIVED,
        'tabUnderReviewICs': IC_REVIEW_LINK,
        'tabApprovedICs': IC_VIEW_PRINT_LINK,
        'tabIsolateConfirmingICs': IC_VIEW_PRINT_LINK,
        'tabPendingICs': IC_VIEW_PRINT_LINK,
        'tabActiveICs': IC_VIEW_PRINT_LINK,
        'tabDeisolateConfirmingICs': IC_VIEW_PRINT,
        'tabClosingICs': IC_VIEW_PRINT,
        'tabSanctionedICs': IC_VIEW_PRINT,
        'tabClosedICs': IC_VIEW_PRINT,
    },
    UserRoles.ISSUING: {
        'tabUnderReviewPTWs': REVIEW,
        'tabMeetingPTWs': REVIEW,
        'tabReturnedPTWs': VIEW_PRINT_EXPORT,
        'tabApprovedPTWs': LINKABLE_APPROVED,
        'tabWaitingRunConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionRunAcceptPTW', 'optionRunRejectPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabRunningPTWs': WATCH_PA,
        'tabWaitingHldConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'viewHeldICsOption', 'optionHldTakeActionPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabHeldPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'viewHeldICsOption', 'optionPrintPTW', 'optionExportPTW'],
        'tabWaitingClsConfirmationPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionClsAcceptPTW', 'optionClsRejectPTW', 'optionPrintPTW', 'optionExportPTW'],
        'tabClosedPTWs': CLOSED,
        'tabArchivedPTWs': ARCHIVED,
        'tabUnderReviewICs': IC_REVIEW_LINK,
        'tabApprovedICs': IC_VIEW_PRINT_LINK,
        'tabIsolateConfirmingICs': ['optionViewIC', 'optionPrintIC', 'optionConfirmIsolateIC', 'optionReturnIsolateIC', 'optionLinkPTWToIC'],
        'tabPendingICs': IC_VIEW_PRINT_LINK,
        'tabActiveICs': IC_VIEW_PRINT_LINK,
        'tabDeisolateConfirmingICs': ['optionViewIC', 'optionPrintIC', 'optionConfirmDeisolateIC', 'optionReturnDeisolateIC'],
        'tabClosingICs': IC_VIEW_PRINT,
        'tabSanctionedICs': IC_VIEW_PRINT,
        'tabClosedICs': IC_VIEW_PRINT,
    },
    UserRoles.HSE_ENGINEER: {
        'tabUnderReviewPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestEditsPTW', 'optionAcceptPTW'],
        'tabMeetingPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRequestEditsPTW', 'optionAcceptPTW'],
        'tabRunningPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionViewPerformingPTW', 'optionPrintPTW'],
    },
    UserRoles.GAS_TESTER: {
        'tabGasTestPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'optionRecordGasTestPTW'],
    },
    UserRoles.PGM: {
        'tabUnderReviewPTWs': REVIEW,
        'tabReturnedPTWs': VIEW_PRINT_EXPORT,
        'tabApprovedPTWs': VIEW_PRINT_EXPORT,
        'tabRunningPTWs': WATCH_PA,
        'tabHeldPTWs': ['optionViewPTW', 'optionViewRequestorPTW', 'viewHeldICsOption', 'optionPrintPTW', 'optionExportPTW'],
        'tabClosedPTWs': CLOSED,
        'tabUnderReviewICs': ['optionViewIC', 'optionPrintIC', 'optionAcceptIC', 'optionRequestEditsIC'],
    },
    UserRoles.ISOLATOR: {
        'tabPendingICs': ['optionViewIC', 'optionPrintIC', 'optionExecuteIsolateIC'],
        'tabActiveICs': IC_VIEW_PRINT,
        'tabClosingICs': ['optionViewIC', 'optionPrintIC', 'optionExecuteDeisolateIC'],
        'tabSanctionedICs': IC_VIEW_PRINT,
    },
    UserRoles.ADMIN: {},
}


def option_names(window) -> dict:
    """id(MenuOption) -> the attribute name it is stored under on the window."""
    return {
        id(getattr(window, n)): n for n in dir(window)
        if (n.startswith('option') or n.endswith('Option')) and isinstance(getattr(window, n), TablePTWs.MenuOption)
    }


def reachable_menus(window) -> dict:
    """tab attribute name -> option attribute names, for every reachable PTW/IC table tab."""
    names = option_names(window)
    by_widget = {getattr(window, n): n for n in dir(window) if n.startswith('tab')}
    return {
        by_widget[tab]: [names[id(o)] for o in tab.options]
        for tab in window._availableTabs if isinstance(tab, (TablePTWs, TableICs))
    }


@pytest.fixture(params=list(_window_classes()), ids=lambda r: str(r))
def role_window(request, offline_window):
    role = request.param
    return role, build_role_window(offline_window, role, 'menu_' + str(role).lower().replace(' ', '_'))


class TestMenuSnapshot:
    def test_reachable_tab_menus_match_snapshot(self, role_window):
        role, w = role_window
        assert reachable_menus(w) == MENU_SNAPSHOT[role]

    def test_every_reachable_table_tab_double_clicks_into_view(self, role_window):
        # options[0] is what TablePTWs/TableICs.doubleClickHandler runs
        role, w = role_window
        for tab_name, options in reachable_menus(w).items():
            assert options and options[0] in ('optionViewPTW', 'optionViewIC'), (role, tab_name, options)

    def test_menu_labels_are_the_translated_option_texts(self, role_window):
        role, w = role_window
        labels = {n: getattr(w, n).lbl for n in option_names(w).values()}
        assert labels['optionRunRequestPTW'] == labels['optionRunAcceptPTW'] == 'Run'
        assert labels['optionRecordGasTestPTW'] == 'Record Gas Test'
        assert labels['optionHldTakeActionPTW'] == 'Take Action'
        assert labels['optionLinkICToPTW'] == 'Link to IC' and labels['optionLinkPTWToIC'] == 'Link to PTW'
        assert labels['optionExecuteIsolateIC'] == 'Complete Isolation'


class TestRoleContrasts:
    """The role-to-role differences the menus exist for, stated directly."""

    def test_only_issuing_answers_run_hold_close_requests(self):
        answering = {'optionRunAcceptPTW', 'optionRunRejectPTW', 'optionHldTakeActionPTW', 'optionClsAcceptPTW', 'optionClsRejectPTW'}
        for role, tabs in MENU_SNAPSHOT.items():
            registered = {o for opts in tabs.values() for o in opts}
            assert (registered & answering) == (answering if role == UserRoles.ISSUING else set()), role

    def test_only_user_requests_run_hold_close(self):
        requesting = {'optionRunRequestPTW', 'optionHldRequestPTW', 'optionClsRequestPTW'}
        for role, tabs in MENU_SNAPSHOT.items():
            registered = {o for opts in tabs.values() for o in opts}
            assert (registered & requesting) == (requesting if role == UserRoles.USER else set()), role

    def test_gas_test_recording_is_gas_tester_only(self):
        for role, tabs in MENU_SNAPSHOT.items():
            has = any('optionRecordGasTestPTW' in opts for opts in tabs.values())
            assert has == (role == UserRoles.GAS_TESTER), role

    def test_only_isolator_executes_isolation(self):
        executing = {'optionExecuteIsolateIC', 'optionExecuteDeisolateIC'}
        for role, tabs in MENU_SNAPSHOT.items():
            registered = {o for opts in tabs.values() for o in opts}
            assert (registered & executing) == (executing if role == UserRoles.ISOLATOR else set()), role

    def test_only_issuing_confirms_or_returns_isolation_requests(self):
        confirming = {'optionConfirmIsolateIC', 'optionReturnIsolateIC', 'optionConfirmDeisolateIC', 'optionReturnDeisolateIC'}
        for role, tabs in MENU_SNAPSHOT.items():
            registered = {o for opts in tabs.values() for o in opts}
            assert (registered & confirming) == (confirming if role == UserRoles.ISSUING else set()), role

    def test_approvers_can_request_edits_but_a_user_cannot(self):
        # a User's Under Review tab is only for the Excavation department sign-off: Accept, no Request Edits
        for role in (UserRoles.COORDINATOR, UserRoles.ISSUING, UserRoles.HSE_ENGINEER, UserRoles.PGM):
            assert 'optionRequestEditsPTW' in MENU_SNAPSHOT[role]['tabUnderReviewPTWs'], role
        assert 'optionRequestEditsPTW' not in MENU_SNAPSHOT[UserRoles.USER]['tabUnderReviewPTWs']
        assert 'optionAcceptPTW' in MENU_SNAPSHOT[UserRoles.USER]['tabUnderReviewPTWs']

    def test_guest_never_gets_a_mutating_option(self):
        mutating = {'optionEditPTW', 'optionDltPTW', 'optionArchivePTW', 'optionAcceptPTW', 'optionRequestEditsPTW',
                    'optionRunRequestPTW', 'optionHldRequestPTW', 'optionClsRequestPTW', 'optionLinkICToPTW'}
        registered = {o for opts in MENU_SNAPSHOT[UserRoles.GUEST].values() for o in opts}
        assert not (registered & mutating)


# ---- visibleFor predicates ---------------------------------------------------------------------

@pytest.fixture
def user_window(offline_window):
    from windows.UserMainWindow import UserMainWindow
    return offline_window(UserMainWindow, make_user())


IC_STATUS_OPTION = {
    'optionConfirmIsolateIC': IC.Status.ISOLATE_CONFIRMING,
    'optionReturnIsolateIC': IC.Status.ISOLATE_CONFIRMING,
    'optionExecuteIsolateIC': IC.Status.PENDING,
    'optionRequestDeisolateIC': IC.Status.ACTIVE,
    'optionConfirmDeisolateIC': IC.Status.DEISOLATE_CONFIRMING,
    'optionReturnDeisolateIC': IC.Status.DEISOLATE_CONFIRMING,
    'optionExecuteDeisolateIC': IC.Status.CLOSING,
}


class TestVisibleFor:
    @pytest.mark.parametrize('option, wanted', list(IC_STATUS_OPTION.items()))
    def test_ic_lifecycle_options_show_for_exactly_one_status(self, user_window, option, wanted):
        predicate = getattr(user_window, option).visibleFor
        visible = {status for status in ALL_IC_STATUSES if predicate(ic_in(status))}
        assert visible == {wanted}

    def test_link_to_ptw_hidden_once_the_ic_is_winding_down(self, user_window):
        predicate = user_window.optionLinkPTWToIC.visibleFor
        hidden = {status for status in ALL_IC_STATUSES if not predicate(ic_in(status))}
        assert hidden == {IC.Status.SANCTIONED, IC.Status.DEISOLATE_CONFIRMING, IC.Status.CLOSING, IC.Status.CLOSED}

    def test_link_to_ic_only_for_an_approved_not_yet_running_ptw(self, user_window):
        predicate = user_window.optionLinkICToPTW.visibleFor
        assert predicate(approved_ptw(approved_at=NOW))
        assert not predicate(make_ptw())                                                                # under review
        assert not predicate(approved_ptw(approved_at=NOW, run_cycles=[dict(run_pa='u', run_pa_timestamp='x')]))   # run requested
        assert not predicate(approved_ptw(approved_at=NOW, run_cycles=[running_cycle(NOW)]))            # running
        held = running_cycle(NOW); held.update(stop_pa='u', stop_pa_request='Hold', stop_ia='i', stop_ia_action='Approved')
        assert not predicate(approved_ptw(approved_at=NOW, run_cycles=[held]))                          # held

    def test_options_without_a_predicate_are_always_offered(self, user_window):
        for name in ('optionViewPTW', 'optionRunRequestPTW', 'optionHldRequestPTW', 'optionAcceptIC', 'optionRequestIsolateIC'):
            assert getattr(user_window, name).visibleFor is None, name


# ---- the table machinery the menu runs through ------------------------------------------------

class RecordingMenu(QMenu):
    """QMenu whose exec() never blocks; remembers the last built menu."""
    last = None

    def exec(self, *args, **kwargs):
        RecordingMenu.last = self
        return None


@pytest.fixture
def silent_menus(monkeypatch):
    RecordingMenu.last = None
    monkeypatch.setattr(TP, 'QMenu', RecordingMenu)
    monkeypatch.setattr(TI, 'QMenu', RecordingMenu)


def cell_pos(tab, row):
    return tab.tbl.visualRect(tab.tbl.model().index(row, 0)).center()


def menu_texts():
    return [a.text() for a in RecordingMenu.last.actions()]


class TestContextMenuMachinery:
    def test_menu_lists_every_option_that_passes_its_predicate(self, user_window, silent_menus):
        tab = user_window.tabApprovedPTWs
        tab.addPTWToGUI(approved_ptw(approved_at=NOW, id=1))
        tab.showContextMenu(cell_pos(tab, 0))
        assert menu_texts() == ['View', 'View Requestor', 'Re-Request PTW', 'Run', 'Link to IC', 'Print', 'Export']

    def test_menu_drops_state_gated_options_for_a_record_in_the_wrong_state(self, user_window, silent_menus):
        # the tab normally only ever holds ACTIVE ICs, so put a CLOSED one in it directly
        tab = user_window.tabActiveICs
        tab.addICToGUI(ic_in(IC.Status.ACTIVE, id=1))
        tab.addICToGUI(ic_in(IC.Status.CLOSED, id=2))
        tab.showContextMenu(cell_pos(tab, 0))
        assert menu_texts() == ['View', 'Print', 'Request De-isolate', 'Link to PTW']
        tab.showContextMenu(cell_pos(tab, 1))
        assert menu_texts() == ['View', 'Print']

    def test_right_click_outside_any_row_builds_no_menu(self, user_window, silent_menus):
        from PyQt6.QtCore import QPoint
        user_window.tabApprovedPTWs.showContextMenu(QPoint(5, 5))
        assert RecordingMenu.last is None

    def test_do_for_all_selected_filters_the_selection_by_the_predicate(self, user_window):
        tab = user_window.tabActiveICs
        for i, status in enumerate((IC.Status.ACTIVE, IC.Status.CLOSED, IC.Status.ACTIVE), start=1):
            tab.addICToGUI(ic_in(status, id=i))
        tab.tbl.selectAll()
        seen = []
        tab.optionDoForAllSelected(lambda row, ic: seen.append((row, ic.id)), False, user_window.optionRequestDeisolateIC.visibleFor)
        assert seen == [(2, 3), (0, 1)]        # reverse row order, the CLOSED row skipped

    def test_do_for_all_selected_batches_when_all_at_once(self, user_window):
        tab = user_window.tabClosedPTWs
        for i in (1, 2, 3):
            tab.addPTWToGUI(approved_ptw(approved_at=NOW, id=i))
        tab.tbl.selectAll()
        seen = []
        tab.optionDoForAllSelected(lambda rows, ptws: seen.append((rows, [p.id for p in ptws])), True)
        assert seen == [([0, 1, 2], [1, 2, 3])]

    def test_triggering_a_menu_action_runs_the_handler_for_the_selected_row(self, offline_window, silent_menus, monkeypatch):
        """End to end through the real menu: Issuing right-clicks a PTW waiting for run
        confirmation, picks Run, confirms - runResponsePTW goes out for that PTW."""
        from windows.IssuingMainWindow import IssuingMainWindow
        globalData.allPTWs[6] = approved_ptw(approved_at=NOW, id=6, run_cycles=[dict(run_pa='user_turbo', run_pa_timestamp='x')])
        w = offline_window(IssuingMainWindow, make_user('issuing', UserRoles.ISSUING, UserDepartments.PROD))
        install_prompts(monkeypatch)
        FakeInputDialog.answer('go ahead')
        log = record_requests(monkeypatch, 'runResponsePTW')

        tab = w.tabWaitingRunConfirmationPTWs
        assert [p.id for p in tab.ptwsData] == [6]
        tab.tbl.selectRow(0)
        tab.showContextMenu(cell_pos(tab, 0))
        run = [a for a in RecordingMenu.last.actions() if a.text() == 'Run']
        assert len(run) == 1
        run[0].trigger()

        user, args, kwargs = only_call(log, 'runResponsePTW')
        assert user is w.loggedUser
        assert args[0] == 6 and args[1] == 'issuing' and args[3] is True and args[4] == 'go ahead'
