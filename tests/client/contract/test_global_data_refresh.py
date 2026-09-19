"""The client's cache refresh against the live server: every fetch it chains, its scoping,
its replace-not-merge semantics, and the asynchronous delivery the windows rely on."""

from datetime import datetime

import pytest

from GlobalData import globalData
from models.PTW import PTW
from models.Isolation import IC
from models.User import User, SecuredUser
from network.clientRequests import ClientRequests as CR
from ptw_factory import ptw_payload

pytestmark = pytest.mark.contract


def ts():
    return datetime.now().strftime(PTW.TIMESTAMP_FORMAT)


@pytest.fixture
def seeded(contract):
    """Two PTWs (Turbo, Mech), one archived Turbo PTW, one IC, one MIWI, one library risk."""
    turbo = contract.login('user_turbo')
    mech = contract.login('user_mech')
    hse = contract.login('hse')
    _, p1 = CR.addPTW(turbo, PTW(ptw_payload(equipment='T-1')))
    _, p2 = CR.addPTW(mech, PTW(ptw_payload(equipment='M-1', department='Mech', requestor='user_mech')))
    _, p3 = CR.addPTW(turbo, PTW(ptw_payload(equipment='T-archived')))
    for who in ('coord', 'issuing', 'hse'):
        u = contract.login(who)
        assert CR.updateApprovalPTW(u, p3, PTW.Approval(action='Approved', username=who, timestamp=ts())) is None
    CR.requestToClsPTW(turbo, p3, 'user_turbo', ts())
    CR.clsResponsePTW(contract.login('issuing'), p3, 'issuing', ts(), accepted=True)
    assert CR.archivePTWs(turbo, [p3]) is None
    _, ic = CR.addIC(turbo, IC(dict(type='Mechanical', execution_department='Prod', location='Phase VII', equipment='P-1',
                                   reason='r', long_term_reason='', items=[])))
    from models.PTW import RiskAssessment, RiskItem
    assert CR.addNewRiskAssessment(hse, RiskAssessment(title='Lib', date='19/09/2026', risks=[RiskItem(hazard='h', effect='e', free_analysis='f', ctrl='c', ctrl_analysis='a', eval='v')])) is None
    return dict(turbo=turbo, mech=mech, p1=p1, p2=p2, p3=p3, ic=ic)


def test_refresh_all_scoped_to_a_department(seeded):
    err = globalData.refresh(seeded['turbo'], 'Turbo', refreshAll=True)
    assert err is None
    assert set(globalData.allPTWs) == {seeded['p1']}                          # Mech's permit is out of scope
    assert isinstance(globalData.allPTWs[seeded['p1']], PTW)
    assert set(globalData.archivedPTWs) == {seeded['p3']}
    assert globalData.archivedPTWs[seeded['p3']].running_status == PTW.RunningStatus.CLOSED
    assert set(globalData.ics) == {seeded['ic']} and isinstance(globalData.ics[seeded['ic']], IC)
    assert isinstance(globalData.allUsers['coord'], SecuredUser)
    assert set(globalData.allRiskAssessments) == {'Lib'}
    assert globalData.allMIWIs == []


def test_unscoped_refresh_for_an_approver(seeded, contract):
    coord = contract.login('coord')
    assert globalData.refresh(coord, None, refreshPTWs=True, refreshICs=True) is None
    assert set(globalData.allPTWs) == {seeded['p1'], seeded['p2']}
    assert globalData.allUsers == {}                                          # only the requested pieces are touched
    assert globalData.archivedPTWs == {}


def test_refresh_replaces_rather_than_merges(seeded):
    globalData.allPTWs[999] = PTW(ptw_payload(id=999))
    assert globalData.refresh(seeded['turbo'], 'Turbo', refreshPTWs=True) is None
    assert 999 not in globalData.allPTWs


def test_first_failing_fetch_stops_the_chain_and_reports_it(seeded):
    bad = User(username='coord', password='wrong')
    err = globalData.refresh(bad, None, refreshAll=True)
    assert err and 'Failed to fetch users' in err
    assert globalData.allPTWs == {} and globalData.allUsers == {}            # nothing was replaced


def test_asynchronous_delivery_on_the_gui_thread(seeded, qtbot):
    from PyQt6.QtCore import QThread, QCoreApplication
    results = []

    def on_done(err, _):
        results.append((err, QThread.currentThread() is QCoreApplication.instance().thread()))

    assert globalData.refresh(seeded['turbo'], 'Turbo', refreshPTWs=True, callback=on_done) is None   # returns immediately
    qtbot.waitUntil(lambda: bool(results), timeout=10000)
    assert results == [(None, True)]
    assert set(globalData.allPTWs) == {seeded['p1']}


def test_single_record_patching(seeded):
    globalData.refresh(seeded['turbo'], 'Turbo', refreshPTWs=True, refreshICs=True)
    err, fresh = CR.getPTWById(seeded['turbo'], seeded['p1'])
    fresh.setEquipment('patched')
    globalData.upsertPTW(fresh)
    assert globalData.allPTWs[seeded['p1']].equipment == 'patched'
    globalData.removePTW(seeded['p1'])
    globalData.removePTW(seeded['p1'])                                        # idempotent
    assert globalData.allPTWs == {}
    err, ic = CR.getICById(seeded['turbo'], seeded['ic'])
    globalData.upsertIC(ic)
    globalData.removeIC(seeded['ic'])
    globalData.removeIC(12345)
    assert globalData.ics == {}
