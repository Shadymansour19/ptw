"""User account routes beyond creation: lookup, self-service edits, admin edits, preferences,
activation, deletion - and the privilege boundaries between them."""

import pytest

from conftest import auth, GUEST, PASSWORD


@pytest.fixture
def temp_user(client, server):
    """A throwaway account (session users are shared; never mutate them)."""
    body = {'username': 'tmp_user', 'password': 'Init1', 'name': 'Temp', 'role': 'User', 'department': 'Mech',
            'email': 'tmp@example.invalid', 'must_change_password': False}
    assert client.post('/users', json=body, headers=auth('admin')).status_code == 200
    yield 'tmp_user', 'Init1'
    if server.userDB.isUsernameExists('tmp_user'):
        server.userDB.deleteUser(server.userDB.getSecuredUser('tmp_user'))
    server.globalData.allUsers.pop('tmp_user', None)


def login(client, username, password):
    return client.post('/login', headers=auth(username, password))


class TestLookups:
    def test_get_user_and_usernames_are_open_to_any_authenticated_caller(self, client):
        for who in ('coord', 'user_turbo', GUEST):
            r = client.get('/user', json={'username': 'issuing'}, headers=auth(who))
            assert r.status_code == 200, who
            u = r.get_json()['user']
            assert (u['username'], u['role'], u['department']) == ('issuing', 'Issuing', 'Prod')
            assert 'password' not in u
            r = client.get('/usernames', headers=auth(who))
            assert r.status_code == 200 and {'coord', 'issuing', 'admin'} <= set(r.get_json()['usernames'])
        assert client.get('/user', json={'username': 'x'}).status_code == 401

    def test_unknown_user_lookup_is_a_400(self, client):
        # documented as "400 on lookup failure": the DB layer raises for a missing row
        r = client.get('/user', json={'username': 'nobody'}, headers=auth('coord'))
        assert r.status_code == 400 and 'Error fetching user' in r.get_json()['error']


class TestSelfService:
    def test_user_edits_own_name_email_ext_and_password(self, client, server, temp_user):
        username, pw = temp_user
        body = {'username': username, 'name': 'Renamed', 'email': 'new@example.invalid', 'ext': '1234', 'password': 'Better2'}
        r = client.put('/users', json=body, headers=auth(username, pw))
        assert r.status_code == 200 and r.get_json() == {'success': True, 'user': None}
        assert login(client, username, pw).status_code == 401              # old password gone
        me = login(client, username, 'Better2').get_json()['user']
        assert (me['name'], me['email'], me['ext']) == ('Renamed', 'new@example.invalid', '1234')
        assert server.globalData.allUsers[username].getName() == 'Renamed'   # cache patched

    def test_self_update_cannot_escalate(self, client, server, temp_user):
        username, pw = temp_user
        body = {'username': username, 'role': 'Admin', 'department': 'Prod', 'is_active': False, 'must_change_password': True, 'name': 'Sneaky'}
        r = client.put('/users', json=body, headers=auth(username, pw))
        assert r.status_code == 200
        me = login(client, username, pw).get_json()['user']
        # role/department/is_active untouched; must_change_password stays True (creation forces it,
        # and only a real password change may clear it - not a payload flag)
        assert (me['role'], me['department'], me['is_active'], me['must_change_password']) == ('User', 'Mech', True, True)
        assert me['name'] == 'Sneaky'                                          # the allowed field went through
        assert client.put('/users', json={'username': username, 'must_change_password': False}, headers=auth(username, pw)).status_code == 200
        assert login(client, username, pw).get_json()['user']['must_change_password'] is True

    def test_blank_password_leaves_the_current_one_alone(self, client, temp_user):
        username, pw = temp_user
        assert client.put('/users', json={'username': username, 'password': '', 'name': 'N'}, headers=auth(username, pw)).status_code == 200
        assert login(client, username, pw).status_code == 200

    def test_cannot_edit_someone_else(self, client, temp_user):
        username, pw = temp_user
        assert client.put('/users', json={'username': 'coord', 'name': 'Hijacked'}, headers=auth(username, pw)).status_code == 401
        assert client.get('/user', json={'username': 'coord'}, headers=auth('coord')).get_json()['user']['name'] == 'Coord'

    def test_guest_cannot_edit_anything(self, client):
        assert client.put('/users', json={'username': GUEST, 'name': 'x'}, headers=auth(GUEST)).status_code == 401

    def test_preferences_are_per_user_only(self, client, temp_user):
        username, pw = temp_user
        assert client.patch('/users/theme', json={'username': username, 'theme': 'dark'}, headers=auth(username, pw)).status_code == 200
        assert client.patch('/users/language', json={'username': username, 'language': 'ar'}, headers=auth(username, pw)).status_code == 200
        me = login(client, username, pw).get_json()['user']
        assert (me['theme'], me['language']) == ('dark', 'ar')
        assert client.patch('/users/theme', json={'username': 'coord', 'theme': 'dark'}, headers=auth(username, pw)).status_code == 401
        assert client.patch('/users/language', json={'username': 'coord', 'language': 'ar'}, headers=auth(username, pw)).status_code == 401
        assert client.patch('/users/theme', json={'username': GUEST, 'theme': 'dark'}, headers=auth(GUEST)).status_code == 401
        # None clears the preference
        assert client.patch('/users/theme', json={'username': username, 'theme': None}, headers=auth(username, pw)).status_code == 200
        assert login(client, username, pw).get_json()['user']['theme'] is None


