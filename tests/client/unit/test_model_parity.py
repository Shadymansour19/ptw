"""client/models must stay in lock-step with server/models: same vocabulary, same derived state.

The two PTW.py files are maintained by hand as copies ("kept in sync with the equivalent
server/models/PTW.py"). These tests feed identical data to both and compare everything the
UI or the API decides from it. A failure here means one side was edited without the other.
"""

from datetime import datetime, timedelta

import pytest

import models.PTW as cPTWmod
import models.Isolation as cIsomod
import models.User as cUsermod
from server_models import load
from ptw_factory import ptw_payload, full_chain, running_cycle, gas_test, approval, COORD, ISSUING, HSE, EX_DEPARTMENTS

S = load()
cPTW, sPTW = cPTWmod.PTW, S.PTW.PTW
cIC, sIC = cIsomod.IC, S.Isolation.IC

T0 = datetime(2026, 9, 1, 8, 0)
APPROVED_AT = datetime(2026, 8, 31, 10, 0)
HOLD = 'Hold'
CLOSE = 'Close'
OK = 'Approved'
NO = 'Rejected'


def held_cycle():
    c = running_cycle(T0)
    c.update(stop_pa='u', stop_pa_request=HOLD, stop_ia='i', stop_ia_action=OK, held_ics=['4'])
    return c


def chain(type, when=APPROVED_AT):
    return full_chain(type, start=when - timedelta(minutes=10))


PTW_FIXTURES = {
    'fresh cold work': ptw_payload(),
    'coordinator approved': ptw_payload(approvals=[approval(*COORD)]),
    'issuing stage (in meeting)': ptw_payload(approvals=[approval(*COORD), approval(*HSE)]),
    'returned': ptw_payload(approvals=[approval(*COORD, action='Returned')]),
    'approved idle': ptw_payload(approvals=chain('Cold')),
    'hot work fully approved': ptw_payload('Hot', approvals=chain('Hot')),
    'hot work missing dfgm': ptw_payload('Hot', approvals=chain('Hot')[:-1]),
    'excavation partial': ptw_payload('Excavation', approvals=[approval(*COORD)] + [approval('User', d) for d in EX_DEPARTMENTS[:3]]),
    'run requested': ptw_payload(approvals=chain('Cold'), run_cycles=[dict(run_pa='u', run_pa_timestamp='01/09/2026 08:00:00')]),
    'running': ptw_payload(approvals=chain('Cold'), run_cycles=[running_cycle(T0)]),
    'held': ptw_payload(approvals=chain('Cold'), run_cycles=[held_cycle()]),
    'rejected resume': ptw_payload(approvals=chain('Cold'), run_cycles=[held_cycle(), dict(run_pa='u', run_ia_action=NO)]),
    'closed never run': ptw_payload(approvals=chain('Cold'), run_cycles=[dict(stop_pa='u', stop_pa_request=CLOSE, stop_ia='i', stop_ia_action=OK, stop_ia_timestamp='01/09/2026 09:00:00')]),
    'spark needs gas test': ptw_payload('Spark', hazards=['Electrical / Mechanical Spark'], controls=['Initial Gas Test', 'Continuous Gas Test'],
                                        approvals=chain('Spark', when=datetime.now() - timedelta(hours=1))),
    'spark with reading': ptw_payload('Spark', hazards=['Electrical / Mechanical Spark'], controls=['Initial Gas Test', 'Continuous Gas Test'],
                                      approvals=chain('Spark', when=datetime.now() - timedelta(hours=1)),
                                      gas_tests=[gas_test(cPTW.gasTestTargetShift())]),
    'invalid: power tools on cold': ptw_payload(tools=['Power Tools']),
    'invalid: msds attachment': ptw_payload(hazards=['Hazardous Substance'], controls=['MSDS']),
    'expired validity': ptw_payload(approvals=chain('Cold', when=datetime(2025, 1, 1))),
}


def derived(P, data):
    p = P(data)
    now = datetime(2026, 9, 1, 12, 0)
    return {
        'approval_status': str(p.approval_status),
        'running_status': str(p.running_status),
        'pending': [(str(a.role), str(a.department) if a.department else None) for a in p.pendingApprovers()],
        'stages': [[(str(a.role), str(a.department) if a.department else None) for a in st] for st in p.requiredApprovers()],
        'validate': p.validate(),
        'required_attachs': p.requiredAttachs(),
        'docs': p.requiredDocsToPrint(),
        'requires_gas_test': p.requiresInitialGasTest(),
        'needs_gas_test_now': p.needsGasTestNow(),
        'can_link_ic': p.canLinkIC(),
        'performing': p.getPerforming(),
        'issuing': p.getIssuing(),
        'held_ics': p.getHeldICs(),
        'status_display': p.runningStatusDisplay(),
        'validity_expiry': p.validityExpiry(),
        'validity_expired': p.isValidityExpired(now),
        'shift_expired': p.isRunCycleShiftExpired(now),
        'close_alarm': p.needsCloseAlarm(now),
        'my_status_issuing': str(p.getApprovalStatus('Issuing', 'Prod')) if p.getApprovalStatus('Issuing', 'Prod') is not None else None,
        'my_status_mech_user': str(p.getApprovalStatus('User', 'Mech')) if p.getApprovalStatus('User', 'Mech') is not None else None,
    }


@pytest.mark.parametrize("name", list(PTW_FIXTURES), ids=list(PTW_FIXTURES))
def test_ptw_derived_state_matches(name):
    data = PTW_FIXTURES[name]
    assert derived(cPTW, data) == derived(sPTW, data)


