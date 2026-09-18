"""The running cycle state machine, replayed from run_cycles, plus the shift/validity limits."""

from datetime import datetime, timedelta

import pytest

from models.PTW import PTW
from ptw_factory import make_ptw, approved_ptw, run_cycle, running_cycle, ts

R = PTW.RunningStatus
OK = str(PTW.RunCycle.Actions.APPROVED)
NO = str(PTW.RunCycle.Actions.REJECTED)
HOLD = str(PTW.RunCycle.StopTypes.HOLD)
CLOSE = str(PTW.RunCycle.StopTypes.CLOSE)

T0 = datetime(2026, 9, 1, 8, 0, 0)          # a day-shift morning
APPROVED_AT = datetime(2026, 8, 31, 10, 0, 0)


def ptw_with(*cycles, **over):
    return approved_ptw(approved_at=APPROVED_AT, run_cycles=list(cycles), **over)


class TestReplay:
    def test_no_cycles_means_not_running(self):
        assert ptw_with().running_status == R.NOT_RUNNING

    def test_unapproved_ptw_is_never_running_whatever_the_cycles_say(self):
        ptw = make_ptw(run_cycles=[running_cycle(T0)])
        assert ptw.approval_status == PTW.ApprovalStatus.UNDER_REVIEW
        assert ptw.running_status == R.NOT_RUNNING

    def test_run_request_waits_for_issuing(self):
        ptw = ptw_with(run_cycle(run_pa='u', run_pa_timestamp=ts(T0)))
        assert ptw.running_status == R.WAITING_RUN_CONFIRM
        assert ptw.getPerforming() == 'u'
        assert ptw.getIssuing() is None

    def test_run_accepted(self):
        ptw = ptw_with(running_cycle(T0))
        assert ptw.running_status == R.RUNNING
        assert ptw.getIssuing() == 'issuing_prod'
        assert ptw.getIssuingTimestamp() == ts(T0)

    def test_run_rejected_reverts_to_not_running_and_closes_the_cycle(self):
        ptw = ptw_with(run_cycle(run_pa='u', run_pa_timestamp=ts(T0), run_ia='i', run_ia_action=NO, run_ia_timestamp=ts(T0)))
        assert ptw.running_status == R.NOT_RUNNING
        assert ptw.currentRunCycle() is None
        assert ptw.lastRunCycle() is not None
        assert ptw.operativeRunCycle() is None
        assert ptw.getPerforming() is None

    def test_hold_request_then_accept(self):
        cyc = running_cycle(T0)
        cyc.update(stop_pa='u', stop_pa_request=HOLD, stop_pa_timestamp=ts(T0), held_ics=['7'])
        assert ptw_with(cyc).running_status == R.WAITING_HLD_CONFIRM
        cyc.update(stop_ia='i', stop_ia_action=OK, stop_ia_timestamp=ts(T0))
        ptw = ptw_with(cyc)
        assert ptw.running_status == R.HELD
        assert ptw.getHeldICs() == ['7']
        assert ptw.currentRunCycle() is None          # a fully accepted stop closes the cycle

    def test_hold_rejected_keeps_running(self):
        cyc = running_cycle(T0)
        cyc.update(stop_pa='u', stop_pa_request=HOLD, stop_ia='i', stop_ia_action=NO)
        ptw = ptw_with(cyc)
        assert ptw.running_status == R.RUNNING
        assert ptw.currentRunCycle() is not None

    def test_resume_from_held_appends_a_fresh_cycle(self):
        held = running_cycle(T0)
        held.update(stop_pa='u', stop_pa_request=HOLD, stop_ia='i', stop_ia_action=OK, held_ics=['7'])
        resume = run_cycle(run_pa='u', run_pa_timestamp=ts(T0 + timedelta(hours=3)))
        ptw = ptw_with(held, resume)
        assert ptw.running_status == R.WAITING_RUN_CONFIRM
        resume.update(run_ia='i', run_ia_action=OK, run_ia_timestamp=ts(T0 + timedelta(hours=3)))
        ptw = ptw_with(held, resume)
        assert ptw.running_status == R.RUNNING
        assert ptw.getHeldICs() == []                 # the operative cycle is now the resumed one

    def test_rejected_resume_falls_back_to_held_and_keeps_held_ics(self):
        held = running_cycle(T0)
        held.update(stop_pa='u', stop_pa_request=HOLD, stop_ia='i', stop_ia_action=OK, held_ics=['7', '9'])
        rejected = run_cycle(run_pa='u', run_pa_timestamp=ts(T0), run_ia='i', run_ia_action=NO)
        ptw = ptw_with(held, rejected)
        assert ptw.running_status == R.HELD
        assert ptw.getHeldICs() == ['7', '9']
        assert ptw.operativeRunCycle().held_ics == ['7', '9']

    def test_close_request_then_accept(self):
        cyc = running_cycle(T0)
        cyc.update(stop_pa='u', stop_pa_request=CLOSE)
        assert ptw_with(cyc).running_status == R.WAITING_CLS_CONFIRM
        cyc.update(stop_ia='i', stop_ia_action=OK, stop_ia_timestamp=ts(T0 + timedelta(hours=2)))
        assert ptw_with(cyc).running_status == R.CLOSED

    def test_close_rejected_keeps_running(self):
        cyc = running_cycle(T0)
        cyc.update(stop_pa='u', stop_pa_request=CLOSE, stop_ia='i', stop_ia_action=NO)
        assert ptw_with(cyc).running_status == R.RUNNING

    def test_close_without_ever_running(self):
        cyc = run_cycle(stop_pa='u', stop_pa_request=CLOSE, stop_pa_timestamp=ts(T0))
        assert ptw_with(cyc).running_status == R.WAITING_CLS_CONFIRM
        rejected = dict(cyc, stop_ia='i', stop_ia_action=NO)
        assert ptw_with(rejected).running_status == R.NOT_RUNNING     # not RUNNING: it never ran
        accepted = dict(cyc, stop_ia='i', stop_ia_action=OK)
        assert ptw_with(accepted).running_status == R.CLOSED

    def test_can_link_ic_only_while_approved_and_idle(self):
        assert ptw_with().canLinkIC() is True
        assert ptw_with(run_cycle(run_pa='u')).canLinkIC() is False
        assert ptw_with(running_cycle(T0)).canLinkIC() is False
        assert make_ptw().canLinkIC() is False

    def test_run_cycle_is_open(self):
        assert PTW.RunCycle().isOpen()
        assert PTW.RunCycle(run_ia_action=OK).isOpen()
        assert not PTW.RunCycle(run_ia_action=NO).isOpen()
        assert not PTW.RunCycle(run_ia_action=OK, stop_ia_action=OK).isOpen()
        assert PTW.RunCycle(run_ia_action=OK, stop_ia_action=NO).isOpen()


