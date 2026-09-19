"""The client's SSE listener against the live server's /events stream."""

import time

import pytest
from PyQt6.QtCore import QThread

from models.PTW import PTW
from network.SSEListener import SSEListener
from network.clientRequests import ClientRequests as CR
from ptw_factory import ptw_payload

pytestmark = pytest.mark.contract


@pytest.fixture
def listener(contract, qtbot):
    made = []

    def start(username):
        l = SSEListener(contract.url, username, 'pw', verify=True)
        received = []
        l.eventReceived.connect(lambda et, data: received.append((et, data)))
        l.received = received
        l.start()
        made.append(l)
        return l

    yield start
    for l in made:
        l.stop()
    # stop() can't interrupt a blocking read; the loop only notices _running is False on the
    # next line from the stream (the real app has the same property, bounded by the server's
    # 30 s heartbeat). An approval is broadcast to every role, so it wakes every listener.
    try:
        u = contract.login('user_turbo')
        err, pid = CR.addPTW(u, PTW(ptw_payload(equipment='wake-up')))
        coord = contract.login('coord')
        CR.updateApprovalPTW(coord, pid, PTW.Approval(action='Approved', username='coord', timestamp='19/09/2026 10:00:00'))
    except AssertionError:
        pass
    for l in made:
        assert l.wait(40000), "listener thread did not stop"


def _wait_for(qtbot, predicate, timeout=10000):
    qtbot.waitUntil(predicate, timeout=timeout)


def test_events_arrive_for_the_targeted_roles(contract, qtbot, listener):
    coord_l = listener('coord')
    issuing_l = listener('issuing')
    user = contract.login('user_turbo')
    # The stream registers asynchronously; poke until the first event lands.
    deadline = time.time() + 15
    while not coord_l.received and time.time() < deadline:
        err, pid = CR.addPTW(user, PTW(ptw_payload()))
        assert err is None
        qtbot.wait(300)
    assert coord_l.received, contract.log_tail()
    et, data = coord_l.received[-1]
    assert et == 'ptw'
    assert data['object'] == 'PTW' and data['action'] == 'created' and data['by'] == 'user_turbo'
    assert data['object_id'] == pid
    assert issuing_l.received == []                    # 'created' goes to USER and COORDINATOR only

    # a coordinator approval is broadcast to everyone
    coord = contract.login('coord')
    assert CR.updateApprovalPTW(coord, pid, PTW.Approval(action='Approved', username='coord', timestamp='19/09/2026 10:00:00')) is None
    _wait_for(qtbot, lambda: any(d['action'] == 'approved' for _, d in issuing_l.received))
    assert any(d['action'] == 'approved' and d['object_id'] == pid for _, d in coord_l.received)


def test_bad_credentials_never_emit_and_keep_retrying_quietly(contract, qtbot):
    l = SSEListener(contract.url, 'coord', 'wrong', verify=True)
    received = []
    l.eventReceived.connect(lambda et, data: received.append((et, data)))
    l.start()
    qtbot.wait(1500)
    assert l.isRunning() and received == []
    l.stop()
    assert l.wait(10000)          # blocked in its 5 s retry sleep, not in a stream read
