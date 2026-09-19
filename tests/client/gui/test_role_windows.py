"""Per-role tab reachability: which tabs each role window exposes, and that every exposed
nav button really switches the stack to its tab. Built headless with the network stubbed.

EXPECTED_TABS is a snapshot of the current role -> tab layout. When a role's tabs change on
purpose, update the snapshot here in the same commit - that's the point of the test.
"""

import pytest

from GlobalData import globalData
from models.User import UserRoles, UserDepartments
from conftest import make_user

pytestmark = pytest.mark.gui


def _window_classes():
    from windows.UserMainWindow import UserMainWindow
    from windows.GuestMainWindow import GuestMainWindow
    from windows.CoordinatorMainWindow import CoordinatorMainWindow
    from windows.IssuingMainWindow import IssuingMainWindow
    from windows.HSEMainWindow import HSEMainWindow
    from windows.GasTesterMainWindow import GasTesterMainWindow
    from windows.ManagerMainWindow import ManagerMainWindow
    from windows.AdminMainWindow import AdminMainWindow
    from windows.IsolatorMainWindow import IsolatorMainWindow
    return {
        UserRoles.USER: (UserMainWindow, UserDepartments.TURBO),
        UserRoles.GUEST: (GuestMainWindow, ''),
        UserRoles.COORDINATOR: (CoordinatorMainWindow, UserDepartments.PROD),
        UserRoles.ISSUING: (IssuingMainWindow, UserDepartments.PROD),
        UserRoles.HSE_ENGINEER: (HSEMainWindow, UserDepartments.HSE),
        UserRoles.GAS_TESTER: (GasTesterMainWindow, UserDepartments.PROD),
        UserRoles.PGM: (ManagerMainWindow, UserDepartments.PROD, 'PGM'),
        UserRoles.ADMIN: (AdminMainWindow, 'Admin'),
        UserRoles.ISOLATOR: (IsolatorMainWindow, UserDepartments.PROD),
    }


PTW_TABS = {
    'tabRequestedPTWs', 'tabUnderReviewPTWs', 'tabMeetingPTWs', 'tabReturnedPTWs', 'tabApprovedPTWs',
    'tabWaitingRunConfirmationPTWs', 'tabRunningPTWs', 'tabWaitingHldConfirmationPTWs', 'tabHeldPTWs',
    'tabWaitingClsConfirmationPTWs', 'tabClosedPTWs', 'tabArchivedPTWs',
}
IC_TABS = {
    'tabRequestedICs', 'tabUnderReviewICs', 'tabApprovedICs', 'tabIsolateConfirmingICs', 'tabPendingICs',
    'tabActiveICs', 'tabDeisolateConfirmingICs', 'tabClosingICs', 'tabSanctionedICs', 'tabClosedICs',
}
ADMIN_ONLY = {'tabAllUsers', 'tabServerLogs', 'tabBackups'}


def tab_names(window) -> set[str]:
    """Attribute names of the tabs this role can reach."""
    by_widget = {getattr(window, name): name for name in dir(window) if name.startswith('tab') and name != 'tabWelcome'}
    by_widget[window.tabWelcome] = 'tabWelcome'
    return {by_widget[tab] for tab in window._availableTabs}


def build_role_window(offline_window, role, username='tester'):
    cls, dept, *extra = _window_classes()[role]
    return offline_window(cls, make_user(username, role, dept), *extra)


@pytest.fixture(params=list(_window_classes()), ids=lambda r: str(r))
def role_window(request, offline_window):
    role = request.param
    return role, build_role_window(offline_window, role, f'{str(role).lower().replace(" ", "_")}_1')


class TestEveryRole:
    def test_welcome_is_always_reachable_and_is_the_landing_tab(self, role_window):
        role, w = role_window
        assert 'tabWelcome' in tab_names(w)
        assert w.stack.currentWidget() is w.tabWelcome

    def test_every_available_button_switches_to_its_tab(self, role_window):
        role, w = role_window
        for btn in w._availableNavButtons:
            tab = w._sideBarBtnMap.get(btn)
            if tab is None:
                continue        # footer action buttons (refresh/logout/settings/...)
            assert w.stack.indexOf(tab) >= 0, f"{role}: tab not in the stack"
            btn.click()
            assert w.stack.currentWidget() is tab, f"{role}: button did not switch to its tab"

    def test_no_unreachable_tab_leaks_into_the_sidebar(self, role_window):
        role, w = role_window
        for btn, tab in w._sideBarBtnMap.items():
            if tab is not None and tab not in w._availableTabs:
                assert btn not in w._availableNavButtons, f"{role}: {btn.toolTip()!r} shown but its tab isn't available"

    def test_admin_only_tabs(self, role_window):
        role, w = role_window
        present = tab_names(w) & ADMIN_ONLY
        if role == UserRoles.ADMIN:
            assert present == ADMIN_ONLY
        else:
            assert present == set(), f"{role} can reach admin tabs {present}"

    def test_gas_test_tab_belongs_to_gas_tester(self, role_window):
        role, w = role_window
        assert ('tabGasTestPTWs' in tab_names(w)) == (role == UserRoles.GAS_TESTER)

    def test_footer_hides_preferences_for_guests(self, role_window):
        role, w = role_window
        footer = w._footerButtons()
        assert w.btnRefresh in footer and w.btnLogout in footer
        assert (w.btnSettings in footer) == (role != UserRoles.GUEST)
        assert (w.btnTheme in footer) == (role != UserRoles.GUEST)

    def test_refresh_ran_once_on_construction(self, role_window, offline_window):
        # every role window pulls its data exactly once while being built (Admin's own
        # panels add their log/backup fetches on top, hence the filter on the loggedUser arg)
        role, w = role_window
        refreshes = [(a, k) for a, k in offline_window.refresh_calls if len(a) >= 2]   # globalData.refresh(user, dept, ...)
        assert len(refreshes) == 1, offline_window.refresh_calls
        args, kwargs = refreshes[0]
        assert args[0] is w.loggedUser
        expected_scope = w.loggedUser.getDepartment() if role in (UserRoles.USER, UserRoles.GUEST) else None
        assert args[1] == expected_scope


