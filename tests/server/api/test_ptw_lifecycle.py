"""End-to-end permit lifecycle through HTTP: create -> approve -> run -> hold -> resume -> close -> archive.

After every mutation both the in-memory cache and the database row are checked, since the
routes serve from the cache and write to the DB.
"""

from datetime import datetime, timedelta

import pytest

from models.PTW import PTW
from conftest import auth, GUEST
from api_helpers import (
    create_ptw, approve, approve_fully, run_request, run_response, hold_request, hold_response,
    close_request, close_response, gas_test, get_ptw, list_ptws, RETURN, now_ts,
)
from ptw_factory import ptw_payload

A = PTW.ApprovalStatus
R = PTW.RunningStatus
SPARK = 'Electrical / Mechanical Spark'
GAS_CONTROLS = ['Initial Gas Test', 'Continuous Gas Test']


def status(server, ptw_id):
    """(approval_status, running_status) from the cache AND from a fresh DB read; they must agree."""
    cached = server.globalData.allPTWs[ptw_id]
    stored = server.ptwDB.getPTWById(ptw_id)
    assert (cached.approval_status, cached.running_status) == (stored.approval_status, stored.running_status)
    return str(cached.approval_status), str(cached.running_status)


class TestCreate:
    def test_create_returns_id_and_persists(self, client, server):
        pid = create_ptw(client)
        assert pid == 1
        assert status(server, pid) == (A.UNDER_REVIEW, R.NOT_RUNNING)
        row = server.ptwDB.getPTWById(pid)
        assert row.equipment == 'P-101' and row.requestor == 'user_turbo'
        assert get_ptw(client, pid)['description'] == 'Replace pump gasket'

    def test_invalid_payload_is_rejected_with_the_validation_message(self, client, server):
        r = client.post('/ptws', json=ptw_payload(equipment=''), headers=auth('user_turbo'))
        assert r.status_code == 400
        assert r.get_json()['error'] == 'Equipment cannot be empty'
        r = client.post('/ptws', json=ptw_payload(PTW.Types.SP), headers=auth('user_turbo'))
        assert r.status_code == 400 and 'required for Spark permits' in r.get_json()['error']
        assert server.globalData.allPTWs == {}

    def test_status_fields_in_payload_are_ignored(self, client, server):
        pid = create_ptw(client, approval_status='Approved', running_status='Running')
        assert status(server, pid) == (A.UNDER_REVIEW, R.NOT_RUNNING)

    def test_guest_can_create(self, client, server):
        r = client.post('/ptws', json=ptw_payload(requestor=GUEST, department='Visitors'), headers=auth(GUEST, ''))
        assert r.status_code == 200


