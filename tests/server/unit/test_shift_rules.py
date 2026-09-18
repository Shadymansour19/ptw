"""Shift arithmetic: the 07:00/19:00 boundaries and which shift a gas-test reading counts for."""

from datetime import datetime

import pytest

from models.PTW import PTW

D = datetime(2026, 9, 10)  # any date; only the time of day matters


@pytest.mark.parametrize("now, expected_start", [
    (D.replace(hour=7, minute=0),            D.replace(hour=7)),
    (D.replace(hour=7, minute=0, second=1),  D.replace(hour=7)),
    (D.replace(hour=12),                     D.replace(hour=7)),
    (D.replace(hour=18, minute=59, second=59), D.replace(hour=7)),
    (D.replace(hour=19),                     D.replace(hour=19)),
    (D.replace(hour=23, minute=59),          D.replace(hour=19)),
    (D.replace(hour=0, minute=30),           D.replace(hour=19) - __import__('datetime').timedelta(days=1)),
    (D.replace(hour=6, minute=59, second=59), D.replace(hour=19) - __import__('datetime').timedelta(days=1)),
])
def test_shift_start(now, expected_start):
    assert PTW.shiftStart(now) == expected_start


def test_shift_end_is_next_shift_start():
    for hour in range(24):
        now = D.replace(hour=hour)
        end = PTW.shiftEnd(now)
        assert end == PTW.shiftStart(now) + __import__('datetime').timedelta(hours=12)
        assert end.hour in PTW.SHIFT_START_HOURS
        assert end > now


@pytest.mark.parametrize("now, expected_shift", [
    # deep inside the day shift: credited to the day shift in progress
    (D.replace(hour=12),               D.replace(hour=7)),
    # last second before the 1-hour window opens: still the shift in progress
    (D.replace(hour=17, minute=59, second=59), D.replace(hour=7)),
    # window open: credited to the upcoming night shift
    (D.replace(hour=18),               D.replace(hour=19)),
    (D.replace(hour=18, minute=45),    D.replace(hour=19)),
    # just after the night shift began: that night shift
    (D.replace(hour=19, minute=5),     D.replace(hour=19)),
    # early morning inside the night shift, before the window: the night shift that began yesterday
    (D.replace(hour=5, minute=59),     D.replace(hour=19) - __import__('datetime').timedelta(days=1)),
    # window before the 07:00 day shift
    (D.replace(hour=6, minute=15),     D.replace(hour=7)),
])
def test_gas_test_target_shift(now, expected_shift):
    assert PTW.gasTestTargetShift(now) == expected_shift


def test_gas_test_window_constant_is_one_hour():
    # The 18:00 boundary above depends on this; make a change to it deliberate.
    assert PTW.INITIAL_GAS_TEST_WINDOW_HOURS == 1
    assert PTW.SHIFT_DURATION_HOURS == 12
    assert PTW.SHIFT_START_HOURS == (7, 19)
