"""Thin request helpers so lifecycle tests read like the workflow they exercise."""

from datetime import datetime

from models.PTW import PTW
from ptw_factory import ptw_payload
from conftest import auth, PASSWORD, EX_USERS

APPROVE = str(PTW.ApprovalActions.APPROVED)
RETURN = str(PTW.ApprovalActions.RETURNED)


def now_ts(when: datetime = None) -> str:
    return (when or datetime.now()).strftime(PTW.TIMESTAMP_FORMAT)


def create_ptw(client, as_user='user_turbo', type=PTW.Types.CW, **over) -> int:
    over.setdefault('requestor', as_user)
    r = client.post('/ptws', json=ptw_payload(type, **over), headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ptw-id']


def approve(client, ptw_id, as_user, action=APPROVE, when: datetime = None, comment=None):
    return client.post('/ptws/approvals', json={
        'ptw-id': ptw_id,
        'approval': {'action': action, 'username': as_user, 'timestamp': now_ts(when), 'comment': comment},
    }, headers=auth(as_user))


def approve_fully(client, ptw_id, type=PTW.Types.CW, when: datetime = None):
    """Walk the whole chain for a permit of `type`, asserting each step is accepted."""
    order = ['coord']
    if type == PTW.Types.EX:
        order += EX_USERS
    order += ['issuing', 'hse']
    if type in (PTW.Types.HT, PTW.Types.CS):
        order += ['pgm', 'dfgm']
    for u in order:
        r = approve(client, ptw_id, u, when=when)
        assert r.status_code == 200, (u, r.get_json())


def run_request(client, ptw_id, as_user='user_turbo', when=None):
    return client.post('/ptws/run-request', json={'ptw-id': ptw_id, 'pa': as_user, 'timestamp': now_ts(when)}, headers=auth(as_user))


def run_response(client, ptw_id, ok=True, as_user='issuing', comment=None, when=None):
    return client.post('/ptws/run', json={'ptw-id': ptw_id, 'ia': as_user, 'timestamp': now_ts(when), 'response': ok, 'comment': comment},
                       headers=auth(as_user))


def hold_request(client, ptw_id, as_user='user_turbo', held_ics=None, comment=None):
    return client.post('/ptws/hold-request', json={'ptw-id': ptw_id, 'pa': as_user, 'timestamp': now_ts(), 'comment': comment,
                                                  'held-ics': held_ics or []}, headers=auth(as_user))


def hold_response(client, ptw_id, ok=True, as_user='issuing'):
    return client.post('/ptws/hold', json={'ptw-id': ptw_id, 'ia': as_user, 'timestamp': now_ts(), 'response': ok}, headers=auth(as_user))


def close_request(client, ptw_id, as_user='user_turbo', comment=None):
    return client.post('/ptws/close-request', json={'ptw-id': ptw_id, 'pa': as_user, 'timestamp': now_ts(), 'comment': comment},
                       headers=auth(as_user))


def close_response(client, ptw_id, ok=True, as_user='issuing'):
    return client.post('/ptws/close', json={'ptw-id': ptw_id, 'ia': as_user, 'timestamp': now_ts(), 'response': ok}, headers=auth(as_user))


def gas_test(client, ptw_ids, as_user='gas', when=None):
    return client.post('/ptws/gas-test', json={
        'ptw-ids': list(ptw_ids), 'timestamp': now_ts(when),
        'readings': [{'gas': g, 'percentage': 0} for g in PTW.GAS_TEST_TYPES],
    }, headers=auth(as_user))


def get_ptw(client, ptw_id, as_user='coord') -> dict:
    r = client.get(f'/ptws/{ptw_id}', headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ptw']


def list_ptws(client, as_user, **body) -> list[dict]:
    r = client.get('/ptws', json=body or None, headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ptws']