class TestApprovalCycle:
    def test_stage_order_is_enforced(self, client, server):
        pid = create_ptw(client)
        r = approve(client, pid, 'issuing')
        assert r.status_code == 403 and 'not an eligible approver' in r.get_json()['error']
        assert approve(client, pid, 'user_turbo').status_code == 403      # requestor's own department can't approve
        assert approve(client, pid, 'coord').status_code == 200
        assert approve(client, pid, 'coord').status_code == 403           # can't approve twice
        assert status(server, pid) == (A.UNDER_REVIEW, R.NOT_RUNNING)
        assert approve(client, pid, 'issuing').status_code == 200
        assert approve(client, pid, 'pgm').status_code == 403             # not part of a Cold Work chain
        assert approve(client, pid, 'hse').status_code == 200
        assert status(server, pid) == (A.APPROVED, R.NOT_RUNNING)

    def test_role_and_department_are_snapshotted_from_the_verified_user_not_the_payload(self, client, server):
        pid = create_ptw(client)
        r = client.post('/ptws/approvals', json={'ptw-id': pid, 'approval': {
            'action': 'Approved', 'username': 'coord', 'timestamp': now_ts(), 'role': 'DFGM', 'department': 'IT'}},
            headers=auth('coord'))
        assert r.status_code == 200
        rec = server.ptwDB.getPTWById(pid).approvals[0]
        assert (rec.role, rec.department) == ('Coordinator', 'Prod')

    @pytest.mark.parametrize("type", [PTW.Types.HT, PTW.Types.CS, PTW.Types.EX])
    def test_long_chains(self, client, server, type):
        over = {'hazards': [SPARK], 'controls': GAS_CONTROLS} if type == PTW.Types.SP else {}
        pid = create_ptw(client, type=type, **over)
        approve_fully(client, pid, type)
        assert status(server, pid) == (A.APPROVED, R.NOT_RUNNING)

    def test_return_edit_resubmit(self, client, server):
        pid = create_ptw(client)
        assert approve(client, pid, 'coord', action=RETURN, comment='wrong equipment').status_code == 200
        assert status(server, pid) == (A.RETURNED, R.NOT_RUNNING)
        assert approve(client, pid, 'issuing').status_code == 403
        # only the owning department may edit, and only while RETURNED
        edited = dict(get_ptw(client, pid), equipment='P-102')
        assert client.put('/ptws', json=edited, headers=auth('user_mech')).status_code == 403
        r = client.put('/ptws', json=edited, headers=auth('user_turbo'))
        assert r.status_code == 200, r.get_json()
        assert server.ptwDB.getPTWById(pid).equipment == 'P-102'
        # resubmitting keeps the audit trail, so the client re-requests as a *new* PTW; the old one is deletable
        assert client.delete('/ptws', json={'ptw-id': pid}, headers=auth('user_turbo')).status_code == 200
        assert pid not in server.globalData.allPTWs and server.ptwDB.getPTWById(pid) is None

    def test_cannot_delete_or_edit_a_live_ptw(self, client, server):
        pid = create_ptw(client)
        assert client.delete('/ptws', json={'ptw-id': pid}, headers=auth('user_turbo')).status_code == 403
        assert client.put('/ptws', json=get_ptw(client, pid), headers=auth('user_turbo')).status_code == 403
        assert client.put('/ptws', json={'id': 'abc'}, headers=auth('user_turbo')).status_code == 400
        assert client.put('/ptws', json={'id': 999}, headers=auth('user_turbo')).status_code == 404

    def test_unknown_ptw(self, client):
        assert approve(client, 999, 'coord').status_code == 404
        assert run_request(client, 999).status_code == 400


class TestRunningCycle:
    @pytest.fixture
    def approved(self, client):
        pid = create_ptw(client)
        approve_fully(client, pid)
        return pid

    def test_full_run_hold_resume_close_archive(self, client, server, approved):
        pid = approved
        assert run_request(client, pid).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.WAITING_RUN_CONFIRM)
        assert run_response(client, pid, ok=True).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.RUNNING)
        assert server.globalData.allPTWs[pid].getIssuing() == 'issuing'

        assert hold_request(client, pid, held_ics=['4']).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.WAITING_HLD_CONFIRM)
        assert hold_response(client, pid, ok=True).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.HELD)
        assert server.globalData.allPTWs[pid].getHeldICs() == ['4']

        # resume: a fresh cycle
        assert run_request(client, pid).status_code == 200
        assert run_response(client, pid, ok=True).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.RUNNING)
        assert len(server.ptwDB.getPTWById(pid).run_cycles) == 2

        assert close_request(client, pid).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.WAITING_CLS_CONFIRM)
        assert close_response(client, pid, ok=True).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.CLOSED)

        r = client.post('/ptws/archive', json={'ptw-ids': [pid]}, headers=auth('user_turbo'))
        assert r.status_code == 200
        assert pid not in server.globalData.allPTWs
        assert list_ptws(client, 'user_turbo') == []
        archived = client.get('/ptws/archive', headers=auth('user_turbo')).get_json()['ptws']
        assert [p['id'] for p in archived] == [pid]
        assert archived[0]['running_status'] == 'Closed'

    def test_rejections_revert(self, client, server, approved):
        pid = approved
        run_request(client, pid)
        assert run_response(client, pid, ok=False, comment='not now').status_code == 200
        assert status(server, pid) == (A.APPROVED, R.NOT_RUNNING)
        run_request(client, pid); run_response(client, pid, ok=True)
        hold_request(client, pid)
        assert hold_response(client, pid, ok=False).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.RUNNING)
        close_request(client, pid)
        assert close_response(client, pid, ok=False).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.RUNNING)

    def test_response_without_an_open_request_is_an_error_not_a_silent_write(self, client, server, approved):
        pid = approved
        r = run_response(client, pid, ok=True)
        assert r.status_code == 400 and 'no open run cycle' in r.get_json()['error']
        assert status(server, pid) == (A.APPROVED, R.NOT_RUNNING)
        assert server.ptwDB.getPTWById(pid).run_cycles == []

    def test_close_a_never_run_ptw(self, client, server, approved):
        pid = approved
        assert close_request(client, pid).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.WAITING_CLS_CONFIRM)
        assert close_response(client, pid, ok=False).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.NOT_RUNNING)
        assert close_request(client, pid).status_code == 200
        assert close_response(client, pid, ok=True).status_code == 200
        assert status(server, pid) == (A.APPROVED, R.CLOSED)

    def test_close_request_needs_an_approved_ptw(self, client, server):
        pid = create_ptw(client)
        r = close_request(client, pid)
        assert r.status_code == 403 and 'not approved' in r.get_json()['error']

    def test_archive_needs_closed(self, client, approved):
        r = client.post('/ptws/archive', json={'ptw-ids': [approved]}, headers=auth('user_turbo'))
        assert r.status_code == 403
        assert client.post('/ptws/archive', json={'ptw-ids': [999]}, headers=auth('user_turbo')).status_code == 404

    def test_validity_expiry_blocks_new_runs(self, client, server):
        pid = create_ptw(client)
        approve_fully(client, pid, when=datetime.now() - timedelta(days=30))
        assert server.globalData.allPTWs[pid].isValidityExpired()
        r = run_request(client, pid)
        assert r.status_code == 403 and '14-shift validity' in r.get_json()['error']
        # ...but closing it is still possible (it's an alarm, not an automatic close)
        assert close_request(client, pid).status_code == 200
        assert close_response(client, pid, ok=True).status_code == 200


