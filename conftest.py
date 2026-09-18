"""Repo-root pytest guard.

The server and client trees both ship a top-level ``models`` package (plus ``GlobalData``,
``helper``, ...), so they cannot be imported into one Python process. Each half of the
suite therefore has its own rootdir (``tests/server`` and ``tests/client``, each with a
``pytest.ini``) and must be run as a separate pytest invocation - see ``tests/run_all.sh``.
This file only exists to fail fast, with a clear message, when someone runs ``pytest`` from
the repo root and would otherwise collect both halves into one process.
"""

import os
import pytest


def pytest_configure(config):
    root = str(config.rootpath)
    server = os.path.join(root, 'tests', 'server')
    client = os.path.join(root, 'tests', 'client')

    def touches(path):
        for arg in config.args or ['.']:
            full = os.path.abspath(os.path.join(config.invocation_params.dir, arg.split('::')[0]))
            if full == path or full.startswith(path + os.sep) or path.startswith(full + os.sep):
                return True
        return False

    if touches(server) and touches(client):
        raise pytest.UsageError(
            "tests/server and tests/client cannot run in one process (both trees define a "
            "top-level 'models' package). Run them separately:\n"
            "    pytest tests/server\n"
            "    pytest tests/client\n"
            "or use tests/run_all.sh"
        )
