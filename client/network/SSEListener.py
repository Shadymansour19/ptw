import json
import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal


class SSEListener(QThread):
    eventReceived = pyqtSignal(str, dict)   # (event_type, data)

    def __init__(self, server_url: str, username: str, password: str):
        super().__init__()
        self._server_url = server_url
        self._username = username
        self._password = password
        self._running = True

    def stop(self):
        self._running = False
        self.quit()

    def run(self):
        while self._running:
            try:
                with requests.get(
                    f"{self._server_url}/events",
                    auth=(self._username, self._password),
                    stream=True,
                    timeout=(10, None),
                ) as resp:
                    resp.raise_for_status()
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
