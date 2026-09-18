"""objToDict / dictToObj and the model <-> dict round trips the DB layer relies on."""

from types import SimpleNamespace

from utils import objToDict, dictToObj
from models.PTW import PTW
from ptw_factory import approved_ptw, running_cycle, gas_test
from datetime import datetime


def test_scalars_and_containers_pass_through():
    assert objToDict({'a': [1, (2, 3), {4}], 'b': None, 'c': 'x'}) == {'a': [1, (2, 3), {4}], 'b': None, 'c': 'x'}
    ns = dictToObj({'a': {'b': [1, {'c': 2}]}})
    assert isinstance(ns, SimpleNamespace) and ns.a.b[1].c == 2


def test_objects_become_dicts():
    class Thing:
        def __init__(self):
            self.x = 1
            self.child = SimpleNamespace(y=2)
    assert objToDict(Thing()) == {'x': 1, 'child': {'y': 2}}


def test_ptw_round_trip_preserves_derived_state():
    src = approved_ptw(run_cycles=[running_cycle(datetime(2026, 9, 1, 8, 0))], gas_tests=[gas_test(datetime(2026, 9, 1, 7, 0))])
    data = objToDict(src)
    assert isinstance(data['run_cycles'][0], dict) and isinstance(data['approvals'][0], dict)
    # as the DB layer does: dict -> namespace -> PTW
    clone = PTW().setAll(namespace=dictToObj(data))
    assert clone.approval_status == PTW.ApprovalStatus.APPROVED
    assert clone.running_status == PTW.RunningStatus.RUNNING
    assert clone.gas_tests[0].shift == src.gas_tests[0].shift
    assert isinstance(clone.run_cycles[0], PTW.RunCycle)
    # and as the JSON route does: dict -> PTW
    assert PTW(data).running_status == PTW.RunningStatus.RUNNING


def test_setall_ignores_unknown_keys():
    ptw = PTW().setAll({'no_such_field': 1, 'equipment': 'E-1'})
    assert ptw.equipment == 'E-1' and not hasattr(ptw, 'no_such_field')
