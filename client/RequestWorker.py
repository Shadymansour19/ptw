from PyQt6.QtCore import QObject, QThread, pyqtSignal


class _Relay(QObject):
    """
    Singleton that lives on the GUI thread.
    Receives the cross-thread signal and calls the callback safely on the GUI thread.
    """
    _sig = pyqtSignal(object, object, object)   # (callback, err, result)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._deliver)

    def _deliver(self, cb, err, result):
        if cb:
            cb(err, result)

    def emit(self, cb, err, result):
        self._sig.emit(cb, err, result)


_relay = _Relay()   # created once on the GUI thread at import time


def async_request(fn):
    """
    Decorator for ClientRequests methods.

    - Without callback: behaves exactly as before (synchronous).
    - With callback:    runs fn on a background thread, then calls
                        callback(err, result) back on the GUI thread.

    Usage:
        # sync — unchanged, still works:
        err, user = ClientRequests.login(username, password)

        # async — non-blocking:
        def on_done(err, user):
            if err: ...
        ClientRequests.login(username, password, callback=on_done)
    """
    def wrapper(*args, callback=None, **kwargs):
        if callback is None:
            return fn(*args, **kwargs)      # sync path, fully unchanged

        thread = QThread()

        class Worker(QObject):
            def run(self_):
                try:
                    ret = fn(*args, **kwargs)
                except Exception as e:
                    _relay.emit(callback, str(e), None)
                else:
                    if isinstance(ret, tuple):
                        _relay.emit(callback, ret[0], ret[1])
                    else:                   # method returns plain err or None
                        _relay.emit(callback, ret, None)
                finally:
                    thread.quit()

        worker = Worker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    return wrapper
