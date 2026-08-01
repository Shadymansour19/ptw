from PyQt6.QtCore import QObject, QThread, pyqtSignal

_relay = None
_active = []   # keeps (thread, worker) pairs alive until the thread finishes


def _get_relay():
    global _relay
    if _relay is None:
        class _Relay(QObject):
            _sig = pyqtSignal(object, object, object)
            def __init__(self):
                super().__init__()
                self._sig.connect(self._deliver)
            def _deliver(self, cb, err, result):
                if cb: cb(err, result)
            def emit(self, cb, err, result):
                self._sig.emit(cb, err, result)
        _relay = _Relay()
    return _relay


def async_request(fn):
    def wrapper(*args, callback=None, **kwargs):
        if callback is None:
            return fn(*args, **kwargs)

        relay = _get_relay()
        thread = QThread()

        class Worker(QObject):
            def run(self_):
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