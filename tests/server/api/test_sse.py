"""Server-Sent Events fan-out: who gets which event when a route mutates a PTW."""

import json
import queue

import pytest

from models.User import UserRoles
from models.SSE import SSEObject, SSEAction
from api_helpers import create_ptw, approve_fully, run_request


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def parse(msg):
    event, data = msg.strip().split('\n')
    assert event.startswith('event: ')
    return event[len('event: '):], json.loads(data[len('data: '):])


@pytest.fixture
def listeners(server):
    qs = {role: server.sse.registerClient(role) for role in (UserRoles.USER, UserRoles.COORDINATOR, UserRoles.ISSUING, UserRoles.GAS_TESTER)}
    yield qs
    for role, q in qs.items():
        server.sse.unregisterClient(role, q)


def test_broadcast_targets_roles(server, listeners):
    server.sse.broadcast(SSEObject.PTW, 7, SSEAction.CREATED, 'someone', roles=[UserRoles.USER])
    assert len(drain(listeners[UserRoles.USER])) == 1
    assert drain(listeners[UserRoles.COORDINATOR]) == []
    server.sse.broadcast(SSEObject.IC, 3, SSEAction.ISOLATED, 'iso')        # roles=None -> everyone
    for q in listeners.values():
        event, data = parse(drain(q)[0])
        assert event == 'ic'
        assert data == {'object': 'IC', 'object_id': 3, 'action': 'isolated', 'by': 'iso'}


def test_routes_emit_the_documented_events(client, server, listeners):
    pid = create_ptw(client)
    assert [parse(m)[1]['action'] for m in drain(listeners[UserRoles.USER])] == ['created']
    assert [parse(m)[1]['action'] for m in drain(listeners[UserRoles.COORDINATOR])] == ['created']
    assert drain(listeners[UserRoles.ISSUING]) == []                        # create is USER+COORDINATOR only

    approve_fully(client, pid)
    for role in listeners:                                                   # approvals go to every role
        assert [parse(m)[1]['action'] for m in drain(listeners[role])] == ['approved'] * 3

    run_request(client, pid)
    msgs = {role: drain(q) for role, q in listeners.items()}
    assert [parse(m)[1] for m in msgs[UserRoles.ISSUING]] == [{'object': 'PTW', 'object_id': pid, 'action': 'run requested', 'by': 'user_turbo'}]
    assert len(msgs[UserRoles.USER]) == 1
    assert msgs[UserRoles.COORDINATOR] == [] and msgs[UserRoles.GAS_TESTER] == []


def test_unregister_and_client_count(server):
    q = server.sse.registerClient(UserRoles.ISOLATOR)
    assert server.sse.clientCount(UserRoles.ISOLATOR) == 1
    server.sse.unregisterClient(UserRoles.ISOLATOR, q)
    assert server.sse.clientCount(UserRoles.ISOLATOR) == 0
    server.sse.unregisterClient(UserRoles.ISOLATOR, q)   # idempotent
