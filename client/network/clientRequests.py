"""Compose the individual endpoint-group mixins into the single HTTP client class.

Each sibling module in this package (``authRequests``, ``userRequests``,
``ptwRequests``, ``icRequests``, ``riskRequests``, ``documentRequests``,
``adminRequests``) defines one mixin holding the thin wrapper methods for a
group of related server endpoints. This module just combines them all into
``ClientRequests``, the single class the rest of the client calls into for
every HTTP request to the Flask server.
"""

from network.authRequests import AuthRequests
from network.userRequests import UserRequests
from network.ptwRequests import PTWRequests
from network.icRequests import ICRequests
from network.riskRequests import RiskRequests
from network.documentRequests import DocumentRequests
from network.adminRequests import AdminRequests


class ClientRequests(AuthRequests, UserRequests, PTWRequests, ICRequests, RiskRequests, DocumentRequests, AdminRequests):
    """The composed HTTP client the rest of the app uses to talk to the server.

    Combines every endpoint-group mixin (auth, users, PTWs, ICs, risk
    assessments, documents/MIWI, admin) into one class. Callers invoke its
    methods directly on the class (e.g. ``ClientRequests.login(...)``); each
    method is wrapped with ``@async_request`` (see ``network/RequestWorker.py``)
    so it can run synchronously or be offloaded to a background thread with a
    callback, and returns ``(err, data)`` rather than raising.
    """

    pass
