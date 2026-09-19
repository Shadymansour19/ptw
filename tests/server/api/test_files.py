"""File endpoints: PTW and IC attachments, MIWI documents. Upload, list, download, delete,
copy, duplicate names, and path-traversal attempts - all against the temp PTW_DATA_DIR."""

import io
import os

import pytest

import paths
from conftest import auth, GUEST
from api_helpers import create_ptw
from ic_helpers import create_ic


def upload(client, url, id_field, rec_id, files: dict, as_user='user_turbo'):
    data = {id_field: str(rec_id)}
    for name, content in files.items():
        data[name] = (io.BytesIO(content), name)
    return client.post(url, data=data, content_type='multipart/form-data', headers=auth(as_user))


def listing(client, url, id_field, rec_id, as_user='coord'):
    r = client.get(url, json={id_field: rec_id}, headers=auth(as_user))
    assert r.status_code == 200, r.get_json()
    return sorted(r.get_json()['attachments'])


@pytest.mark.parametrize("kind", ['ptw', 'ic'])
class TestAttachments:
    def _record(self, client, kind):
        return create_ptw(client) if kind == 'ptw' else create_ic(client)

    def _url(self, kind):
        return f'/{kind}s/attachments', f'{kind}-id'

    def test_upload_list_download_delete(self, client, server, kind):
        url, idf = self._url(kind)
        rid = self._record(client, kind)
        assert listing(client, url, idf, rid) == []                                    # no folder yet -> []
        r = upload(client, url, idf, rid, {'MSDS.pdf': b'%PDF-1 a', 'Lifting Plan.pdf': b'%PDF-1 b'})
        assert r.status_code == 200, r.get_json()
        assert listing(client, url, idf, rid) == ['Lifting Plan.pdf', 'MSDS.pdf']
        assert os.path.isfile(os.path.join(paths.attachmentsDir(kind, rid), 'MSDS.pdf'))
        assert paths.attachmentsDir(kind, rid).startswith(server.data_dir)             # never outside the test data dir

        r = client.get(url, json={idf: rid, 'filename': 'MSDS.pdf'}, headers=auth('user_mech'))    # any authenticated user
        assert r.status_code == 200 and r.data == b'%PDF-1 a'
        assert 'attachment' in r.headers.get('Content-Disposition', '')

        r = client.delete(url, json={idf: rid, 'keep-filenames': ['MSDS.pdf']}, headers=auth('user_turbo'))
        assert r.status_code == 200
        assert listing(client, url, idf, rid) == ['MSDS.pdf']
        assert client.delete(url, json={idf: rid, 'keep-filenames': []}, headers=auth('user_turbo')).status_code == 200
        assert listing(client, url, idf, rid) == []

    def test_duplicate_names_reject_the_whole_batch(self, client, kind):
        url, idf = self._url(kind)
        rid = self._record(client, kind)
        upload(client, url, idf, rid, {'a.pdf': b'1'})
        r = upload(client, url, idf, rid, {'a.pdf': b'2', 'b.pdf': b'3'})
        assert r.status_code == 400 and 'already exists: a.pdf' in r.get_json()['error']
        assert listing(client, url, idf, rid) == ['a.pdf']                             # b.pdf was not saved either
        r = client.get(url, json={idf: rid, 'filename': 'a.pdf'}, headers=auth('coord'))
        assert r.data == b'1'

    def test_path_traversal_is_refused(self, client, kind):
        url, idf = self._url(kind)
        victim = self._record(client, kind)
        rid = self._record(client, kind)
        upload(client, url, idf, victim, {'secret.pdf': b'top secret'})
        # upload with a traversal name: werkzeug/the route must not write outside the folder
        r = upload(client, url, idf, rid, {'../secret2.pdf': b'x'})
        assert r.status_code in (200, 400)
        assert not os.path.exists(os.path.join(os.path.dirname(paths.attachmentsDir(kind, rid)), 'secret2.pdf'))
        # download via a sibling folder
        sibling = f'../{kind}-{victim}-attachments/secret.pdf'
        r = client.get(url, json={idf: rid, 'filename': sibling}, headers=auth('coord'))
        assert r.status_code == 400 and r.get_json()['error'] == 'Invalid filename'
        r = client.get(url, json={idf: rid, 'filename': 'nope.pdf'}, headers=auth('coord'))
        assert r.status_code == 404

    def test_validation_and_auth(self, client, kind):
        url, idf = self._url(kind)
        assert client.get(url, json={}, headers=auth('coord')).status_code == 400
        assert client.get(url, json={idf: 'abc'}, headers=auth('coord')).status_code == 400
        assert client.delete(url, json={idf: 1}, headers=auth('coord')).status_code == 400          # keep-filenames required
        assert client.post(url, data={idf: '1'}, headers=auth('coord')).status_code == 200            # nothing to upload is fine
        assert client.get(url, json={idf: 1}).status_code == 401
        assert client.post(url, data={idf: '1'}).status_code == 401

    def test_upload_without_id(self, client, kind):
        url, idf = self._url(kind)
        r = client.post(url, data={'x.pdf': (io.BytesIO(b'1'), 'x.pdf')}, content_type='multipart/form-data', headers=auth('coord'))
        assert r.status_code == 400


