"""Login, Basic Auth resolution, guests, inactive accounts."""

from conftest import auth, GUEST, PASSWORD


def test_login_ok(client):
    r = client.post('/login', headers=auth('coord'))
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['user']['username'] == 'coord'
    assert body['user']['role'] == 'Coordinator'
    assert 'password' not in body['user'] or body['user']['password'] != PASSWORD


def test_login_wrong_password(client):
    r = client.post('/login', headers=auth('coord', 'nope'))
    assert r.status_code == 401
    assert r.get_json()['success'] is False


def test_login_unknown_user(client):
    assert client.post('/login', headers=auth('nobody', 'x')).status_code == 401


def test_login_without_credentials(client):
    assert client.post('/login').status_code in (400, 401)


def test_inactive_account_is_rejected_at_login_and_on_every_request(client):
    assert client.post('/login', headers=auth('inactive')).status_code == 403
    assert client.get('/ptws', headers=auth('inactive')).status_code == 401


def test_guest_passes_with_no_password_and_unknown_username(client):
    r = client.get('/ptws', headers=auth(GUEST, ''))
    assert r.status_code == 200


def test_guest_cannot_shadow_a_real_account(client):
    # a real username with an empty password is NOT a guest
    assert client.get('/ptws', headers=auth('coord', '')).status_code == 401
    # nor can a made-up name with a password sneak through
    assert client.get('/ptws', headers=auth(GUEST, 'anything')).status_code == 401


def test_no_auth_header(client):
    assert client.get('/ptws').status_code == 401
    assert client.get('/events').status_code == 401


def test_events_stream_requires_auth_only(client):
    # We don't consume the stream (it never ends); just check the gate is the same primitive.
    assert client.get('/events', headers=auth('nobody', 'x')).status_code == 401
