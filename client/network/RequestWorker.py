"""``@async_request`` decorator: run a blocking request function off the GUI thread.

Wraps a plain ``fn(*args, **kwargs) -> err | (err, data)`` function (as defined
on each ``*Requests`` mixin) so that:

- called with no ``callback``, it runs synchronously in the caller's thread
  and returns ``fn``'s result directly;
- called with a ``callback``, it instead runs ``fn`` on a dedicated
  ``QThread`` and delivers the result to ``callback(err, data)`` back on the
  thread that owns the shared ``_Relay`` object (normally the GUI thread) via
  a queued ``pyqtSignal`` connection, so the callback is safe to touch widgets
  from even though ``fn`` itself ran elsewhere.
"""

from PyQt6.QtCore import QObject, QThread, pyqtSignal

_relay = None
_active = []   # keeps (thread, worker) pairs alive until the thread finishes


def _get_relay():
    """Return the process-wide ``_Relay`` singleton, creating it on first use.

    Creating the ``_Relay`` (a ``QObject``) lazily, on whichever thread first
    calls this (normally the GUI thread on the first async request), gives it
    that thread's affinity — which is what makes its signal emission from a
    worker thread land on that thread via a queued connection.
    """
    global _relay
    if _relay is None:
        class _Relay(QObject):
            """Cross-thread relay: re-emits a worker's result as a queued signal.

            Lives on the thread that created it (see ``_get_relay``); a worker
            thread calls ``emit()``, which re-emits ``_sig`` and, because the
            connection is queued (cross-thread), causes ``_deliver`` to run on
            the relay's own (GUI) thread instead of the worker thread.
            """

            _sig = pyqtSignal(object, object, object)
            def __init__(self):
                """Construct the relay and connect its internal signal to ``_deliver``."""
                super().__init__()
                self._sig.connect(self._deliver)
            def _deliver(self, cb, err, result):
                """Invoke the original caller-supplied callback with ``(err, result)``."""
                if cb: cb(err, result)
            def emit(self, cb, err, result):
                """Emit the internal signal carrying ``callback``, ``err``, and ``result``."""
                self._sig.emit(cb, err, result)
        _relay = _Relay()
    return _relay


def async_request(fn):
    """Decorate a request function so it can optionally run off the GUI thread.

    Returns a ``wrapper`` that, given a ``callback`` keyword argument, spins up
    a ``QThread``/``Worker`` pair to call ``fn`` in the background and deliver
    its result to ``callback`` via ``_Relay`` (queued signal) instead of
    calling ``fn`` and returning its result directly.
    """
    def wrapper(*args, callback=None, **kwargs):
        """Call ``fn`` synchronously if no ``callback`` is given, else run it on a QThread.

        With no ``callback``, returns whatever ``fn(*args, **kwargs)`` returns
        (typically ``(err, data)`` or just ``err``). With a ``callback``, starts
        a background ``QThread`` running ``fn`` and returns ``None`` immediately;
        the eventual ``(err, data)`` result (or ``(str(e), None)`` if ``fn``
        raised) is delivered asynchronously to ``callback(err, data)``.
        """
        if callback is None:
            return fn(*args, **kwargs)

        relay = _get_relay()
        thread = QThread()

        class Worker(QObject):
            """Runs ``fn`` on the worker ``QThread`` and relays its outcome back."""

            def run(self_):
                """Execute ``fn``, relay its ``(err, data)`` result, then quit the thread.

                Catches any exception from ``fn`` and relays it as
                ``(str(e), None)`` instead of letting it escape the thread. A
                tuple return is unpacked as ``(err, data)``; any other return
                value is relayed as ``(value, None)``. The thread is always
                told to quit afterward, whether ``fn`` succeeded or raised.
                """
                try:
                    ret = fn(*args, **kwargs)
                except Exception as e:
                    relay.emit(callback, str(e), None)
                else:
                    if isinstance(ret, tuple):
                        relay.emit(callback, ret[0], ret[1])
                    else:
                        relay.emit(callback, ret, None)
                finally:
                    thread.quit()

        worker = Worker()
        pair = (thread, worker)
        _active.append(pair)                      # prevent garbage collection
        thread.finished.connect(
            lambda: _active.remove(pair) if pair in _active else None
        )

        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    return wrapper