class TestAdmin:
    def test_admin_edits_role_department_and_forces_password_change(self, client, server, temp_user):
        username, pw = temp_user
        body = {'username': username, 'role': 'Isolator', 'department': 'Prod', 'must_change_password': True}
        assert client.put('/users', json=body, headers=auth('admin')).status_code == 200
        me = login(client, username, pw).get_json()['user']
        assert (me['role'], me['department'], me['must_change_password']) == ('Isolator', 'Prod', True)
        assert server.globalData.allUsers[username].getRole() == 'Isolator'
        # the forced flag clears itself when the user sets a password
        assert client.put('/users', json={'username': username, 'password': 'Fresh3'}, headers=auth(username, pw)).status_code == 200
        assert login(client, username, 'Fresh3').get_json()['user']['must_change_password'] is False

    def test_activation(self, client, server, temp_user):
        username, pw = temp_user
        r = client.patch('/users/active', json={'username': username, 'is_active': False}, headers=auth('admin'))
        assert r.status_code == 200
        assert login(client, username, pw).status_code == 403
        assert server.globalData.allUsers[username].getIsActive() is False
        assert client.patch('/users/active', json={'username': username, 'is_active': True}, headers=auth('admin')).status_code == 200
        assert login(client, username, pw).status_code == 200

    def test_activation_guards(self, client):
        r = client.patch('/users/active', json={'username': 'admin', 'is_active': False}, headers=auth('admin'))
        assert r.status_code == 400 and 'your own account' in r.get_json()['error']
        assert client.patch('/users/active', json={'username': 'coord'}, headers=auth('admin')).status_code == 400
        assert client.patch('/users/active', json={'username': 'coord', 'is_active': False}, headers=auth('coord')).status_code == 401
        assert login(client, 'coord', PASSWORD).status_code == 200

    def test_delete(self, client, server, temp_user):
        username, pw = temp_user
        assert client.delete('/users', json={'username': username}, headers=auth('coord')).status_code == 401
        r = client.delete('/users', json={'username': username}, headers=auth('admin'))
        assert r.status_code == 200 and r.get_json() == {'success': True, 'user': None}
        assert login(client, username, pw).status_code == 401
        assert username not in server.globalData.allUsers
        assert client.delete('/users', json={}, headers=auth('admin')).status_code == 400          # missing username

    def test_update_of_unknown_user_is_a_silent_no_op(self, client, server):
        # UPDATE ... WHERE username='ghost' matches nothing and raises nothing; no row is created
        r = client.put('/users', json={'username': 'ghost', 'name': 'x'}, headers=auth('admin'))
        assert r.status_code == 200 and r.get_json()['user'] is None
        assert not server.userDB.isUsernameExists('ghost')
