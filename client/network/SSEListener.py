"""Background thread that streams real-time PTW/IC events from GET /events.

See "Real-Time Events (SSE)" in PROJECT.md for the server-side event envelope
and the full list of broadcast object/action pairs.
"""

import json
import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal


class SSEListener(QThread):
    """QThread that keeps a long-lived SSE connection to GET /events open.

    Parses the ``event:``/``data:`` lines of the stream and re-emits each
    event generically as ``eventReceived(event_type, data)`` — consumers
    (``MainWindow._onSSEEvent``) dispatch on the ``data`` payload's own
    ``{object, object_id, action, by}`` envelope, not on ``event_type``. Runs
    until ``stop()`` is called, auto-reconnecting after any connection error.

    The server keeps no replay buffer / Last-Event-ID support, so anything
    broadcast while disconnected is gone by the time the stream reopens —
    ``reconnected`` tells a consumer (``MainWindow``) exactly when that may have
    happened, so it can run a full resync instead of silently trusting a cache
    that might be missing whatever was lost during the outage.
    """

    eventReceived = pyqtSignal(str, dict)   # (event_type, data)
    reconnected = pyqtSignal()   # fired once the stream re-establishes after the *first* connection

    def __init__(self, server_url: str, username: str, password: str, verify=True):
        """Store the server URL, Basic Auth credentials, and TLS `verify=` value (see
        `network.requestConfig.VERIFY` - this listener opens its own raw `requests.get()`
        outside that module's mixins, so it needs the same treatment passed in explicitly)
        for the eventual connection."""
        super().__init__()
        self._server_url = server_url
        self._username = username
        self._password = password
        self._verify = verify
        self._running = True
        self._ever_connected = False

    def stop(self):
        """Ask the thread's run loop to exit and quit the underlying QThread."""
        self._running = False
        self.quit()

    def run(self):
        """Thread entry point: connect to GET /events and emit events until stopped.

        Loops while ``_running``. Each iteration opens a streaming, Basic-Auth
        GET to ``{server_url}/events`` (10s connect timeout, 65s read timeout
        — comfortably above the server's 30s heartbeat, so a half-open
        connection surfaces as ReadTimeout and triggers a reconnect) and, once
        connected, emits ``reconnected`` (skipped the very first time — that
        initial connection races the caller's own startup fetch, not a resync)
        before reading the stream line by line in the SSE wire format: a blank
        line resets the current event type back to ``"message"``, a line
        starting with ``:`` is a comment and is ignored, an ``event:`` line
        updates the current event type, and a ``data:`` line JSON-decodes its
        payload and emits ``eventReceived(event_type, data)`` — a JSON decode
        failure on that line is silently swallowed rather than raised. If
        ``_running`` turns false while reading, the method returns
        immediately, ending the thread. Any other exception (e.g. a dropped
        connection) is caught broadly; if the listener hasn't been stopped, it
        sleeps 5 seconds and the outer loop reconnects by opening a fresh
        stream.
        """
        while self._running:
            try:
                with requests.get(
                    f"{self._server_url}/events",
                    auth=(self._username, self._password),
                    stream=True,
                    verify=self._verify,
                    # Read timeout must exceed the server's 30s heartbeat interval:
                    # a half-open connection (no FIN/RST) then raises ReadTimeout
                    # instead of blocking iter_lines() forever, letting the outer
                    # loop reconnect.
                    timeout=(10, 65),
                ) as resp:
                    resp.raise_for_status()
                    if self._ever_connected:
                        self.reconnected.emit()
                    self._ever_connected = True
                    event_type = "message"
                    for raw in resp.iter_lines():
                        if not self._running:
                            return
                        if not raw:
                            event_type = "message"
                            continue
                        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                        if line.startswith(":"):
                            continue
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                self.eventReceived.emit(event_type, json.loads(data_str))
                            except (json.JSONDecodeError, ValueError):
                                pass
            except Exception:
                if self._running:
                    time.sleep(5)
