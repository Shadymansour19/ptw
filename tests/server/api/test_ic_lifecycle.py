"""Isolation Certificate lifecycle through HTTP, and its coupling to PTWs.

Approval chain (plain and PSIC), isolate request/confirm/execute, de-isolate
request/confirm/execute, linking to PTWs, and the automatic de-isolation request that
fires when every linked PTW has stopped needing the IC (close-accept, hold-accept, unlink).
"""

import pytest

from models.Isolation import IC
from models.PTW import PTW
from conftest import auth, GUEST
from api_helpers import create_ptw, approve_fully, run_request, run_response, hold_request, hold_response, close_request, close_response
from ic_helpers import (
    create_ic, ic_approve, isolate_request, isolate_confirm, isolate_execute, deisolate_request, deisolate_confirm,
    deisolate_execute, link, unlink, get_ic, list_ics, make_active_ic, ic_payload, RETURN, PSIC_TERMS,
)

S = IC.Status


def status(server, ic_id) -> str:
    """Status from the cache AND from a fresh DB read; they must agree."""
    cached = server.globalData.ics[ic_id]
    stored = server.icDB.getICById(ic_id)
    assert cached.getStatus() == stored.getStatus()
    return str(cached.getStatus())


class TestCreate:
    def test_create_stamps_requestor_fields_from_the_caller(self, client, server):
        ic_id = create_ic(client, requestor='someone_else', requestor_department='IT')
        ic = server.icDB.getICById(ic_id)
        assert (ic.requestor, ic.requestor_department, ic.execution_department) == ('user_turbo', 'Turbo', 'Prod')
        assert [i.tag for i in ic.items] == ['XV-101', 'XV-102']
        assert status(server, ic_id) == S.REQUESTED
        assert ic.requestor_timestamp

    def test_psic_cannot_be_set_at_creation(self, client, server):
        ic_id = create_ic(client, is_psic=True, psic_reasons=['x'], psic_moc_number='M')
        ic = server.icDB.getICById(ic_id)
        assert ic.is_psic is False and ic.psic_reasons == [] and ic.psic_moc_number == ''
        assert [[str(a.role) for a in st] for st in ic.requiredApprovers()] == [['Issuing']]

    def test_execution_department_is_required(self, client):
        r = client.post('/ics', json=ic_payload(execution_department=None), headers=auth('user_turbo'))
        assert r.status_code == 400 and 'Execution department' in r.get_json()['error']

    def test_self_isolation_must_stay_in_the_requestors_department(self, client):
        r = client.post('/ics', json=ic_payload(type='Self', execution_department='Prod'), headers=auth('user_turbo'))
        assert r.status_code == 400 and 'own department' in r.get_json()['error']
        r = client.post('/ics', json=ic_payload(type='Self', execution_department='Turbo'), headers=auth('user_turbo'))
        assert r.status_code == 200

    def test_guest_cannot_create(self, client):
        assert client.post('/ics', json=ic_payload(), headers=auth(GUEST)).status_code == 401

    def test_listing_is_department_scoped_for_users_only(self, client):
        a = create_ic(client, 'user_turbo')
        b = create_ic(client, 'user_mech')
        assert {c['id'] for c in list_ics(client, 'user_turbo')} == {a}
        assert {c['id'] for c in list_ics(client, 'user_mech')} == {b}
        assert {c['id'] for c in list_ics(client, 'issuing')} == {a, b}
        assert {c['id'] for c in list_ics(client, 'isolator')} == {a, b}
        assert {c['id'] for c in list_ics(client, 'issuing', department='mech')} == {b}


