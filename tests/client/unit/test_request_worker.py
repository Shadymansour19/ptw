"""network/RequestWorker.py: the @async_request decorator's threading contract.

With a callback the wrapped function must run off the GUI thread and its result must be
handed to the callback back on the GUI thread; without one it is a plain synchronous call.
"""

import threading

import pytest
from PyQt6.QtCore import QThread, QCoreApplication

import network.RequestWorker as rw
from network.RequestWorker import async_request


def gui_thread():
    return QCoreApplication.instance().thread()


@pytest.fixture
def delivered(qtbot):
    """A callback that records (err, data) plus the QThread it was invoked on, and a waiter."""
    seen = []

    def callback(err, data):
        seen.append((err, data, QThread.currentThread()))

    def wait():
        qtbot.waitUntil(lambda: len(seen) >= 1, timeout=5000)
        return seen

    callback.wait = wait
    return callback


class TestSynchronous:
    def test_without_callback_the_function_runs_inline_and_returns_its_value(self, qapp):
        calls = []

        @async_request
        def fetch(a, b, flag=False):
            calls.append((a, b, flag, QThread.currentThread()))
            return None, {'sum': a + b}

        assert fetch(1, 2, flag=True) == (None, {'sum': 3})
        assert calls == [(1, 2, True, gui_thread())]

    def test_without_callback_exceptions_propagate(self):
        @async_request
        def boom():
            raise ValueError('boom')

        with pytest.raises(ValueError, match='boom'):
            boom()

    def test_without_callback_nothing_is_tracked(self):
        before = list(rw._active)

        @async_request
        def fetch():
            return 'err'

        assert fetch() == 'err'
        assert rw._active == before


class TestAsynchronous:
    def test_tuple_result_is_unpacked_and_delivered_on_the_gui_thread(self, qtbot, delivered):
        ran_on = []

        @async_request
        def fetch(x, *, unit):
            ran_on.append(QThread.currentThread())
            return None, f'{x} {unit}'

        assert fetch(5, unit='bar', callback=delivered) is None      # returns immediately
        seen = delivered.wait()
        assert seen == [(None, '5 bar', gui_thread())]
        assert ran_on and ran_on[0] is not gui_thread()               # the work itself left the GUI thread

    def test_non_tuple_result_is_delivered_as_the_error(self, delivered):
        @async_request
        def fetch():
            return 'Server unreachable'

        fetch(callback=delivered)
        assert delivered.wait()[0][:2] == ('Server unreachable', None)

    def test_none_result_means_success_with_no_data(self, delivered):
        @async_request
        def fetch():
            return None

        fetch(callback=delivered)
        assert delivered.wait()[0][:2] == (None, None)

    def test_exception_is_delivered_as_its_message(self, delivered):
        @async_request
        def fetch():
            raise RuntimeError('connection refused')

        fetch(callback=delivered)
        err, data, thread = delivered.wait()[0]
        assert (err, data) == ('connection refused', None)
        assert thread is gui_thread()

    def test_callback_is_never_called_synchronously(self, qtbot):
        order = []
        release = threading.Event()

        @async_request
        def fetch():
            release.wait(5)
            return None, 'late'

        fetch(callback=lambda err, data: order.append('callback'))
        order.append('returned')
        release.set()
        qtbot.waitUntil(lambda: len(order) == 2, timeout=5000)
        assert order == ['returned', 'callback']

    def test_active_bookkeeping_is_released_when_the_thread_finishes(self, qtbot, delivered):
        before = len(rw._active)

        @async_request
        def fetch():
            return None, 1

        fetch(callback=delivered)
        delivered.wait()
        qtbot.waitUntil(lambda: len(rw._active) == before, timeout=5000)

    def test_concurrent_requests_each_reach_their_own_callback(self, qtbot):
        results = {}

        @async_request
        def fetch(n):
            return None, n * 10

        for n in range(4):
            fetch(n, callback=lambda err, data, n=n: results.__setitem__(n, (err, data)))
        qtbot.waitUntil(lambda: len(results) == 4, timeout=5000)
        assert results == {n: (None, n * 10) for n in range(4)}
        qtbot.waitUntil(lambda: not rw._active, timeout=5000)
