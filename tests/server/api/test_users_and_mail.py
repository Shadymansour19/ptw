"""Admin user management and the invitation email (recorded, never sent)."""

import threading
import time

import pytest

from conftest import auth, PASSWORD
import routes.users as users_routes


@pytest.fixture
def mail_sent(sent_mail, monkeypatch):
    """The invitation goes out on a daemon thread; wrap it so tests can wait for it."""
    done = threading.Event()
    original = users_routes._sendInvitationEmail

    def wrapped(*args, **kwargs):
        try:
            original(*args, **kwargs)
        finally:
            done.set()

    monkeypatch.setattr(users_routes, '_sendInvitationEmail', wrapped)
    yield sent_mail, done


def test_admin_creates_user_and_invitation_is_built(client, server, mail_sent):
    box, done = mail_sent
    body = {'username': 'newbie', 'password': 'Secret1', 'name': 'New Person', 'role': 'User',
            'department': 'Mech', 'email': 'newbie@example.invalid', 'must_change_password': False}
    r = client.post('/users', json=body, headers=auth('admin'))
    assert r.status_code == 200 and r.get_json()['error'] is None
    assert done.wait(5), "invitation email thread did not finish"
    assert len(box) == 1
    msg = box[0]
    assert msg.recipients == ['newbie@example.invalid']
    assert 'newbie' in msg.html and 'Secret1' in msg.html
    assert msg.subject == 'PTW Invitation'

    # the account works and is forced to change its password regardless of the payload
    r = client.post('/login', headers=auth('newbie', 'Secret1'))
    assert r.status_code == 200
    assert r.get_json()['user']['must_change_password'] is True
    assert 'newbie' in server.globalData.allUsers
    # cleanup for the session-scoped user table
    server.userDB.deleteUser(server.userDB.getSecuredUser('newbie'))


def test_no_email_means_no_invitation(client, server, sent_mail):
    body = {'username': 'quiet', 'password': 'x', 'name': 'Quiet', 'role': 'User', 'department': 'Mech', 'email': ''}
    assert client.post('/users', json=body, headers=auth('admin')).status_code == 200
    time.sleep(0.2)
    assert sent_mail == []
    server.userDB.deleteUser(server.userDB.getSecuredUser('quiet'))


@pytest.mark.xfail(strict=True, reason=(
    "Known bug: UsersDb.addUserFromDict returns the Exception *object*, and routes/users.py "
    "puts it straight into jsonify(), which raises 'Object of type Exception is not JSON "
    "serializable' -> the admin gets a 400 with that message instead of the documented 200 + "
    "DB error string. Fix by returning str(e) (or jsonify str(err)); this test then passes and "
    "strict=True will flag the marker for removal."))
def test_duplicate_username_is_reported_not_raised(client):
    body = {'username': 'coord', 'password': 'x', 'name': 'Dup', 'role': 'User', 'department': 'Mech', 'email': ''}
    r = client.post('/users', json=body, headers=auth('admin'))
    assert r.status_code == 200
    assert 'Error adding data' in r.get_json()['error']          # DB layer's error string


def test_user_listing_excludes_password_hashes(client):
    r = client.get('/users', headers=auth('coord'))
    assert r.status_code == 200
    users = r.get_json()['all-users']
    coord = users['coord']
    assert 'password' not in coord
    assert coord['role'] == 'Coordinator'