def test_ptw_json_round_trip_across_trees():
    """A server-serialized PTW must reconstruct identically on the client and vice versa."""
    for data in PTW_FIXTURES.values():
        as_server_json = S.utils.objToDict(sPTW(data))
        as_server_json.pop('request_date')
        from_server = cPTW(as_server_json)
        assert (str(from_server.approval_status), str(from_server.running_status)) == \
               (str(sPTW(data).approval_status), str(sPTW(data).running_status))


def _enum_values(mod_ptw, name):
    return [(m.name, str(m.value)) for m in getattr(mod_ptw, name)]


@pytest.mark.parametrize("enum_name", ['Types', 'AreaClasses', 'Locations', 'ApprovalActions', 'ApprovalStatus', 'RunningStatus'])
def test_ptw_enums_match(enum_name):
    assert _enum_values(cPTW, enum_name) == _enum_values(sPTW, enum_name)


def test_run_cycle_and_gas_test_enums_and_constants_match():
    assert [(m.name, m.value) for m in cPTW.RunCycle.Actions] == [(m.name, m.value) for m in sPTW.RunCycle.Actions]
    assert [(m.name, m.value) for m in cPTW.RunCycle.StopTypes] == [(m.name, m.value) for m in sPTW.RunCycle.StopTypes]
    for const in ('TIMESTAMP_FORMAT', 'SHIFT_START_HOURS', 'SHIFT_DURATION_HOURS', 'VALIDITY_SHIFTS', 'INITIAL_GAS_TEST_WINDOW_HOURS', 'GAS_TEST_TYPES'):
        assert getattr(cPTW, const) == getattr(sPTW, const), const


def _checkbox_table(P, attr):
    out = {}
    for title, cb in getattr(P, attr).items():
        out[title] = (
            cb.title,
            tuple((str(r.type), r.description) for r in cb.requirements),
            tuple(cb.isRequired(t) for t in P.Types),
            tuple(cb.isRestricted(t) for t in P.Types),
        )
    return out


@pytest.mark.parametrize("table", ['ALL_TOOLS', 'ALL_HAZARDS', 'ALL_CONTROLS'])
def test_checkbox_tables_match(table):
    assert _checkbox_table(cPTW, table) == _checkbox_table(sPTW, table)


def test_user_enums_match():
    assert [(m.name, m.value) for m in cUsermod.UserRoles] == [(m.name, m.value) for m in S.User.UserRoles]
    assert [(m.name, m.value) for m in cUsermod.UserDepartments] == [(m.name, m.value) for m in S.User.UserDepartments]


def test_isolation_enums_match():
    assert [(m.name, m.value) for m in cIsomod.Isolation.Types] == [(m.name, m.value) for m in S.Isolation.Isolation.Types]
    for enum_name in ('Types', 'Status', 'ApprovalActions'):
        assert [(m.name, m.value) for m in getattr(cIC, enum_name)] == [(m.name, m.value) for m in getattr(sIC, enum_name)], enum_name


IC_FIXTURES = {
    'fresh': {},
    'approved': {'approvals': [dict(action=OK, username='i', role='Issuing', department='Prod')]},
    'psic partial': {'is_psic': True, 'approvals': [dict(action=OK, username='i', role='Issuing', department='Prod'), dict(action=OK, username='c', role='Coordinator', department='Prod')]},
    'isolate confirming': {'isolate_requestor': 'u'},
    'pending': {'isolate_requestor': 'u', 'isolate_issuing_action': OK},
    'active': {'isolate_isolator': 'iso'},
    'deisolate confirming': {'isolate_isolator': 'iso', 'deisolate_requestor': 'u'},
    'closing': {'isolate_isolator': 'iso', 'deisolate_requestor': 'u', 'deisolate_issuing_action': OK},
    'sanctioned': {'isolate_isolator': 'iso', 'sanction_isolator': 'iso'},
    'closed': {'deisolate_isolator': 'iso'},
}


def ic_derived(ICcls, data):
    ic = ICcls(dict(reason='r', long_term_reason='', **data))
    return {
        'status': str(ic.getStatus()),
        'stages': [[str(a.role) for a in st] for st in ic.requiredApprovers()],
        'pending': [str(a.role) for a in ic.pendingApprovers()],
        'winding_down': ic.isWindingDown(),
        'issuing_view': str(ic.getApprovalStatus('Issuing', 'Prod')) if ic.getApprovalStatus('Issuing', 'Prod') is not None else None,
    }


@pytest.mark.parametrize("name", list(IC_FIXTURES), ids=list(IC_FIXTURES))
def test_ic_derived_state_matches(name):
    assert ic_derived(cIC, IC_FIXTURES[name]) == ic_derived(sIC, IC_FIXTURES[name])


def test_ic_ptw_link_rules_match():
    approved = ptw_payload(approvals=chain('Cold'))
    for fields in IC_FIXTURES.values():
        for ptw_data in (approved, ptw_payload(), ptw_payload(approvals=chain('Cold'), run_cycles=[held_cycle()])):
            c = cIC(dict(reason='r', long_term_reason='', **fields))
            s = sIC(dict(reason='r', long_term_reason='', **fields))
            assert c.canLinkPTW(cPTW(ptw_data)) == s.canLinkPTW(sPTW(ptw_data))
            assert c.canUnlinkPTW(cPTW(ptw_data)) == s.canUnlinkPTW(sPTW(ptw_data))