# Snapshot of the reachable tabs per role. Update deliberately when a role's layout changes.
EXPECTED_TABS = {
    UserRoles.USER: {'tabWelcome'} | PTW_TABS | (IC_TABS - {'tabUnderReviewICs'}),
    UserRoles.GUEST: {'tabWelcome', 'tabRequestedPTWs', 'tabReturnedPTWs', 'tabApprovedPTWs'},
    UserRoles.GAS_TESTER: {'tabWelcome', 'tabGasTestPTWs'},
    UserRoles.ADMIN: {'tabWelcome'} | ADMIN_ONLY,
}


@pytest.mark.parametrize("role", list(EXPECTED_TABS), ids=lambda r: str(r))
def test_tab_snapshot(role, offline_window):
    assert tab_names(build_role_window(offline_window, role, 'snap')) == EXPECTED_TABS[role]


class TestRoleSpecificShape:
    def test_issuing_sees_the_waiting_confirmation_queues_and_coordinator_does_not(self, offline_window):
        from windows.IssuingMainWindow import IssuingMainWindow
        from windows.CoordinatorMainWindow import CoordinatorMainWindow
        waiting = {'tabWaitingRunConfirmationPTWs', 'tabWaitingHldConfirmationPTWs', 'tabWaitingClsConfirmationPTWs'}
        issuing = tab_names(offline_window(IssuingMainWindow, make_user('i', UserRoles.ISSUING, UserDepartments.PROD)))
        coord = tab_names(offline_window(CoordinatorMainWindow, make_user('c', UserRoles.COORDINATOR, UserDepartments.PROD)))
        assert waiting <= issuing
        assert not (waiting & coord)
        assert 'tabUnderReviewPTWs' in coord and 'tabEquipmentStatus' in coord

    def test_isolator_gets_the_execution_queues_only(self, offline_window):
        from windows.IsolatorMainWindow import IsolatorMainWindow
        tabs = tab_names(offline_window(IsolatorMainWindow, make_user('iso', UserRoles.ISOLATOR, UserDepartments.PROD)))
        assert {'tabPendingICs', 'tabActiveICs', 'tabClosingICs', 'tabSanctionedICs'} <= tabs
        assert not (tabs & PTW_TABS), "an isolator has no PTW tabs"
        assert 'tabRequestedICs' not in tabs

    def test_hse_has_the_risk_library(self, offline_window):
        from windows.HSEMainWindow import HSEMainWindow
        from windows.UserMainWindow import UserMainWindow
        assert 'tabRisks' in tab_names(offline_window(HSEMainWindow, make_user('h', UserRoles.HSE_ENGINEER, UserDepartments.HSE)))
        assert 'tabRisks' not in tab_names(offline_window(UserMainWindow, make_user()))

    def test_manager_window_serves_every_manager_role(self, offline_window):
        from windows.ManagerMainWindow import ManagerMainWindow
        for role in (UserRoles.PDH, UserRoles.PGM, UserRoles.SOD, UserRoles.DFGM):
            w = offline_window(ManagerMainWindow, make_user('m', role, UserDepartments.PROD), str(role))
            assert str(role) in w.windowTitle()
            assert {'tabUnderReviewPTWs', 'tabApprovedPTWs', 'tabUnderReviewICs'} <= tab_names(w), role

    def test_admin_window_populates_users_and_panels(self, offline_window, known_users):
        from windows.AdminMainWindow import AdminMainWindow
        w = offline_window(AdminMainWindow, make_user('root', UserRoles.ADMIN, 'Admin'))
        shown = {w.tabAllUsers.tbl.item(r, 0).text() for r in range(w.tabAllUsers.tbl.rowCount())}
        assert shown >= set(known_users), shown
        assert w.tabServerLogs._statusLabel.text() == 'No log files found.'
        assert w.tabBackups.tbl.rowCount() == 0

    def test_admin_window_survives_a_refresh_reply_during_construction(self, offline_window, known_users, monkeypatch):
        """Regression: the refresh callback used to call updateHomeDashboard() before
        buildHomePage() had created the Users chart. Deliver the reply synchronously,
        mid-constructor, and the window must still build and populate."""
        from windows.AdminMainWindow import AdminMainWindow

        def immediate_refresh(*args, callback=None, **kwargs):
            if callback is not None:
                callback(None, None)

        monkeypatch.setattr(globalData, 'refresh', immediate_refresh)
        w = offline_window(AdminMainWindow, make_user('root', UserRoles.ADMIN, 'Admin'))
        assert w._homeUsersChart is not None
        assert w.tabAllUsers.tbl.rowCount() >= len(known_users)

    def test_window_titles_name_the_role(self, offline_window):
        from windows.UserMainWindow import UserMainWindow
        from windows.GasTesterMainWindow import GasTesterMainWindow
        assert 'User' in offline_window(UserMainWindow, make_user()).windowTitle()
        gw = offline_window(GasTesterMainWindow, make_user('g', UserRoles.GAS_TESTER, UserDepartments.PROD))
        assert 'Gas Tester' in gw.windowTitle()
        assert gw.btnFAB.isHidden()