class TestGasTestGate:
    @pytest.fixture
    def spark(self, client):
        pid = create_ptw(client, type=PTW.Types.SP, hazards=[SPARK], controls=GAS_CONTROLS)
        approve_fully(client, pid, PTW.Types.SP)
        return pid

    def test_run_is_blocked_until_a_reading_is_recorded(self, client, server, spark):
        r = run_request(client, spark)
        assert r.status_code == 403 and 'initial gas test' in r.get_json()['error']
        assert gas_test(client, [spark], as_user='issuing').status_code == 403
        r = gas_test(client, [spark])
        assert r.status_code == 200, r.get_json()
        gt = server.globalData.allPTWs[spark].gas_tests[-1]
        assert gt.username == 'gas'
        assert gt.shift == PTW.gasTestTargetShift().strftime(PTW.TIMESTAMP_FORMAT)     # resolved server-side
        assert run_request(client, spark).status_code == 200
        assert run_response(client, spark, ok=True).status_code == 200
        assert status(server, spark) == (A.APPROVED, R.RUNNING)

    def test_issuing_cannot_accept_a_run_without_the_reading_but_can_reject(self, client, server, spark):
        # sneak the request in via the DB layer (the route would block it)
        server.ptwDB.requestToRunPTW(spark, 'user_turbo', now_ts())
        server.core.syncPtwCache(spark)
        assert run_response(client, spark, ok=True).status_code == 403
        assert run_response(client, spark, ok=False).status_code == 200
        assert status(server, spark) == (A.APPROVED, R.NOT_RUNNING)

    def test_one_reading_for_many_ptws_and_the_not_required_case(self, client, server, spark):
        other = create_ptw(client, type=PTW.Types.SP, hazards=[SPARK], controls=GAS_CONTROLS, equipment='P-2')
        plain = create_ptw(client, equipment='P-3')
        r = gas_test(client, [spark, other, plain])
        assert r.status_code == 400 and 'does not require' in r.get_json()['error']
        assert server.globalData.allPTWs[spark].gas_tests == []        # all-or-nothing
        assert gas_test(client, [spark, other]).status_code == 200
        assert len(server.ptwDB.getPTWById(other).gas_tests) == 1

    def test_reading_for_the_previous_shift_does_not_count(self, client, server, spark):
        stale = PTW.shiftStart(datetime.now()) - timedelta(hours=6)     # squarely inside the previous shift
        assert gas_test(client, [spark], when=stale).status_code == 200
        assert run_request(client, spark).status_code == 403
