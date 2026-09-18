"""The approval cycle: required stages per permit type, eligibility, ordering, returns."""

from datetime import datetime

import pytest

from models.PTW import PTW
from models.User import UserRoles, UserDepartments, SecuredUser
from GlobalData import globalData
from ptw_factory import (
    make_ptw, approval, full_chain, approved_ptw, COORD, ISSUING, HSE, PGM, DFGM, EX_DEPARTMENTS,
)

A = PTW.ApprovalStatus


def slots(stage):
    return [(a.role, a.department) for a in stage]


class TestRequiredApprovers:
    def test_cold_work_chain(self):
        stages = make_ptw(PTW.Types.CW).requiredApprovers()
        assert [slots(s) for s in stages] == [[COORD], [ISSUING, HSE]]

    @pytest.mark.parametrize("type", [PTW.Types.SP, PTW.Types.HC])
    def test_spark_and_hydrocarbon_use_the_base_chain(self, type):
        stages = make_ptw(type).requiredApprovers()
        assert [slots(s) for s in stages] == [[COORD], [ISSUING, HSE]]

    @pytest.mark.parametrize("type", [PTW.Types.HT, PTW.Types.CS])
    def test_hot_work_and_confined_space_add_pgm_then_dfgm(self, type):
        stages = make_ptw(type).requiredApprovers()
        assert [slots(s) for s in stages] == [[COORD], [ISSUING, HSE], [PGM], [DFGM]]

    def test_excavation_adds_parallel_department_stage(self):
        stages = make_ptw(PTW.Types.EX).requiredApprovers()
        assert slots(stages[0]) == [COORD]
        assert slots(stages[1]) == [(UserRoles.USER, d) for d in EX_DEPARTMENTS]
        assert slots(stages[2]) == [ISSUING, HSE]
        assert len(stages) == 3

    def test_fast_track_does_not_change_the_chain(self):
        assert [slots(s) for s in make_ptw(fast_track=True).requiredApprovers()] == \
               [slots(s) for s in make_ptw(fast_track=False).requiredApprovers()]


class TestStatusReplay:
    def test_fresh_ptw_is_under_review_with_everyone_pending(self):
        ptw = make_ptw()
        assert ptw.approval_status == A.UNDER_REVIEW
        assert slots(ptw.pendingApprovers()) == [COORD, ISSUING, HSE]

    def test_coordinator_approval_advances_to_next_stage(self):
        ptw = make_ptw(approvals=[approval(*COORD)])
        assert ptw.approval_status == A.UNDER_REVIEW
        assert slots(ptw.pendingApprovers()) == [ISSUING, HSE]

    def test_partial_parallel_stage_stays_under_review(self):
        ptw = make_ptw(approvals=[approval(*COORD), approval(*ISSUING)])
        assert ptw.approval_status == A.UNDER_REVIEW
        assert slots(ptw.pendingApprovers()) == [HSE]

    @pytest.mark.parametrize("type", list(PTW.Types))
    def test_full_chain_approves_every_type(self, type):
        ptw = make_ptw(type, approvals=full_chain(type))
        assert ptw.approval_status == A.APPROVED
        assert ptw.pendingApprovers() == []

    @pytest.mark.parametrize("type", list(PTW.Types))
    def test_dropping_any_one_approval_leaves_it_under_review(self, type):
        chain = full_chain(type)
        for i in range(len(chain)):
            ptw = make_ptw(type, approvals=chain[:i] + chain[i + 1:])
            assert ptw.approval_status == A.UNDER_REVIEW, f"missing approval #{i} ({chain[i]['role']})"

    def test_wrong_department_user_does_not_satisfy_excavation_slot(self):
        chain = [approval(*COORD)] + [approval(UserRoles.USER, d) for d in EX_DEPARTMENTS if d != UserDepartments.MECH]
        chain.append(approval(UserRoles.USER, UserDepartments.HVAC))   # not one of the 8
        ptw = make_ptw(PTW.Types.EX, approvals=chain)
        assert slots(ptw.pendingApprovers())[0] == (UserRoles.USER, UserDepartments.MECH)

    def test_any_return_makes_the_ptw_returned_even_if_others_approved(self):
        chain = [approval(*COORD), approval(*ISSUING), approval(*HSE, action=PTW.ApprovalActions.RETURNED)]
        assert make_ptw(approvals=chain).approval_status == A.RETURNED
        # ... and a later approval doesn't un-return it
        chain.append(approval(*HSE))
        assert make_ptw(approvals=chain).approval_status == A.RETURNED

    def test_dfgm_slot_ignores_department(self):
        chain = full_chain(PTW.Types.HT)
        chain[-1]['department'] = str(UserDepartments.IT)
        assert make_ptw(PTW.Types.HT, approvals=chain).approval_status == A.APPROVED

    def test_clear_approvals_resets_everything(self):
        ptw = approved_ptw()
        ptw.run_cycles = [PTW.RunCycle(run_pa='x')]
        ptw.clearApprovals()
        assert ptw.approval_status == A.UNDER_REVIEW
        assert ptw.run_cycles == [] and ptw.approvals == []

    def test_update_approvals_appends_and_recomputes(self):
        ptw = make_ptw(approvals=[approval(*COORD), approval(*ISSUING)])
        ptw.updateApprovals(PTW.Approval(**approval(*HSE)))
        assert ptw.approval_status == A.APPROVED