class TestApprovalChain:
    def test_plain_ic_is_approved_by_issuing_alone(self, client, server):
        ic_id = create_ic(client)
        assert ic_approve(client, ic_id, 'coord').status_code == 403         # not on a plain chain
        assert ic_approve(client, ic_id, 'user_turbo').status_code == 403
        assert ic_approve(client, ic_id, 'issuing').status_code == 200
        assert status(server, ic_id) == S.APPROVED
        assert ic_approve(client, ic_id, 'issuing').status_code == 403       # not twice
        rec = server.icDB.getICById(ic_id).approvals[0]
        assert (rec.role, rec.department, rec.username) == ('Issuing', 'Prod', 'issuing')

    def test_return_then_nothing_else_is_eligible(self, client, server):
        ic_id = create_ic(client)
        assert ic_approve(client, ic_id, 'issuing', action=RETURN, comment='wrong tags').status_code == 200
        assert status(server, ic_id) == S.RETURNED
        assert isolate_request(client, ic_id).status_code == 403

    def test_psic_chain(self, client, server):
        ic_id = create_ic(client)
        # only Issuing may flag PSIC, and only while approving
        assert ic_approve(client, ic_id, 'issuing', mark_psic=True).status_code == 200
        ic = server.icDB.getICById(ic_id)
        assert ic.is_psic is True
        assert status(server, ic_id) == S.REQUESTED                          # five more stages to go
        assert ic_approve(client, ic_id, 'pdh').status_code == 403           # Coordinator first
        # Coordinator's approval must carry complete terms
        r = ic_approve(client, ic_id, 'coord')
        assert r.status_code == 400 and 'PSIC reason' in r.get_json()['error']
        r = ic_approve(client, ic_id, 'coord', psic_terms=dict(PSIC_TERMS, psic_control_measures='  '))
        assert r.status_code == 400 and 'control measures' in r.get_json()['error']
        assert len(server.icDB.getICById(ic_id).approvals) == 1              # nothing was recorded
        assert ic_approve(client, ic_id, 'coord', psic_terms=PSIC_TERMS).status_code == 200
        ic = server.icDB.getICById(ic_id)
        assert ic.psic_reasons == ['Maintenance'] and ic.psic_isolation_method == 'Forced bypass'
        for u in ('pdh', 'pgm', 'sod'):
            assert ic_approve(client, ic_id, 'dfgm').status_code == 403, u   # strict order
            assert ic_approve(client, ic_id, u).status_code == 200
        assert status(server, ic_id) == S.REQUESTED
        assert ic_approve(client, ic_id, 'dfgm').status_code == 200
        assert status(server, ic_id) == S.APPROVED

    def test_mark_psic_is_ignored_for_other_roles_and_is_sticky(self, client, server):
        ic_id = create_ic(client)
        assert ic_approve(client, ic_id, 'issuing', mark_psic=True).status_code == 200
        ic_approve(client, ic_id, 'coord', psic_terms=PSIC_TERMS, mark_psic=True)
        assert server.icDB.getICById(ic_id).is_psic is True
        plain = create_ic(client)
        ic_approve(client, plain, 'issuing', mark_psic=False)
        assert server.icDB.getICById(plain).is_psic is False

    def test_coordinator_terms_are_ignored_on_a_plain_ic(self, client, server):
        ic_id = create_ic(client)
        ic_approve(client, ic_id, 'issuing')
        assert ic_approve(client, ic_id, 'coord', psic_terms=PSIC_TERMS).status_code == 403

    def test_isolate_asap_skips_the_manual_request_only_at_full_approval(self, client, server):
        ic_id = create_ic(client, isolate_asap=True)
        assert ic_approve(client, ic_id, 'issuing', mark_psic=True).status_code == 200
        assert status(server, ic_id) == S.REQUESTED                         # Issuing alone doesn't complete a PSIC
        assert server.icDB.getICById(ic_id).isolate_requestor is None
        ic_approve(client, ic_id, 'coord', psic_terms=PSIC_TERMS)
        for u in ('pdh', 'pgm', 'sod', 'dfgm'):
            ic_approve(client, ic_id, u)
        ic = server.icDB.getICById(ic_id)
        assert ic.isolate_requestor == 'user_turbo' and ic.isolate_requestor_timestamp
        assert status(server, ic_id) == S.ISOLATE_CONFIRMING

    def test_unknown_ic(self, client):
        assert ic_approve(client, 999, 'issuing').status_code == 404
        assert isolate_request(client, 999).status_code == 404


