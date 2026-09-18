"""Initial gas test requirements per shift."""

from datetime import datetime, timedelta

from models.PTW import PTW
from ptw_factory import make_ptw, approved_ptw, gas_test, running_cycle, ts

DAY = datetime(2026, 9, 1, 7, 0)
NIGHT = datetime(2026, 9, 1, 19, 0)
CONTROLS = ['Initial Gas Test', 'Continuous Gas Test']
HAZ = ['Electrical / Mechanical Spark']


def test_requires_initial_gas_test_from_controls():
    assert make_ptw(controls=CONTROLS).requiresInitialGasTest() is True
    assert make_ptw(controls=['MSDS']).requiresInitialGasTest() is False
    assert make_ptw(controls=None).requiresInitialGasTest() is False


def test_not_required_means_always_acceptable():
    assert make_ptw().hasAcceptableGasTestForShift(DAY) is True
    assert make_ptw().needsGasTestNow() is False


def test_reading_is_credited_to_its_shift_only():
    ptw = make_ptw(PTW.Types.SP, hazards=HAZ, controls=CONTROLS, gas_tests=[gas_test(DAY)])
    assert ptw.hasAcceptableGasTestForShift(DAY) is True
    assert ptw.hasAcceptableGasTestForShift(NIGHT) is False
    assert ptw.gasTestForShift(DAY).username == 'gas_prod'
    assert ptw.gasTestForShift(NIGHT) is None


def test_most_recent_reading_for_a_shift_wins():
    first = gas_test(DAY, taken_at=DAY - timedelta(minutes=40), username='a')
    second = gas_test(DAY, taken_at=DAY - timedelta(minutes=10), username='b')
    ptw = make_ptw(controls=CONTROLS, gas_tests=[first, second])
    assert ptw.gasTestForShift(DAY).username == 'b'


def test_late_flag():
    assert PTW.GasTest().setAll(gas_test(DAY, taken_at=DAY + timedelta(minutes=1))).isLate() is True
    assert PTW.GasTest().setAll(gas_test(DAY, taken_at=DAY - timedelta(minutes=1))).isLate() is False
    assert PTW.GasTest().isLate() is False


def test_needs_gas_test_now_is_scoped_to_approved_open_ptws(monkeypatch):
    # approved, required, no reading for the shift a reading right now would count toward
    ptw = approved_ptw(PTW.Types.SP, approved_at=datetime(2026, 9, 1, 8, 0), hazards=HAZ, controls=CONTROLS)
    assert ptw.needsGasTestNow() is True
    # a reading for the current target shift satisfies it
    ptw.gas_tests = [PTW.GasTest().setAll(gas_test(PTW.gasTestTargetShift()))]
    assert ptw.needsGasTestNow() is False
    # not approved: never nags
    assert make_ptw(PTW.Types.SP, hazards=HAZ, controls=CONTROLS).needsGasTestNow() is False
    # closed: never nags again
    closed = running_cycle(datetime(2026, 9, 1, 8, 0))
    closed.update(stop_pa='u', stop_pa_request=str(PTW.RunCycle.StopTypes.CLOSE), stop_ia='i',
                  stop_ia_action=str(PTW.RunCycle.Actions.APPROVED))
    assert approved_ptw(PTW.Types.SP, approved_at=datetime(2026, 9, 1, 7, 30), hazards=HAZ, controls=CONTROLS,
                        run_cycles=[closed]).needsGasTestNow() is False


def test_gas_test_round_trips_through_setall():
    src = gas_test(DAY)
    gt = PTW.GasTest().setAll(src)
    assert gt.shift == ts(DAY) and len(gt.readings) == len(PTW.GAS_TEST_TYPES)
    assert gt.isAcceptable() is True    # placeholder criteria today; a real threshold must update this test