class TestShiftLimits:
    @pytest.mark.parametrize("accepted, expected_end", [
        (datetime(2026, 9, 1, 8, 0),  datetime(2026, 9, 1, 19, 0)),   # day shift: valid until 19:00, not 20:00
        (datetime(2026, 9, 1, 18, 59), datetime(2026, 9, 1, 19, 0)),
        (datetime(2026, 9, 1, 20, 0), datetime(2026, 9, 2, 7, 0)),    # night shift spills into the next day
        (datetime(2026, 9, 2, 3, 0),  datetime(2026, 9, 2, 7, 0)),
    ])
    def test_run_shift_end(self, accepted, expected_end):
        assert PTW.RunCycle().setAll(running_cycle(accepted)).runShiftEnd() == expected_end

    def test_run_shift_end_none_when_not_accepted(self):
        assert PTW.RunCycle(run_pa='u').runShiftEnd() is None
        assert PTW.RunCycle(run_ia_action=NO, run_ia_timestamp=ts(T0)).runShiftEnd() is None

    def test_shift_expiry_only_while_running(self):
        ptw = ptw_with(running_cycle(T0))
        assert ptw.isRunCycleShiftExpired(now=T0 + timedelta(hours=5)) is False
        assert ptw.isRunCycleShiftExpired(now=datetime(2026, 9, 1, 19, 0)) is True
        # a pending hold request stops the nag on its own
        cyc = running_cycle(T0)
        cyc.update(stop_pa='u', stop_pa_request=HOLD)
        assert ptw_with(cyc).isRunCycleShiftExpired(now=datetime(2026, 9, 2)) is False

    def test_running_status_display(self):
        assert ptw_with(running_cycle(T0)).runningStatusDisplay() == 'Running 08:00 - 19:00'
        assert ptw_with().runningStatusDisplay() == str(R.NOT_RUNNING)
        assert make_ptw().runningStatusDisplay() == str(PTW.ApprovalStatus.UNDER_REVIEW)


class TestValidityWindow:
    def test_expiry_counts_14_shifts_from_the_next_shift_start(self):
        ptw = approved_ptw(approved_at=datetime(2026, 9, 1, 10, 0))
        # next shift after 10:00 starts 19:00; 14 x 12h = 7 days
        assert ptw.validityExpiry() == datetime(2026, 9, 8, 19, 0)
        assert ptw.isValidityExpired(now=datetime(2026, 9, 8, 18, 59)) is False
        assert ptw.isValidityExpired(now=datetime(2026, 9, 8, 19, 0)) is True

    def test_night_approval(self):
        ptw = approved_ptw(approved_at=datetime(2026, 9, 1, 23, 0))
        assert ptw.validityExpiry() == datetime(2026, 9, 9, 7, 0)

    def test_close_alarm_states(self):
        late = datetime(2026, 12, 1)
        assert approved_ptw(approved_at=APPROVED_AT).needsCloseAlarm(now=late) is True
        assert ptw_with(running_cycle(T0)).needsCloseAlarm(now=late) is True
        held = running_cycle(T0); held.update(stop_pa='u', stop_pa_request=HOLD, stop_ia='i', stop_ia_action=OK)
        assert ptw_with(held).needsCloseAlarm(now=late) is True
        pending_hold = running_cycle(T0); pending_hold.update(stop_pa='u', stop_pa_request=HOLD)
        assert ptw_with(pending_hold).needsCloseAlarm(now=late) is False
        pending_close = running_cycle(T0); pending_close.update(stop_pa='u', stop_pa_request=CLOSE)
        assert ptw_with(pending_close).needsCloseAlarm(now=late) is False
        closed = running_cycle(T0); closed.update(stop_pa='u', stop_pa_request=CLOSE, stop_ia='i', stop_ia_action=OK)
        assert ptw_with(closed).needsCloseAlarm(now=late) is False
        assert approved_ptw(approved_at=APPROVED_AT).needsCloseAlarm(now=APPROVED_AT + timedelta(days=1)) is False
        assert make_ptw().needsCloseAlarm(now=late) is False
