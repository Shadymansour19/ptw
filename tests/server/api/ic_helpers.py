"""Request helpers for the IC (Isolation Certificate) routes."""

from models.Isolation import IC
from conftest import auth
from api_helpers import now_ts

APPROVE = str(IC.ApprovalActions.APPROVED)
RETURN = str(IC.ApprovalActions.RETURNED)

PSIC_TERMS = {
    'psic_reasons': ['Maintenance'],
    'psic_moc_number': 'MOC-1',
    'psic_system_description': 'ESD loop 12',
    'psic_isolation_method': 'Forced bypass',
    'psic_control_measures': 'Operator on watch',
}


def ic_payload(**over) -> dict:
    data = dict(
        type=str(IC.Types.MECHANICAL),
        execution_department='Prod',
        location='Phase VII',
        equipment='P-101',
        reason='Gasket replacement',
        items=[{'tag': 'XV-101', 'description': 'Inlet valve', 'state': 'close'},
               {'tag': 'XV-102', 'description': 'Outlet valve', 'state': 'close'}],
        isolate_asap=False,
        long_term=False,
        long_term_reason='',
    )
    data.update(over)
    return data


def create_ic(client, as_user='user_turbo', **over) -> int:
    r = client.post('/ics', json=ic_payload(**over), headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ic-id']


def ic_approve(client, ic_id, as_user, action=APPROVE, mark_psic=False, psic_terms=None, comment=None):
    body = {'ic-id': ic_id, 'approval': {'action': action, 'username': as_user, 'timestamp': now_ts(), 'comment': comment}}
    if mark_psic:
        body['mark_psic'] = True
    if psic_terms is not None:
        body['psic_terms'] = psic_terms
    return client.post('/ics/approvals', json=body, headers=auth(as_user))


def isolate_request(client, ic_id, as_user='user_turbo'):
    return client.post('/ics/isolate-request', json={'ic-id': ic_id}, headers=auth(as_user))


def isolate_confirm(client, ic_id, ok=True, as_user='issuing'):
    return client.post('/ics/isolate-confirm', json={'ic-id': ic_id, 'response': ok}, headers=auth(as_user))


def isolate_execute(client, ic_id, as_user='isolator', items=None):
    body = {'ic-id': ic_id}
    if items is not None:
        body['items'] = items
    return client.post('/ics/isolate-execute', json=body, headers=auth(as_user))


def deisolate_request(client, ic_id, as_user='user_turbo'):
    return client.post('/ics/deisolate-request', json={'ic-id': ic_id}, headers=auth(as_user))


def deisolate_confirm(client, ic_id, ok=True, as_user='issuing'):
    return client.post('/ics/deisolate-confirm', json={'ic-id': ic_id, 'response': ok}, headers=auth(as_user))


def deisolate_execute(client, ic_id, as_user='isolator'):
    return client.post('/ics/deisolate-execute', json={'ic-id': ic_id}, headers=auth(as_user))


def link(client, ic_id, ptw_id, as_user='user_turbo'):
    return client.post('/ics/link-ptw', json={'ic-id': ic_id, 'ptw-id': ptw_id}, headers=auth(as_user))


def unlink(client, ic_id, ptw_id, as_user='user_turbo'):
    return client.post('/ics/unlink-ptw', json={'ic-id': ic_id, 'ptw-id': ptw_id}, headers=auth(as_user))


def get_ic(client, ic_id, as_user='coord') -> dict:
    r = client.get(f'/ics/{ic_id}', headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ic']


def list_ics(client, as_user, **body) -> list[dict]:
    r = client.get('/ics', json=body or None, headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['ics']


def make_active_ic(client, **over) -> int:
    """Create, approve, request, confirm and execute isolation: an ACTIVE IC."""
    ic_id = create_ic(client, **over)
    assert ic_approve(client, ic_id, 'issuing').status_code == 200
    assert isolate_request(client, ic_id).status_code == 200
    assert isolate_confirm(client, ic_id).status_code == 200
    assert isolate_execute(client, ic_id).status_code == 200
    return ic_id