class TestIsolateCycle:
    @pytest.fixture
    def approved(self, client):
        ic_id = create_ic(client)
        ic_approve(client, ic_id, 'issuing')
        return ic_id

    def test_request_confirm_execute(self, client, server, approved):
        ic_id = approved
        assert isolate_confirm(client, ic_id).status_code == 403                # nothing requested yet
        assert isolate_execute(client, ic_id).status_code == 403
        assert isolate_request(client, ic_id, as_user='user_mech').status_code == 200   # any non-guest
        assert status(server, ic_id) == S.ISOLATE_CONFIRMING
        assert isolate_request(client, ic_id).status_code == 403                # not twice
        assert isolate_confirm(client, ic_id, as_user='coord').status_code == 403      # Issuing only
        assert isolate_execute(client, ic_id).status_code == 403                # not confirmed yet
        assert isolate_confirm(client, ic_id).status_code == 200
        assert status(server, ic_id) == S.PENDING
        assert isolate_execute(client, ic_id, as_user='issuing').status_code == 403     # Isolator only
        r = isolate_execute(client, ic_id, as_user='isolator_mech')
        assert r.status_code == 403 and 'different execution department' in r.get_json()['error']
        r = isolate_execute(client, ic_id, items=[
            {'tag': 'XV-101', 'lock_num': 'L-7', 'lock_box_num': 'B-2', 'description': 'tampered', 'state': 'open'},
            {'tag': 'XV-999', 'lock_num': 'L-0'},                                    # unknown tag dropped
        ])
        assert r.status_code == 200
        assert status(server, ic_id) == S.ACTIVE
        items = {i.tag: i for i in server.icDB.getICById(ic_id).items}
        assert set(items) == {'XV-101', 'XV-102'}
        assert (items['XV-101'].lock_num, items['XV-101'].lock_box_num) == ('L-7', 'B-2')
        # only the lock fields are taken from the client; tag/description/state stay server-side
        assert items['XV-101'].description == 'Inlet valve' and items['XV-101'].state == 'close'
        assert items['XV-102'].lock_num == ''

    def test_returned_isolate_request_can_be_re_requested_cleanly(self, client, server, approved):
        ic_id = approved
        isolate_request(client, ic_id)
        assert isolate_confirm(client, ic_id, ok=False).status_code == 200
        assert status(server, ic_id) == S.APPROVED
        assert isolate_request(client, ic_id).status_code == 200
        ic = server.icDB.getICById(ic_id)
        assert ic.isolate_issuing is None and ic.isolate_issuing_action == ''   # stale decision cleared
        assert status(server, ic_id) == S.ISOLATE_CONFIRMING

    def test_deisolate_cycle(self, client, server):
        ic_id = make_active_ic(client)
        assert deisolate_confirm(client, ic_id).status_code == 403
        assert deisolate_execute(client, ic_id).status_code == 403
        assert deisolate_request(client, ic_id).status_code == 200
        assert status(server, ic_id) == S.DEISOLATE_CONFIRMING
        assert deisolate_confirm(client, ic_id, ok=False).status_code == 200
        assert status(server, ic_id) == S.ACTIVE
        assert deisolate_request(client, ic_id).status_code == 200
        assert deisolate_confirm(client, ic_id).status_code == 200
        assert status(server, ic_id) == S.CLOSING
        assert deisolate_execute(client, ic_id, as_user='isolator_mech').status_code == 403
        assert deisolate_execute(client, ic_id).status_code == 200
        assert status(server, ic_id) == S.CLOSED
        assert deisolate_request(client, ic_id).status_code == 403             # terminal
        assert isolate_request(client, ic_id).status_code == 403


