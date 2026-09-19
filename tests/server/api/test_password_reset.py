"""Forgot-password flow: code by email, verification, expiry, and the new password taking effect."""

import re

import pytest

import routes.auth as auth_routes
from conftest import auth


@pytest.fixture(autouse=True)
def clear_codes():
    auth_routes.resetCodes.clear()
    yield
    auth_routes.resetCodes.clear()


@pytest.fixture
def temp_user(client, server):
    body = {'username': 'forgetful', 'password': 'Old1', 'name': 'Forgetful', 'role': 'User', 'department': 'Mech',
            'email': 'forgetful@example.invalid'}
    assert client.post('/users', json=body, headers=auth('admin')).status_code == 200
    yield 'forgetful'
    server.userDB.deleteUser(server.userDB.getSecuredUser('forgetful'))
    server.globalData.allUsers.pop('forgetful', None)


def request_code(client, username):
    return client.post('/reset-password-request', json={'username': username})


def reset(client, username, code, new_password='New2'):
    return client.post('/reset-password', json={'username': username, 'new-password': new_password, 'verification-code': code})


def test_happy_path(client, sent_mail, temp_user):
    r = request_code(client, temp_user)
    assert r.status_code == 200, r.get_json()
    invitation, code_mail = sent_mail                       # the invitation from user creation, then the code
    assert code_mail.recipients == ['forgetful@example.invalid']
    assert code_mail.subject == 'PTW Reset Password Verification Code'
    code, _ = auth_routes.resetCodes[temp_user]
    assert re.fullmatch(r'\d{6}', code) and code in code_mail.html

    assert reset(client, temp_user, 'wrong!').status_code == 400
    assert temp_user in auth_routes.resetCodes             # a wrong guess doesn't burn the code
    r = reset(client, temp_user, code)
    assert r.status_code == 200
    assert temp_user not in auth_routes.resetCodes         # ...but success does
    assert client.post('/login', headers=auth(temp_user, 'Old1')).status_code == 401
    assert client.post('/login', headers=auth(temp_user, 'New2')).status_code == 200
    assert reset(client, temp_user, code).status_code == 404   # no second use


def test_expired_code(client, temp_user):
    request_code(client, temp_user)
    code, ts = auth_routes.resetCodes[temp_user]
    auth_routes.resetCodes[temp_user] = (code, ts - auth_routes._RESET_CODE_TTL - 1)
    r = reset(client, temp_user, code)
    assert r.status_code == 400 and 'expired' in r.get_json()['error']
    assert temp_user not in auth_routes.resetCodes
    assert client.post('/login', headers=auth(temp_user, 'Old1')).status_code == 200


def test_requests_need_a_known_user_with_an_email(client, sent_mail):
    assert request_code(client, '').status_code == 401
    assert request_code(client, 'nobody').status_code == 400
    assert len(sent_mail) == 0


def test_mail_failure_is_a_500_and_leaves_no_code(client, server, temp_user, monkeypatch):
    def boom(msg):
        raise RuntimeError('smtp down')
    monkeypatch.setattr(server.core.mail, 'send', boom)
    r = request_code(client, temp_user)
    assert r.status_code == 500 and 'Failed to send' in r.get_json()['error']
    assert temp_user not in auth_routes.resetCodes


def test_reset_validation(client, temp_user):
    assert reset(client, temp_user, '').status_code == 400
    assert reset(client, temp_user, '123456', new_password='').status_code == 400
    assert reset(client, temp_user, '123456').status_code == 404      # nothing requested


def test_a_new_request_replaces_the_old_code(client, temp_user):
    request_code(client, temp_user)
    first, _ = auth_routes.resetCodes[temp_user]
    request_code(client, temp_user)
    second, _ = auth_routes.resetCodes[temp_user]
    if first != second:                                            # 1-in-a-million collision otherwise
        assert reset(client, temp_user, first).status_code == 400
    assert reset(client, temp_user, second).status_code == 200
