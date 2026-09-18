"""Which tab a PTW lands in for a given viewer, driven through the real refresh path.

globalData is pre-populated, the window is built (its constructor runs refreshGUI, whose
server call is stubbed), and each tab's rows are inspected.
"""

from datetime import datetime, timedelta

import pytest

from GlobalData import globalData
from models.PTW import PTW
from models.User import UserRoles, UserDepartments
from conftest import make_user
from ptw_factory import ptw_payload, approval, full_chain, running_cycle, gas_test, COORD, ISSUING, HSE, EX_DEPARTMENTS

pytestmark = pytest.mark.gui

T0 = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
OK = 'Approved'
NO = 'Rejected'


def put(pid, type='Cold', **over):
    over.setdefault('id', pid)
    over.setdefault('department', 'Mech')
    over.setdefault('requestor', 'user_mech')
    ptw = PTW(ptw_payload(type, **over))
    globalData.allPTWs[pid] = ptw
    return ptw


def ids(tab):
    return sorted(p.id for p in tab.ptwsData)


def approved(**over):
    return dict(approvals=full_chain('Cold', start=T0 - timedelta(days=1)), **over)


@pytest.fixture
def populated():
    put(1)                                                                       # under review, not my turn -> Requested
    put(2, approvals=[approval(*COORD)])                                          # Issuing stage -> Requested + in Meeting
    put(3, approvals=[approval(*COORD)], fast_track=True)                         # fast track: never in Meeting
    put(4, approvals=[approval(*COORD, action='Returned')])                       # Returned
    put(5, **approved())                                                          # Approved, idle
    put(6, **approved(run_cycles=[dict(run_pa='u', run_pa_timestamp='x')]))       # Waiting run confirm
    put(7, **approved(run_cycles=[running_cycle(T0)]))                            # Running
    hold = running_cycle(T0); hold.update(stop_pa='u', stop_pa_request='Hold')
    put(8, **approved(run_cycles=[hold]))                                         # Waiting hold confirm
    held = dict(hold, stop_ia='i', stop_ia_action=OK)
    put(9, **approved(run_cycles=[held]))                                         # Held
    close = running_cycle(T0); close.update(stop_pa='u', stop_pa_request='Close')
    put(10, **approved(run_cycles=[close]))                                       # Waiting close confirm
    closed = dict(close, stop_ia='i', stop_ia_action=OK, stop_ia_timestamp='x')
    put(11, **approved(run_cycles=[closed]))                                      # Closed
    # Excavation from another department where *Mech* is a pending approver -> Under Review for a Mech user
    put(12, 'Excavation', department='Turbo', requestor='user_turbo', approvals=[approval(*COORD)])
    # Spark permit that still needs this shift's gas test -> also in the Gas Test overlay
    put(13, 'Spark', hazards=['Electrical / Mechanical Spark'], controls=['Initial Gas Test', 'Continuous Gas Test'],
        approvals=full_chain('Spark', start=datetime.now() - timedelta(hours=2)))
    put(14, 'Spark', hazards=['Electrical / Mechanical Spark'], controls=['Initial Gas Test', 'Continuous Gas Test'],
        approvals=full_chain('Spark', start=datetime.now() - timedelta(hours=2)), gas_tests=[gas_test(PTW.gasTestTargetShift())])


def test_user_window_routing(populated, offline_window):
    from windows.UserMainWindow import UserMainWindow
    w = offline_window(UserMainWindow, make_user('user_mech', UserRoles.USER, UserDepartments.MECH))
    assert ids(w.tabRequestedPTWs) == [1, 2, 3]
    assert ids(w.tabUnderReviewPTWs) == [12]
    assert ids(w.tabMeetingPTWs) == [2]
    assert ids(w.tabReturnedPTWs) == [4]
    assert ids(w.tabApprovedPTWs) == [5, 13, 14]
    assert ids(w.tabWaitingRunConfirmationPTWs) == [6]
    assert ids(w.tabRunningPTWs) == [7]
    assert ids(w.tabWaitingHldConfirmationPTWs) == [8]
    assert ids(w.tabHeldPTWs) == [9]
    assert ids(w.tabWaitingClsConfirmationPTWs) == [10]
    assert ids(w.tabClosedPTWs) == [11]
    assert ids(w.tabGasTestPTWs) == [13]
    # every PTW sits in exactly one exclusive tab
    exclusive = [t for t in w._allPTWTabs() if t not in (w.tabMeetingPTWs, w.tabGasTestPTWs)]
    assert sorted(p for t in exclusive for p in ids(t)) == list(range(1, 15))


def test_coordinator_sees_fresh_ptws_as_under_review(populated, offline_window):
    from windows.CoordinatorMainWindow import CoordinatorMainWindow
    w = offline_window(CoordinatorMainWindow, make_user('coord', UserRoles.COORDINATOR, UserDepartments.PROD))
    assert ids(w.tabUnderReviewPTWs) == [1]              # only where it's Coordinator's turn
    assert ids(w.tabRequestedPTWs) == [2, 3, 12]         # already approved by Coordinator, waiting on others
    assert ids(w.tabMeetingPTWs) == [2]


def test_issuing_sees_its_turn_and_the_waiting_queues(populated, offline_window):
    from windows.IssuingMainWindow import IssuingMainWindow
    w = offline_window(IssuingMainWindow, make_user('issuing', UserRoles.ISSUING, UserDepartments.PROD))
    assert ids(w.tabUnderReviewPTWs) == [2, 3]
    assert ids(w.tabWaitingRunConfirmationPTWs) == [6]
    assert ids(w.tabWaitingHldConfirmationPTWs) == [8]
    assert ids(w.tabWaitingClsConfirmationPTWs) == [10]


def test_gas_tester_sees_only_permits_needing_a_reading(populated, offline_window):
    from windows.GasTesterMainWindow import GasTesterMainWindow
    w = offline_window(GasTesterMainWindow, make_user('gas', UserRoles.GAS_TESTER, UserDepartments.PROD))
    assert ids(w.tabGasTestPTWs) == [13]


def test_sse_event_repaints_a_single_ptw(populated, offline_window, monkeypatch):
    """A 'PTW run accepted' event re-fetches that one PTW and moves it between tabs."""
    from windows.UserMainWindow import UserMainWindow
    from network.clientRequests import ClientRequests
    w = offline_window(UserMainWindow, make_user('user_mech', UserRoles.USER, UserDepartments.MECH))
    assert ids(w.tabWaitingRunConfirmationPTWs) == [6]
    now_running = PTW(ptw_payload(id=6, department='Mech', requestor='user_mech', **approved(run_cycles=[running_cycle(T0)])))

    def fake_get(loggedUser, ptwId, callback=None):
        assert ptwId == 6
        callback(None, now_running)

    monkeypatch.setattr(ClientRequests, 'getPTWById', staticmethod(fake_get))
    w._onSSEEvent('ptw', {'object': 'PTW', 'object_id': 6, 'action': 'run accepted', 'by': 'issuing'})
    assert ids(w.tabWaitingRunConfirmationPTWs) == []
    assert ids(w.tabRunningPTWs) == [6, 7]
    assert globalData.allPTWs[6] is now_running

    w._onSSEEvent('ptw', {'object': 'PTW', 'object_id': 11, 'action': 'archived', 'by': 'system'})
    assert ids(w.tabClosedPTWs) == [] and 11 not in globalData.allPTWs


def test_empty_cache_builds_empty_tabs(offline_window):
    from windows.UserMainWindow import UserMainWindow
    w = offline_window(UserMainWindow, make_user())
    assert all(ids(t) == [] for t in w._allPTWTabs())