class TestLinking:
    @pytest.fixture
    def approved_ptw(self, client):
        pid = create_ptw(client)
        approve_fully(client, pid)
        return pid

    def test_link_rules(self, client, server, approved_ptw):
        ic_id = create_ic(client)
        under_review = create_ptw(client, equipment='P-2')
        assert link(client, ic_id, approved_ptw, as_user='isolator').status_code == 403     # role gate
        assert link(client, ic_id, under_review).status_code == 403                        # PTW not approved
        assert link(client, ic_id, 999).status_code == 404
        assert link(client, 999, approved_ptw).status_code == 404
        assert link(client, ic_id, approved_ptw).status_code == 200
        assert link(client, ic_id, approved_ptw).status_code == 400                        # already linked
        assert server.icDB.getICById(ic_id).linked_ptws == [str(approved_ptw)]
        assert server.ptwDB.getPTWById(approved_ptw).linked_ics == [str(ic_id)]
        assert server.globalData.allPTWs[approved_ptw].linked_ics == [str(ic_id)]           # cache resynced

    def test_run_is_blocked_until_every_linked_ic_is_active(self, client, server, approved_ptw):
        ic_id = create_ic(client)
        ic_approve(client, ic_id, 'issuing')
        link(client, ic_id, approved_ptw)
        r = run_request(client, approved_ptw)
        assert r.status_code == 403 and 'not isolated' in r.get_json()['error']
        isolate_request(client, ic_id); isolate_confirm(client, ic_id)
        assert run_request(client, approved_ptw).status_code == 403                        # PENDING isn't enough
        isolate_execute(client, ic_id)
        assert run_request(client, approved_ptw).status_code == 200
        assert run_response(client, approved_ptw, ok=True).status_code == 200
        # a running PTW can no longer be linked or unlinked
        other = create_ic(client, equipment='P-9')
        ic_approve(client, other, 'issuing')
        assert link(client, other, approved_ptw).status_code == 403
        assert unlink(client, ic_id, approved_ptw).status_code == 403

    def test_unlink_rules(self, client, server, approved_ptw):
        ic_id = create_ic(client)
        ic_approve(client, ic_id, 'issuing')
        assert unlink(client, ic_id, approved_ptw).status_code == 400                      # not linked
        link(client, ic_id, approved_ptw)
        assert unlink(client, ic_id, approved_ptw, as_user='hse').status_code == 403
        assert unlink(client, ic_id, approved_ptw).status_code == 200
        assert server.icDB.getICById(ic_id).linked_ptws == []
        assert server.ptwDB.getPTWById(approved_ptw).linked_ics == []
        # once physically isolated the link is frozen
        link(client, ic_id, approved_ptw)
        isolate_request(client, ic_id); isolate_confirm(client, ic_id); isolate_execute(client, ic_id)
        assert unlink(client, ic_id, approved_ptw).status_code == 403

    def test_winding_down_ic_cannot_take_new_links(self, client, server, approved_ptw):
        ic_id = make_active_ic(client)
        deisolate_request(client, ic_id)
        assert link(client, ic_id, approved_ptw).status_code == 403