class TestCopy:
    def test_copy_attachments_between_ptws(self, client):
        src, dst = create_ptw(client), create_ptw(client, equipment='dst')
        upload(client, '/ptws/attachments', 'ptw-id', src, {'a.pdf': b'A', 'b.pdf': b'B'})
        upload(client, '/ptws/attachments', 'ptw-id', dst, {'c.pdf': b'C'})
        r = client.post('/ptws/attachments/copy', json={'source-ptw-id': src, 'target-ptw-id': dst}, headers=auth('user_turbo'))
        assert r.status_code == 200 and r.get_json()['risk-copy-error'] is None
        assert listing(client, '/ptws/attachments', 'ptw-id', dst) == ['a.pdf', 'b.pdf', 'c.pdf']
        assert listing(client, '/ptws/attachments', 'ptw-id', src) == ['a.pdf', 'b.pdf']          # source untouched

    def test_copy_validation(self, client):
        assert client.post('/ptws/attachments/copy', json={'source-ptw-id': 1}, headers=auth('user_turbo')).status_code == 400
        assert client.post('/ptws/attachments/copy', json={'source-ptw-id': 'a', 'target-ptw-id': 2}, headers=auth('user_turbo')).status_code == 400
        assert client.post('/ptws/attachments/copy', json={'source-ptw-id': 1, 'target-ptw-id': 2}, headers=auth(GUEST)).status_code == 401
        # a source with no folder is a no-op success
        r = client.post('/ptws/attachments/copy', json={'source-ptw-id': 77, 'target-ptw-id': 78}, headers=auth('user_turbo'))
        assert r.status_code == 200


class TestMiwi:
    def _upload(self, client, name, content=b'%PDF-1 miwi', department='Turbo', as_user='user_turbo'):
        data = {'department': department, 'miwi': (io.BytesIO(content), name)}
        return client.post('/miwi', data=data, content_type='multipart/form-data', headers=auth(as_user))

    def _list(self, client, department=None, as_user='coord'):
        r = client.get('/miwis', json={'department': department} if department else {}, headers=auth(as_user))
        assert r.status_code == 200, r.get_json()
        return sorted(r.get_json()['miwis'])

    def test_upload_list_download(self, client, server):
        assert self._list(client) == []
        assert self._upload(client, 'MIWI-1.pdf').status_code == 200
        assert self._upload(client, 'MIWI-2.pdf', department='Mech', as_user='user_mech').status_code == 200
        assert self._list(client, 'Turbo') == ['MIWI-1.pdf']
        assert self._list(client, 'Mech') == ['MIWI-2.pdf']
        assert self._list(client) == ['MIWI-1.pdf', 'MIWI-2.pdf']                  # no department: everything
        assert self._list(client, 'Narnia') == ['MIWI-1.pdf', 'MIWI-2.pdf']         # unknown department: everything
        assert os.path.isfile(os.path.join(paths.MIWI_DIR, 'Turbo', 'MIWI-1.pdf'))
        assert paths.MIWI_DIR.startswith(server.data_dir)

        r = client.get('/miwi', json={'filename': 'MIWI-2.pdf', 'department': 'Turbo'}, headers=auth('user_turbo'))
        assert r.status_code == 200 and r.data == b'%PDF-1 miwi'                    # cross-department read is allowed
        r = client.get('/miwi', json={'filename': 'MIWI-2.pdf'}, headers=auth('user_turbo'))
        assert r.status_code == 200

    def test_upload_validation(self, client):
        assert self._upload(client, 'x.pdf', department='Narnia').status_code == 400
        r = client.post('/miwi', data={'department': 'Turbo'}, content_type='multipart/form-data', headers=auth('user_turbo'))
        assert r.status_code == 400 and 'No file part' in r.get_json()['error']
        assert self._upload(client, 'dup.pdf').status_code == 200
        r = self._upload(client, 'dup.pdf')
        assert r.status_code == 400 and 'same name already exists' in r.get_json()['error']
        assert self._upload(client, 'x.pdf', as_user=GUEST).status_code == 200      # guests may upload too (any authenticated user)

    def test_download_validation(self, client):
        assert client.get('/miwi', json={}, headers=auth('coord')).status_code == 400
        r = client.get('/miwi', json={'filename': 'nope.pdf'}, headers=auth('coord'))
        assert r.status_code == 404 and r.get_json()['error'] == 'File not found'
        r = client.get('/miwi', json={'filename': '../../etc/passwd'}, headers=auth('coord'))
        assert r.status_code == 404                                                  # traversal resolves to "not found", never a file
        assert client.get('/miwi', json={'filename': 'x'}).status_code == 401
        assert client.get('/miwis').status_code == 401
