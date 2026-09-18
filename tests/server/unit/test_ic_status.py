"""IC (Isolation Certificate) lifecycle status derivation and PTW linking rules."""

import pytest

from models.Isolation import IC
from models.User import UserRoles
from models.PTW import PTW
from ptw_factory import make_ic, ic_approval, make_ptw, approved_ptw, running_cycle
from datetime import datetime

S = IC.Status
OK = str(IC.ApprovalActions.APPROVED)
RET = str(IC.ApprovalActions.RETURNED)


class TestApprovalChain:
    def test_plain_ic_needs_only_issuing(self):
        ic = make_ic()
        assert [[a.role for a in st] for st in ic.requiredApprovers()] == [[UserRoles.ISSUING]]
        assert ic.getStatus() == S.REQUESTED
        assert ic.getApprovalStatus(UserRoles.ISSUING, 'Prod') == S.REQUESTED
        assert make_ic(approvals=[ic_approval(UserRoles.ISSUING)]).getStatus() == S.APPROVED

    def test_psic_chain(self):
        ic = make_ic(is_psic=True)
        roles = [[a.role for a in st] for st in ic.requiredApprovers()]
        assert roles == [[UserRoles.ISSUING], [UserRoles.COORDINATOR], [UserRoles.PDH], [UserRoles.PGM], [UserRoles.SOD], [UserRoles.DFGM]]
        chain = [ic_approval(r) for r in (UserRoles.ISSUING, UserRoles.COORDINATOR, UserRoles.PDH, UserRoles.PGM, UserRoles.SOD)]
        assert make_ic(is_psic=True, approvals=chain).getStatus() == S.REQUESTED
        assert make_ic(is_psic=True, approvals=chain).getApprovalStatus(UserRoles.DFGM, 'Prod') == S.REQUESTED
        assert make_ic(is_psic=True, approvals=chain).getApprovalStatus(UserRoles.PDH, 'Prod') == OK
        chain.append(ic_approval(UserRoles.DFGM))
        assert make_ic(is_psic=True, approvals=chain).getStatus() == S.APPROVED

    def test_return(self):
        ic = make_ic(approvals=[ic_approval(UserRoles.ISSUING, action=RET)])
        assert ic.getStatus() == S.RETURNED
        assert ic.getApprovalStatus(UserRoles.ISSUING, 'Prod') == RET

    def test_department_does_not_matter_for_ic_approvers(self):
        assert make_ic(approvals=[ic_approval(UserRoles.ISSUING, department='IT')]).getStatus() == S.APPROVED


APPROVED = [ic_approval(UserRoles.ISSUING)]


@pytest.mark.parametrize("fields, expected", [
    ({}, S.APPROVED),
    ({'isolate_requestor': 'u'}, S.ISOLATE_CONFIRMING),
    ({'isolate_requestor': 'u', 'isolate_issuing_action': RET}, S.APPROVED),           # returned: back to approved
    ({'isolate_requestor': 'u', 'isolate_issuing_action': OK}, S.PENDING),
    ({'isolate_requestor': 'u', 'isolate_issuing_action': OK, 'isolate_isolator': 'iso'}, S.ACTIVE),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u'}, S.DEISOLATE_CONFIRMING),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u', 'deisolate_issuing_action': RET}, S.ACTIVE),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u', 'deisolate_issuing_action': OK}, S.CLOSING),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u', 'deisolate_issuing_action': OK, 'deisolate_isolator': 'iso'}, S.CLOSED),
    ({'isolate_isolator': 'iso', 'sanction_isolator': 'iso'}, S.SANCTIONED),
    ({'isolate_isolator': 'iso', 'sanction_isolator': 'iso', 'reisolate_isolator': 'iso'}, S.ACTIVE),
    ({'isolate_isolator': 'iso', 'sanction_isolator': 'iso', 'reisolate_isolator': 'iso', 'deisolate_isolator': 'iso'}, S.CLOSED),
])
def test_status_precedence(fields, expected):
    assert make_ic(approvals=APPROVED, **fields).getStatus() == expected


def test_isolation_state_overrides_an_unapproved_chain():
    # Physical state wins over the approval chain, whatever it says.
    assert make_ic(isolate_isolator='iso').getStatus() == S.ACTIVE
    assert make_ic(deisolate_isolator='iso').getStatus() == S.CLOSED


@pytest.mark.parametrize("fields, winding_down", [
    ({}, False),
    ({'isolate_isolator': 'iso'}, False),
    ({'isolate_isolator': 'iso', 'sanction_isolator': 'iso'}, True),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u'}, True),
    ({'isolate_isolator': 'iso', 'deisolate_requestor': 'u', 'deisolate_issuing_action': OK}, True),
    ({'deisolate_isolator': 'iso'}, True),
])
def test_is_winding_down(fields, winding_down):
    assert make_ic(approvals=APPROVED, **fields).isWindingDown() is winding_down


class TestPtwLinking:
    T0 = datetime(2026, 9, 1, 8, 0)

    def test_link_needs_idle_approved_ptw_and_live_ic(self):
        ic = make_ic(approvals=APPROVED)
        assert ic.canLinkPTW(approved_ptw()) is True
        assert ic.canLinkPTW(make_ptw()) is False
        assert ic.canLinkPTW(approved_ptw(run_cycles=[running_cycle(self.T0)])) is False
        assert ic.canLinkPTW(None) is False
        assert make_ic(approvals=APPROVED, deisolate_isolator='iso').canLinkPTW(approved_ptw()) is False

    def test_unlink_rules(self):
        held = running_cycle(self.T0)
        held.update(stop_pa='u', stop_pa_request=str(PTW.RunCycle.StopTypes.HOLD), stop_ia='i', stop_ia_action=str(PTW.RunCycle.Actions.APPROVED))
        ic = make_ic(approvals=APPROVED)
        assert ic.canUnlinkPTW(approved_ptw()) is True
        assert ic.canUnlinkPTW(approved_ptw(run_cycles=[held])) is True
        assert ic.canUnlinkPTW(approved_ptw(run_cycles=[running_cycle(self.T0)])) is False
        assert ic.canUnlinkPTW(None) is False
        assert make_ic(approvals=APPROVED, isolate_isolator='iso').canUnlinkPTW(approved_ptw()) is False

    def test_link_and_unlink_bookkeeping(self):
        ic = make_ic(approvals=APPROVED)
        ic.held_by = ['12']
        ic.linkPTW(12)
        assert ic.linked_ptws == ['12'] and ic.held_by == []
        ic.linkPTW('12')
        assert ic.linked_ptws == ['12']
        ic.unlinkPTW(12)
        assert ic.linked_ptws == []


def test_ic_round_trips_through_setall():
    src = make_ic(approvals=APPROVED, isolate_isolator='iso', items=[{'tag': 'XV-1'}])
    from utils import objToDict
    clone = IC(objToDict(src))
    assert clone.getStatus() == S.ACTIVE
    assert clone.items[0].tag == 'XV-1'
