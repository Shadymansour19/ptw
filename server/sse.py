"""Server-Sent Events client registry and broadcast mechanism backing GET /events.
Connected clients are tracked per role in an in-memory dict of bounded queues;
broadcast() fans a message out to every queue belonging to the targeted role(s),
and each /events request's generator loop (in routes/auth.py) blocks on its own
queue and yields whatever text is put into it."""

import json
import queue
import logging
import threading

from models.SSE import SSEObject, SSEAction
from models.User import UserRoles

log = logging.getLogger("app")

_sse_clients: dict[UserRoles, list[queue.Queue]] = {}
_sse_lock = threading.Lock()


def registerClient(role: UserRoles) -> queue.Queue:
    """Create and register a new bounded (maxsize=50) queue for a connecting
    SSE client of the given role, returning it for the caller's stream loop to
    read from."""
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.setdefault(role, []).append(q)
    return q


def unregisterClient(role: UserRoles, q: queue.Queue):
    """Remove a previously registered client queue for the given role, e.g. on
    stream disconnect; silently ignores an already-removed or unknown queue."""
    with _sse_lock:
        try:
            _sse_clients[role].remove(q)
        except (ValueError, KeyError):
            pass


def clientCount(role: UserRoles) -> int:
    """Return the number of currently connected SSE clients for the given role."""
    return len(_sse_clients.get(role, []))


def broadcast(obj: SSEObject, object_id, action: SSEAction, by: str, roles: list[UserRoles] = None):
    """Broadcast an SSE event: <object> <object-id> <action> by <actor>. roles=None sends to all connected roles."""
    data = {"object": obj.value, "object_id": object_id, "action": action.value, "by": by}
    msg = f"event: {obj.value.lower()}\ndata: {json.dumps(data)}\n\n"
    dropped = 0
    with _sse_lock:
        targets = roles if roles is not None else list(_sse_clients.keys())
        for role in targets:
            for q in list(_sse_clients.get(role, [])):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    _sse_clients[role].remove(q)
                    dropped += 1
    if dropped:
        log.warning("SSE broadcast '%s #%s %s': dropped %d full client queue(s)", obj.value, object_id, action.value, dropped)
    else:
        log.debug("SSE broadcast '%s #%s %s' by='%s'", obj.value, object_id, action.value, by)
