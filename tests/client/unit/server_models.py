"""Load the *server* tree's models into this (client) process without name collisions.

Both trees expose `models`, `GlobalData` and friends at top level. This temporarily swaps
them out of `sys.modules`, imports the server copies with server/ at the front of sys.path,
grabs the module objects, then restores the client copies. The server modules keep working
afterwards because they hold direct references to their own `globalData` and `models.*`.
"""

import importlib
import os
import sys
from functools import lru_cache
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SERVER_DIR = os.path.join(ROOT, 'server')
CLIENT_DIR = os.path.join(ROOT, 'client')

_SHARED_TOP_LEVEL = ('models', 'GlobalData', 'utils')


def _pop_shared():
    saved = {}
    for name in list(sys.modules):
        if name in _SHARED_TOP_LEVEL or name.startswith('models.'):
            saved[name] = sys.modules.pop(name)
    return saved


@lru_cache(maxsize=1)
def load() -> SimpleNamespace:
    client_saved = _pop_shared()
    saved_path = list(sys.path)
    sys.path[:] = [SERVER_DIR] + [p for p in sys.path if os.path.abspath(p) != os.path.abspath(CLIENT_DIR)]
    try:
        importlib.invalidate_caches()
        PTW = importlib.import_module('models.PTW')
        Isolation = importlib.import_module('models.Isolation')
        User = importlib.import_module('models.User')
        GlobalData = importlib.import_module('GlobalData')
        utils = importlib.import_module('utils')
    finally:
        _pop_shared()
        sys.modules.update(client_saved)
        sys.path[:] = saved_path
    assert PTW.__file__.startswith(SERVER_DIR), PTW.__file__
    return SimpleNamespace(PTW=PTW, Isolation=Isolation, User=User, GlobalData=GlobalData, utils=utils)