class TestEligibility:
    """getApprovalStatus(role, dept) is what the /ptws/approvals route gates on."""

    def test_only_current_stage_is_eligible(self):
        ptw = make_ptw()
        assert ptw.getApprovalStatus(*COORD) == A.UNDER_REVIEW
        assert ptw.getApprovalStatus(*ISSUING) is None     # not their turn yet
        assert ptw.getApprovalStatus(*HSE) is None
        assert ptw.getApprovalStatus(UserRoles.USER, UserDepartments.TURBO) is None

    def test_after_coordinator_both_parallel_approvers_are_eligible(self):
        ptw = make_ptw(approvals=[approval(*COORD)])
        assert ptw.getApprovalStatus(*COORD) == PTW.ApprovalActions.APPROVED   # what they did
        assert ptw.getApprovalStatus(*ISSUING) == A.UNDER_REVIEW
        assert ptw.getApprovalStatus(*HSE) == A.UNDER_REVIEW

    def test_pgm_only_after_issuing_and_hse(self):
        ptw = make_ptw(PTW.Types.HT, approvals=[approval(*COORD), approval(*ISSUING)])
        assert ptw.getApprovalStatus(*PGM) is None
        ptw.updateApprovals(PTW.Approval(**approval(*HSE)))
        assert ptw.getApprovalStatus(*PGM) == A.UNDER_REVIEW
        assert ptw.getApprovalStatus(*DFGM) is None

    def test_coordinator_of_other_department_is_not_eligible(self):
        assert make_ptw().getApprovalStatus(UserRoles.COORDINATOR, UserDepartments.MECH) is None

    def test_returned_action_is_reported_to_its_author(self):
        ptw = make_ptw(approvals=[approval(*COORD, action=PTW.ApprovalActions.RETURNED)])
        assert ptw.getApprovalStatus(*COORD) == PTW.ApprovalActions.RETURNED
        assert ptw.getApprovalStatus() == A.RETURNED


class TestLegacyApprovalsWithoutSnapshot:
    """Records written before the role/department snapshot fall back to the live user."""

    @pytest.fixture(autouse=True)
    def users(self):
        saved = globalData.allUsers
        globalData.allUsers = {
            'legacy_coord': SecuredUser(username='legacy_coord', name='C', role=UserRoles.COORDINATOR, department=UserDepartments.PROD),
        }
        yield
        globalData.allUsers = saved

    def test_live_user_lookup(self):
        rec = approval(*COORD, username='legacy_coord')
        rec['role'] = None
        rec['department'] = None
        ptw = make_ptw(approvals=[rec])
        assert slots(ptw.pendingApprovers()) == [ISSUING, HSE]

    def test_deleted_legacy_user_is_not_credited(self):
        rec = approval(*COORD, username='gone')
        rec['role'] = None
        rec['department'] = None
        ptw = make_ptw(approvals=[rec])
        assert slots(ptw.pendingApprovers()) == [COORD, ISSUING, HSE]


class TestFullApprovalTimestamp:
    def test_timestamp_of_the_completing_approval(self):
        when = datetime(2026, 9, 3, 15, 30, 0)
        ptw = approved_ptw(approved_at=when)
        assert ptw.fullApprovalTimestamp() == when

    def test_none_while_under_review(self):
        assert make_ptw(approvals=[approval(*COORD)]).fullApprovalTimestamp() is None

    def test_malformed_timestamp_is_none_not_a_crash(self):
        chain = full_chain()
        chain[-1]['timestamp'] = 'yesterday-ish'
        ptw = make_ptw(approvals=chain)
        assert ptw.approval_status == A.APPROVED
        assert ptw.fullApprovalTimestamp() is None
        assert ptw.validityExpiry() is None
        assert ptw.isValidityExpired() is False
