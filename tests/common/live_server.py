#!/usr/bin/env python3
"""Test-only PTW server, spawned by the client contract tests (tests/client/conftest.py).

Runs the real Flask app under waitress on the given port, against the throwaway test
database and a temp data dir (see ptw_test_db), with the fixed test users seeded, outgoing
mail disabled, and one extra route the real server does not have:

    POST /__test__/reset   -> empty ptws/ics/risks, wipe attachment folders, resync the cache

Prints `READY <port>` on stdout once it is serving. Exit code 2 means PostgreSQL was not
reachable. Never run this against a real deployment: it truncates tables on request.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERVER_DIR = os.path.join(ROOT, 'server')
sys.path.insert(0, SERVER_DIR)
sys.path.insert(0, HERE)

import ptw_test_db  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()

    settings = ptw_test_db.configure_env()
    err = ptw_test_db.postgres_reachable(settings)
    if err:
        print(f"ERROR PostgreSQL not reachable: {err}", flush=True)
        sys.exit(2)
    ptw_test_db.ensure_test_database(settings)
    ptw_test_db.patch_bcrypt()

    import app as app_module
    import core
    from GlobalData import globalData
    from flask import jsonify

    core.mail.send = lambda msg: None                       # never email from a test server
    ptw_test_db.reset_users(core)
    ptw_test_db.reset_tables(core, globalData)

    @app_module.app.route('/__test__/reset', methods=['POST'])
    def _reset():
        ptw_test_db.reset_tables(core, globalData)
        return jsonify({'success': True})

    print(f"READY {args.port}", flush=True)
    from waitress import serve
    serve(app_module.app, host='127.0.0.1', port=args.port, threads=4)


if __name__ == '__main__':
    main()
