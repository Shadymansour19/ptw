"""Role gates per endpoint, and department-scoped visibility.

Every row is (method, path, expected status per role). Payloads are deliberately minimal
(empty JSON) so what's under test is the *gate*, not the handler: a role that gets past the
gate returns 400 ("missing required fields"), a role that doesn't returns 401/403.
"""

import pytest

from models.PTW import PTW
from conftest import auth, GUEST, USERS
from api_helpers import create_ptw, approve, approve_fully, list_ptws

ALL_ROLES = list(USERS) + [GUEST]
ALL_ROLES.remove('inactive')


def _hdr(user):
    return auth(GUEST, '') if user == GUEST else auth(user)


def _matrix(allowed, allowed_status=400, denied_status=403, guest_status=None):
    """Expected status per user: `allowed` users get past the gate (400 on empty body)."""
    exp = {}
    for u in ALL_ROLES:
        if u in allowed:
            exp[u] = allowed_status
        elif u == GUEST and guest_status is not None:
            exp[u] = guest_status
        else:
            exp[u] = denied_status
    return exp


NON_GUEST = [u for u in ALL_ROLES if u != GUEST]

CASES = [
    # Issuing-only running-cycle responses
    ('POST', '/ptws/run',          _matrix({'issuing'})),
    ('POST', '/ptws/hold',         _matrix({'issuing'})),
    ('POST', '/ptws/close',        _matrix({'issuing'})),
    # Gas tester only
    ('POST', '/ptws/gas-test',     _matrix({'gas'})),
    # any non-guest
    ('POST', '/ptws/approvals',    _matrix(NON_GUEST, denied_status=401)),
    ('POST', '/ptws/run-request',  _matrix(NON_GUEST, denied_status=401)),
    ('POST', '/ptws/hold-request', _matrix(NON_GUEST, denied_status=401)),
    ('POST', '/ptws/close-request', _matrix(NON_GUEST, denied_status=401)),
    ('POST', '/ptws/archive',      _matrix(NON_GUEST, denied_status=401)),
    ('DELETE', '/ptws',            _matrix(NON_GUEST, allowed_status=200, denied_status=401)),   # delete of a missing id is a no-op 200
    # admin only
    ('GET',  '/logs',              _matrix({'admin'}, allowed_status=200, denied_status=401)),
    ('GET',  '/backups',           _matrix({'admin'}, allowed_status=200, denied_status=401)),
]


@pytest.mark.parametrize("method, path, expected", CASES, ids=[f'{m} {p}' for m, p, _ in CASES])
def test_role_gate(client, method, path, expected):
    got = {}
    for user in ALL_ROLES:
        r = client.open(path, method=method, json={}, headers=_hdr(user))
        got[user] = r.status_code
    mismatches = {u: (got[u], expected[u]) for u in ALL_ROLES if got[u] != expected[u]}
    assert not mismatches, f"(got, expected) per user: {mismatches}"


def test_every_ptw_route_rejects_anonymous(client):
    for method, path, _ in CASES:
        assert client.open(path, method=method, json={}).status_code == 401, (method, path)


class TestDepartmentVisibility:
    def test_users_see_only_their_department(self, client):
        mine = create_ptw(client, 'user_turbo')
        theirs = create_ptw(client, 'user_mech', department='Mech')
        assert {p['id'] for p in list_ptws(client, 'user_turbo')} == {mine}
        assert {p['id'] for p in list_ptws(client, 'user_turbo2')} == {mine}     # same dept, different requestor
        assert {p['id'] for p in list_ptws(client, 'user_mech')} == {theirs}
        assert client.get(f'/ptws/{theirs}', headers=auth('user_turbo')).status_code == 404
        assert client.get(f'/ptws/{mine}', headers=auth('user_turbo')).status_code == 200

    def test_department_filter_is_ignored_for_restricted_roles(self, client):
        create_ptw(client, 'user_mech', department='Mech')
        assert list_ptws(client, 'user_turbo', department='Mech') == []

    def test_approver_roles_see_everything_unless_they_filter(self, client):
        a = create_ptw(client, 'user_turbo')
        b = create_ptw(client, 'user_mech', department='Mech')
        for u in ('coord', 'issuing', 'hse', 'isolator', 'admin', 'pgm'):
            assert {p['id'] for p in list_ptws(client, u)} == {a, b}, u
        assert {p['id'] for p in list_ptws(client, 'coord', department='mech')} == {b}   # case-insensitive
        assert {p['id'] for p in list_ptws(client, 'coord', requestor='USER_TURBO')} == {a}

    def test_guest_is_scoped_to_its_empty_department(self, client):
        create_ptw(client, 'user_turbo')
        assert list_ptws(client, GUEST) == []

    def test_excavation_ptw_is_visible_to_pending_department_approvers(self, client):
        pid = create_ptw(client, 'user_turbo', type=PTW.Types.EX)
        # Mech has a pending slot only once Coordinator has approved (stage order)
        assert client.get(f'/ptws/{pid}', headers=auth('user_mech')).status_code == 200   # pendingApprovers spans later stages too
        approve(client, pid, 'coord')
        assert {p['id'] for p in list_ptws(client, 'user_mech')} == {pid}
        assert client.get(f'/ptws/{pid}', headers=auth('user_it')).status_code == 404       # IT isn't one of the eight
        # once Mech approved, its slot is no longer pending -> no longer visible to Mech
        approve(client, pid, 'user_mech')
        assert list_ptws(client, 'user_mech') == []

    def test_archive_listing_is_department_scoped_for_users(self, client, server):
        pid = create_ptw(client, 'user_turbo')
        other = create_ptw(client, 'user_mech', department='Mech')
        server.ptwDB.archivePTWs([pid, other])
        server.globalData.refresh(server.userDB, server.ptwDB, server.icDB)
        assert {p['id'] for p in client.get('/ptws/archive', headers=auth('user_turbo')).get_json()['ptws']} == {pid}
        assert {p['id'] for p in client.get('/ptws/archive', headers=auth('coord')).get_json()['ptws']} == {pid, other}
        assert list_ptws(client, 'coord') == []      # archived PTWs leave the live listing


class TestUserRoutes:
    def test_only_admin_creates_users(self, client):
        body = {'username': 'newbie', 'password': 'x', 'name': 'New', 'role': 'User', 'department': 'Turbo', 'email': ''}
        for u in ('coord', 'user_turbo', 'issuing', GUEST):
            r = client.post('/users', json=body, headers=_hdr(u))
            assert r.status_code == 401, u
        assert client.get('/users', headers=auth('coord')).status_code == 200
