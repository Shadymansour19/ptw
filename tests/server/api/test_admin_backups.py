"""Admin routes: server log listing/download and the on-demand backup service (real pg_dump
against the test database, real tar of the temp data dir)."""

import os
import shutil
import tarfile

import pytest

import paths
import backupService
from conftest import auth


@pytest.fixture(autouse=True)
def clean_backups():
    shutil.rmtree(paths.BACKUP_DIR, ignore_errors=True)
    yield
    shutil.rmtree(paths.BACKUP_DIR, ignore_errors=True)


class TestLogs:
    def test_list_and_download(self, client, server):
        r = client.get('/logs', headers=auth('admin'))
        assert r.status_code == 200
        logs = r.get_json()['logs']
        assert 'ptw-server.log' in logs and logs == sorted(logs)
        r = client.get('/logs', json={'filename': 'ptw-server.log'}, headers=auth('admin'))
        assert r.status_code == 200 and r.mimetype == 'text/plain'
        assert b'PTW' in r.data or b'server' in r.data
        assert paths.LOGS_DIR.startswith(server.data_dir)

    def test_traversal_and_missing(self, client):
        r = client.get('/logs', json={'filename': '../.env'}, headers=auth('admin'))
        assert r.status_code == 400 and r.get_json()['error'] == 'Invalid filename'
        assert client.get('/logs', json={'filename': 'nope.log'}, headers=auth('admin')).status_code == 404

    def test_admin_only(self, client):
        for user in ('coord', 'issuing', 'user_turbo'):
            assert client.get('/logs', headers=auth(user)).status_code == 401
            assert client.get('/backups', headers=auth(user)).status_code == 401
            assert client.post('/backups', headers=auth(user)).status_code == 401
            assert client.delete('/backups', json={'name': 'x'}, headers=auth(user)).status_code == 401


class TestBackups:
    def test_empty_listing(self, client):
        r = client.get('/backups', headers=auth('admin'))
        assert r.status_code == 200
        body = r.get_json()
        assert body['backups'] == [] and body['lastBackupAt'] is None and body['retentionDays'] == 14
        assert body['freeBytes'] is None                                          # no BACKUP_DIR yet

    @pytest.mark.skipif(shutil.which('pg_dump') is None, reason='pg_dump not installed')
    def test_create_list_download_delete(self, client, server):
        # something to back up besides the DB dump
        os.makedirs(os.path.join(paths.MIWI_DIR, 'Turbo'), exist_ok=True)
        with open(os.path.join(paths.MIWI_DIR, 'Turbo', 'm.pdf'), 'wb') as f:
            f.write(b'miwi')
        r = client.post('/backups', headers=auth('admin'))
        assert r.status_code == 200, r.get_json()
        row = r.get_json()['backup']
        name = row['name']
        assert row['complete'] is True and row['dumpSizeBytes'] > 0 and row['filesSizeBytes'] > 0
        assert row['totalSizeBytes'] == row['dumpSizeBytes'] + row['filesSizeBytes']
        dump = os.path.join(paths.BACKUP_DIR, name, f"{os.environ['DB_NAME']}.dump")
        assert os.path.isfile(dump) and open(dump, 'rb').read(5) == b'PGDMP'    # a real custom-format pg_dump
        with tarfile.open(os.path.join(paths.BACKUP_DIR, name, 'files.tar.gz')) as tf:
            names = tf.getnames()
        assert 'miwi/Turbo/m.pdf' in names and '.env' in names

        body = client.get('/backups', headers=auth('admin')).get_json()
        assert [b['name'] for b in body['backups']] == [name]
        assert body['lastBackupAt'] == row['created'] and body['freeBytes'] > 0

        r = client.get('/backups', json={'name': name, 'which': 'files'}, headers=auth('admin'))
        assert r.status_code == 200 and r.data[:2] == b'\x1f\x8b'                 # gzip magic
        r = client.get('/backups', json={'name': name, 'which': 'dump'}, headers=auth('admin'))
        assert r.status_code == 200 and r.data[:5] == b'PGDMP'
        r = client.get('/backups', json={'name': name, 'which': 'logs'}, headers=auth('admin'))
        assert r.status_code == 400 and 'Invalid file requested' in r.get_json()['error']

        assert client.delete('/backups', json={'name': name}, headers=auth('admin')).status_code == 200
        assert client.get('/backups', headers=auth('admin')).get_json()['backups'] == []
        r = client.delete('/backups', json={'name': name}, headers=auth('admin'))
        assert r.status_code == 400 and 'not found' in r.get_json()['error']

    def test_name_validation_guards_traversal(self, client):
        for bad in ('../../etc', '20260101_1200', 'x', '', None):
            r = client.get('/backups', json={'name': bad or 'x', 'which': 'dump'}, headers=auth('admin'))
            assert r.status_code in (400, 404), bad
            r = client.delete('/backups', json={'name': bad}, headers=auth('admin'))
            assert r.status_code == 400, bad
        with pytest.raises(ValueError):
            backupService.resolveBackupDir('20260101_120000/../..')

    def test_listing_ignores_foreign_folders_and_sorts_newest_first(self, client):
        for name in ('20260102_000000', 'not-a-backup', '20260101_000000'):
            os.makedirs(os.path.join(paths.BACKUP_DIR, name), exist_ok=True)
        open(os.path.join(paths.BACKUP_DIR, 'stray.txt'), 'w').close()
        body = client.get('/backups', headers=auth('admin')).get_json()
        assert [b['name'] for b in body['backups']] == ['20260102_000000', '20260101_000000']
        assert all(b['complete'] is False for b in body['backups'])
        assert body['lastBackupAt'] == '2026-01-02T00:00:00'
        r = client.get('/backups', json={'name': '20260101_000000', 'which': 'dump'}, headers=auth('admin'))
        assert r.status_code == 404

    def test_pg_dump_failure_is_a_500(self, client, monkeypatch):
        monkeypatch.setenv('DB_NAME', 'no_such_database_for_tests')
        r = client.post('/backups', headers=auth('admin'))
        assert r.status_code == 500 and 'pg_dump failed' in r.get_json()['error']