class TestAutoDeisolate:
    """The IC's link is never removed; instead a de-isolate request is raised automatically
    once no linked PTW still needs it."""

    def _running_ptw_on(self, client, ic_id, **over):
        pid = create_ptw(client, **over)
        approve_fully(client, pid)
        assert link(client, ic_id, pid).status_code == 200
        assert run_request(client, pid).status_code == 200
        assert run_response(client, pid, ok=True).status_code == 200
        return pid

    def test_close_accept_requests_deisolation(self, client, server):
        ic_id = make_active_ic(client)
        pid = self._running_ptw_on(client, ic_id)
        close_request(client, pid)
        assert status(server, ic_id) == S.ACTIVE                              # a pending close changes nothing
        close_response(client, pid, ok=True)
        assert status(server, ic_id) == S.DEISOLATE_CONFIRMING
        ic = server.icDB.getICById(ic_id)
        assert ic.deisolate_requestor == 'system' and ic.linked_ptws == [str(pid)]

    def test_hold_without_keeping_the_ic(self, client, server):
        ic_id = make_active_ic(client)
        pid = self._running_ptw_on(client, ic_id)
        hold_request(client, pid, held_ics=[])
        hold_response(client, pid, ok=True)
        assert status(server, ic_id) == S.DEISOLATE_CONFIRMING

    def test_hold_keeping_the_ic_leaves_it_active(self, client, server):
        ic_id = make_active_ic(client)
        pid = self._running_ptw_on(client, ic_id)
        hold_request(client, pid, held_ics=[str(ic_id)])
        hold_response(client, pid, ok=True)
        assert status(server, ic_id) == S.ACTIVE
        # resume, then close: now it goes
        run_request(client, pid); run_response(client, pid, ok=True)
        close_request(client, pid); close_response(client, pid, ok=True)
        assert status(server, ic_id) == S.DEISOLATE_CONFIRMING

    def test_waits_for_the_last_linked_ptw(self, client, server):
        ic_id = make_active_ic(client)
        a = self._running_ptw_on(client, ic_id, equipment='A')
        b = self._running_ptw_on(client, ic_id, equipment='B')
        close_request(client, a); close_response(client, a, ok=True)
        assert status(server, ic_id) == S.ACTIVE                              # b still needs it
        close_request(client, b); close_response(client, b, ok=True)
        assert status(server, ic_id) == S.DEISOLATE_CONFIRMING

    def test_manual_unlink_of_the_last_idle_ptw_does_not_fire_on_a_non_active_ic(self, client, server):
        ic_id = create_ic(client)
        ic_approve(client, ic_id, 'issuing')
        pid = create_ptw(client)
        approve_fully(client, pid)
        link(client, ic_id, pid)
        unlink(client, ic_id, pid)
        assert status(server, ic_id) == S.APPROVED                            # nothing to de-isolate yet

    def test_rejected_close_does_not_fire(self, client, server):
        ic_id = make_active_ic(client)
        pid = self._running_ptw_on(client, ic_id)
        close_request(client, pid); close_response(client, pid, ok=False)
        assert status(server, ic_id) == S.ACTIVE

    def test_returned_auto_request_can_be_raised_again_by_a_person(self, client, server):
        ic_id = make_active_ic(client)
        pid = self._running_ptw_on(client, ic_id)
        close_request(client, pid); close_response(client, pid, ok=True)
        assert deisolate_confirm(client, ic_id, ok=False).status_code == 200
        assert status(server, ic_id) == S.ACTIVE
        assert deisolate_request(client, ic_id, as_user='issuing').status_code == 200
        assert server.icDB.getICById(ic_id).deisolate_requestor == 'issuing'
        assert deisolate_confirm(client, ic_id).status_code == 200
        assert deisolate_execute(client, ic_id).status_code == 200
        assert status(server, ic_id) == S.CLOSED


class TestPermissionGates:
    @pytest.mark.parametrize("path, allowed", [
        ('/ics/isolate-confirm', {'issuing'}),
        ('/ics/deisolate-confirm', {'issuing'}),
        ('/ics/isolate-execute', {'isolator', 'isolator_mech'}),
        ('/ics/deisolate-execute', {'isolator', 'isolator_mech'}),
        ('/ics/link-ptw', {'user_turbo', 'issuing', 'coord'}),
        ('/ics/unlink-ptw', {'user_turbo', 'issuing', 'coord'}),
    ])
    def test_role_gate(self, client, path, allowed):
        for user in ('user_turbo', 'coord', 'issuing', 'hse', 'isolator', 'isolator_mech', 'pgm', 'admin'):
            code = client.post(path, json={}, headers=auth(user)).status_code
            assert code == (400 if user in allowed else 403), (path, user, code)
        assert client.post(path, json={}, headers=auth(GUEST)).status_code in (401, 403)
