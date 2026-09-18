"""Builders for PTW/IC fixtures shared by the server unit and API tests.

Everything here goes through the real model constructors with plain dicts, the same
shape a `ptws` row or a JSON payload has, so a fixture never bypasses `setAll()` /
`__updateStatus()`.
"""

from datetime import datetime, timedelta

from models.PTW import PTW
from models.Isolation import IC
from models.User import UserRoles, UserDepartments

TS = PTW.TIMESTAMP_FORMAT


def ts(dt: datetime) -> str:
    """Format a datetime the way the app stores every timestamp."""
    return dt.strftime(TS)


def ptw_payload(type=PTW.Types.CW, **over) -> dict:
    """A minimal, valid PTW dict (passes `PTW.validate()` for a Cold Work permit)."""
    data = dict(
        type=str(type),
        requestor='user_turbo',
        department=str(UserDepartments.TURBO),
        location=str(PTW.Locations.PHVII),
        area_class=str(PTW.AreaClasses.HAZ),
        equipment='P-101',
        description='Replace pump gasket',
        mos='1. Isolate\n2. Drain\n3. Replace',
        tools=['Hand Tools'],
        hazards=[],
        controls=[],
        fast_track=False,
    )
    data.update(over)
    return data


def make_ptw(type=PTW.Types.CW, **over) -> PTW:
    return PTW(ptw_payload(type, **over))


def approval(role, department=None, action=PTW.ApprovalActions.APPROVED, username=None,
             when: datetime = None, comment=None) -> dict:
    """An approval record dict with the server-side role/department snapshot filled in."""
    return dict(
        action=str(action),
        username=username or f'{str(role).lower()}_{(department or "x").lower()}',
        timestamp=ts(when or datetime(2026, 9, 1, 10, 0, 0)),
        comment=comment,
        role=str(role),
        department=str(department) if department is not None else None,
    )


# The approval chain in the order the app expects it to be walked.
COORD = (UserRoles.COORDINATOR, UserDepartments.PROD)
ISSUING = (UserRoles.ISSUING, UserDepartments.PROD)
HSE = (UserRoles.HSE_ENGINEER, UserDepartments.HSE)
PGM = (UserRoles.PGM, UserDepartments.PROD)
DFGM = (UserRoles.DFGM, None)

EX_DEPARTMENTS = [
    UserDepartments.MECH, UserDepartments.ELEC, UserDepartments.INST, UserDepartments.TELECOM,
    UserDepartments.TURBO, UserDepartments.PROJECT, UserDepartments.CVL, UserDepartments.CATHODIC_PROTECTION,
]


def full_chain(type=PTW.Types.CW, start: datetime = None) -> list[dict]:
    """Every approval needed to fully approve a permit of `type`, one minute apart."""
    start = start or datetime(2026, 9, 1, 10, 0, 0)
    slots = [COORD]
    if type == PTW.Types.EX:
        slots += [(UserRoles.USER, d) for d in EX_DEPARTMENTS]
    slots += [ISSUING, HSE]
    if type in (PTW.Types.HT, PTW.Types.CS):
        slots += [PGM, DFGM]
    return [approval(role, dept, when=start + timedelta(minutes=i)) for i, (role, dept) in enumerate(slots)]


def approved_ptw(type=PTW.Types.CW, approved_at: datetime = None, **over) -> PTW:
    """A fully approved permit whose last approval landed at `approved_at`."""
    approved_at = approved_at or datetime(2026, 9, 1, 10, 0, 0)
    chain = full_chain(type, start=approved_at - timedelta(minutes=10))
    chain[-1]['timestamp'] = ts(approved_at)
    return make_ptw(type, approvals=chain, **over)


def run_cycle(**fields) -> dict:
    """A RunCycle dict; only the given fields are set."""
    return dict(fields)


def running_cycle(accepted_at: datetime, pa='user_turbo', ia='issuing_prod') -> dict:
    return run_cycle(
        run_pa=pa, run_pa_timestamp=ts(accepted_at - timedelta(minutes=5)),
        run_ia=ia, run_ia_action=str(PTW.RunCycle.Actions.APPROVED), run_ia_timestamp=ts(accepted_at),
    )


def gas_test(shift_start: datetime, taken_at: datetime = None, username='gas_prod') -> dict:
    taken_at = taken_at or (shift_start - timedelta(minutes=20))
    return dict(
        username=username, timestamp=ts(taken_at), shift=ts(shift_start),
        readings=[{'gas': g, 'percentage': 0} for g in PTW.GAS_TEST_TYPES], comment=None,
    )


def make_ic(**over) -> IC:
    data = dict(
        type=str(IC.Types.MECHANICAL),
        requestor_department=str(UserDepartments.TURBO),
        execution_department=str(UserDepartments.PROD),
        requestor='user_turbo',
        location=str(PTW.Locations.PHVII),
        equipment='P-101',
        reason='Gasket replacement',
        items=[],
        long_term_reason='',
        psic_system_description='', psic_isolation_method='', psic_control_measures='',
    )
    data.update(over)
    return IC(data)


def ic_approval(role, department=UserDepartments.PROD, action=IC.ApprovalActions.APPROVED) -> dict:
    return dict(action=str(action), username=f'{str(role).lower()}', timestamp=ts(datetime(2026, 9, 1, 9, 0, 0)),
                comment=None, role=str(role), department=str(department) if department else None)
