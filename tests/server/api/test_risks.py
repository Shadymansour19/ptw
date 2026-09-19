"""Risk assessment routes: the generic library (HSE only) and per-PTW row sets (anyone)."""

import pytest

from conftest import auth, GUEST
from api_helpers import create_ptw


def item(hazard='Pinch', ctrl='Gloves', **over):
    d = dict(hazard=hazard, effect='Injury', free_analysis='Med', ctrl=ctrl, ctrl_analysis='Low', eval='OK')
    d.update(over)
    return d


def assessment(title='Use of Hand Tools', ptw_id=None, items=None, date='19/09/2026'):
    return {'title': title, 'date': date, 'ptw_id': ptw_id, 'risks': items or [item()]}


def library(client, as_user='coord'):
    r = client.get('/risks', headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['risks']


def ptw_risk(client, pid, as_user='coord'):
    r = client.get('/risks/ptw', json={'ptw_id': pid}, headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return r.get_json()['risk']


class TestGenericLibrary:
    def test_empty_library(self, client):
        assert library(client) == {}
        assert library(client, GUEST) == {}                       # readable by guests too

    @pytest.mark.xfail(strict=True, reason=(
        "Known bug: server/db/risksDb.py updateRiskAssessmentFromDict deletes the old rows with "
        "`WHERE title = %s and ptw_id = %s`; for a library assessment ptw_id is NULL and `= NULL` "
        "never matches in SQL, so nothing is deleted and every edit APPENDS its items to the "
        "existing ones (the library entry grows on each save). Use `ptw_id IS NOT DISTINCT FROM %s` "
        "(or a separate IS NULL branch)."))
    def test_hse_creates_updates_deletes(self, client):
        r = client.post('/risks', json=assessment(items=[item(), item(hazard='Noise', ctrl='Ear plugs')]), headers=auth('hse'))
        assert r.status_code == 200 and r.get_json() == {'success': True, 'error': None}
        lib = library(client)
        assert set(lib) == {'Use of Hand Tools'}
        assert sorted(i['hazard'] for i in lib['Use of Hand Tools']['risks']) == ['Noise', 'Pinch']
        assert lib['Use of Hand Tools']['ptw_id'] is None and lib['Use of Hand Tools']['date'] == '19/09/2026'

        r = client.put('/risks', json=assessment(items=[item(hazard='Cuts', ctrl='Gloves')], date='20/09/2026'), headers=auth('hse'))
        assert r.status_code == 200 and r.get_json()['error'] is None
        lib = library(client)
        assert [i['hazard'] for i in lib['Use of Hand Tools']['risks']] == ['Cuts']   # replaced, not appended
        assert lib['Use of Hand Tools']['date'] == '20/09/2026'

        r = client.delete('/risks', json={'title': 'Use of Hand Tools'}, headers=auth('hse'))
        assert r.status_code == 200 and r.get_json()['error'] is None
        assert library(client) == {}

    def test_only_hse_may_touch_the_generic_library(self, client):
        for user in ('coord', 'user_turbo', 'issuing', 'admin', GUEST):
            assert client.post('/risks', json=assessment(), headers=auth(user)).status_code == 401, user
            assert client.put('/risks', json=assessment(), headers=auth(user)).status_code == 401, user
            assert client.delete('/risks', json={'title': 'x'}, headers=auth(user)).status_code == 401, user
        assert library(client) == {}

    def test_anonymous_is_rejected_everywhere(self, client):
        assert client.get('/risks').status_code == 401
        assert client.get('/risks/ptw', json={'ptw_id': 1}).status_code == 401
        assert client.post('/risks', json=assessment()).status_code == 401

    def test_malformed_payload_is_reported_not_raised(self, client):
        r = client.post('/risks', json={'title': 'x'}, headers=auth('hse'))       # no date/risks
        assert r.status_code == 200 and r.get_json()['error']                      # DB layer's message string
        r = client.delete('/risks', json={}, headers=auth('hse'))
        assert r.status_code == 400                                                 # missing 'title' raises KeyError -> 400


class TestPtwSpecific:
    def test_any_user_manages_their_ptw_rows(self, client):
        pid = create_ptw(client)
        assert ptw_risk(client, pid) is None
        r = client.post('/risks', json=assessment(title=str(pid), ptw_id=pid), headers=auth('user_turbo'))
        assert r.status_code == 200 and r.get_json()['error'] is None
        risk = ptw_risk(client, pid, 'user_mech')                                    # readable across departments
        assert risk['ptw_id'] == pid and len(risk['risks']) == 1
        assert library(client) == {}                                                 # PTW rows never leak into the library

        r = client.put('/risks', json=assessment(title=str(pid), ptw_id=pid, items=[item(hazard='A'), item(hazard='B')]), headers=auth('user_turbo'))
        assert r.status_code == 200
        assert sorted(i['hazard'] for i in ptw_risk(client, pid)['risks']) == ['A', 'B']

        r = client.delete('/risks', json={'title': str(pid), 'ptw_id': pid}, headers=auth('user_turbo'))
        assert r.status_code == 200
        assert ptw_risk(client, pid) is None

    def test_lookup_validation(self, client):
        assert client.get('/risks/ptw', json={}, headers=auth('coord')).status_code == 400
        assert client.get('/risks/ptw', json={'ptw_id': 'abc'}, headers=auth('coord')).status_code == 400
        assert client.get('/risks/ptw', json={'ptw_id': 999}, headers=auth('coord')).status_code == 404

    def test_copy_between_ptws_is_additive_and_deduplicated(self, client, server):
        src = create_ptw(client)
        dst = create_ptw(client, equipment='dst')
        client.post('/risks', json=assessment(title=str(src), ptw_id=src, items=[item(hazard='A'), item(hazard='B')]), headers=auth('user_turbo'))
        client.post('/risks', json=assessment(title=str(dst), ptw_id=dst, items=[item(hazard=' b ', ctrl='gloves')]), headers=auth('user_turbo'))   # same as B after strip/casefold
        r = client.post('/ptws/attachments/copy', json={'source-ptw-id': src, 'target-ptw-id': dst}, headers=auth('user_turbo'))
        assert r.status_code == 200 and r.get_json()['risk-copy-error'] is None
        copied = ptw_risk(client, dst)
        assert sorted(i['hazard'].strip() for i in copied['risks']) == ['A', 'b']    # B was a duplicate of ' b '
        assert copied['title'] == str(dst) and copied['ptw_id'] == dst
        # copying from a PTW with no rows is a no-op, not an error
        empty = create_ptw(client, equipment='empty')
        r = client.post('/ptws/attachments/copy', json={'source-ptw-id': empty, 'target-ptw-id': dst}, headers=auth('user_turbo'))
        assert r.status_code == 200 and r.get_json()['risk-copy-error'] is None
        assert len(ptw_risk(client, dst)['risks']) == 2
