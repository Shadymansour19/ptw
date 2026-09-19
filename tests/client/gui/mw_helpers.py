"""Test doubles for the MainWindow action-handler tests.

Everything a handler in `windows/MainWindow.py` talks to at its edges is replaced here:
the confirmation dialogs (`QMessageBox`, `QInputDialog`, the project's own dialog classes)
are swapped in the module namespace for doubles whose outcome the test dictates, and the
`ClientRequests` methods are swapped for recorders that hand the callback a canned reply.
Nothing here touches the network or opens a real modal.
"""

from datetime import datetime, timedelta

from PyQt6.QtWidgets import QDialog, QMessageBox

import windows.MainWindow as MW
import tables.TablePTWs as TP
from network.clientRequests import ClientRequests
from models.Isolation import IC
from models.User import UserRoles
from ptw_factory import make_ic, ic_approval

FROZEN = "2026-09-19 10:30:00"                 # what the handler tests freeze datetime.now() at
FROZEN_TS = "19/09/2026 10:30:00"              # ... in the app's own timestamp format
NOW = datetime(2026, 9, 19, 10, 30, 0)

ACCEPTED = QDialog.DialogCode.Accepted
REJECTED = QDialog.DialogCode.Rejected


# ---- ClientRequests recorder ----------------------------------------------------------------

def record_requests(monkeypatch, *names, **results):
    """Replace each named `ClientRequests` method with a recorder.

    Every call appends `(name, loggedUser, positional_args, kwargs_without_callback)` to the
    returned list. If the handler passed a `callback`, it is called synchronously with
    `(None, results.get(name))`; a synchronous call returns `None` (no error). Names given
    only in `results` are patched too.
    """
    log = []

    def make(name):
        def stub(loggedUser, *args, callback=None, **kwargs):
            log.append((name, loggedUser, args, kwargs))
            if callback is not None:
                callback(None, results.get(name))
            return None
        return staticmethod(stub)

    for name in set(names) | set(results):
        assert hasattr(ClientRequests, name), name
        monkeypatch.setattr(ClientRequests, name, make(name))
    return log


def only_call(log, name):
    """The single recorded request, which must be `name`; returns (loggedUser, args, kwargs)."""
    assert len(log) == 1, log
    got, user, args, kwargs = log[0]
    assert got == name, log
    return user, args, kwargs


# ---- QMessageBox / QInputDialog doubles -----------------------------------------------------

class FakeMessageBox(QMessageBox):
    """Stand-in for `QMessageBox` inside windows.MainWindow / tables.TablePTWs.

    `exec_result` is what every `exec()` (instance or `question()`) returns; `click_label`
    names the `addButton()` button that `clickedButton()` reports (the theme/language
    restart prompt); `on_exec` is called with the box right before it "closes", so a test
    can tick a checkbox the handler attached. `shown` records, at exec() time, the title,
    text and attached-checkbox label of every box built by hand - read that rather than the
    box itself, whose widgets belong to the handler's stack frame. `warnings` / `questions`
    collect the static calls so a test can assert what the user was told.
    """

    exec_result = QMessageBox.StandardButton.Yes
    click_label = None
    on_exec = None
    warnings: list = []
    questions: list = []
    infos: list = []
    shown: list = []

    @classmethod
    def reset(cls):
        cls.exec_result = QMessageBox.StandardButton.Yes
        cls.click_label = None
        cls.on_exec = None
        cls.warnings = []
        cls.questions = []
        cls.infos = []
        cls.shown = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._labelled = {}

    def addButton(self, *args):
        btn = super().addButton(*args)
        if args and isinstance(args[0], str):
            self._labelled[args[0]] = btn
        return btn

    def exec(self):
        if FakeMessageBox.on_exec is not None:
            FakeMessageBox.on_exec(self)
        checkbox = self.checkBox()
        FakeMessageBox.shown.append(dict(title=self.windowTitle(), text=self.text(),
                                         checkbox=checkbox.text() if checkbox is not None else None))
        return FakeMessageBox.exec_result

    def clickedButton(self):
        return self._labelled.get(FakeMessageBox.click_label)

    @staticmethod
    def question(parent, title, text, *args, **kwargs):
        FakeMessageBox.questions.append((title, text))
        return FakeMessageBox.exec_result

    @staticmethod
    def warning(parent, title, text, *args, **kwargs):
        FakeMessageBox.warnings.append((title, text))
        return QMessageBox.StandardButton.Ok

    @staticmethod
    def information(parent, title, text, *args, **kwargs):
        FakeMessageBox.infos.append((title, text))
        return QMessageBox.StandardButton.Ok


class FakeInputDialog:
    """Stand-in for `QInputDialog` inside windows.MainWindow: `getText` /
    `getMultiLineText` return `(text, ok)` from the class attributes and log the prompt."""

    text = ''
    ok = True
    calls: list = []

    @classmethod
    def reset(cls):
        cls.text, cls.ok, cls.calls = '', True, []

    @classmethod
    def answer(cls, text, ok=True):
        cls.text, cls.ok = text, ok

    @staticmethod
    def getText(parent, title, label, *args, **kwargs):
        FakeInputDialog.calls.append((title, label))
        return FakeInputDialog.text, FakeInputDialog.ok

    @staticmethod
    def getMultiLineText(parent, title, label, *args, **kwargs):
        FakeInputDialog.calls.append((title, label))
        return FakeInputDialog.text, FakeInputDialog.ok


def install_prompts(monkeypatch):
    """Swap `QMessageBox` (MainWindow and TablePTWs namespaces) and `QInputDialog`
    (MainWindow) for the doubles above, reset to 'Yes / OK, empty text'."""
    FakeMessageBox.reset()
    FakeInputDialog.reset()
    monkeypatch.setattr(MW, 'QMessageBox', FakeMessageBox)
    monkeypatch.setattr(TP, 'QMessageBox', FakeMessageBox)
    monkeypatch.setattr(MW, 'QInputDialog', FakeInputDialog)


# ---- project dialog doubles -----------------------------------------------------------------

def fake_dialog(monkeypatch, name, result=ACCEPTED, **canned):
    """Replace `windows.MainWindow.<name>` with a dialog double.

    The double records every construction in `cls.instances` as `(args, kwargs)`,
    `exec()` returns `result`, and each `canned` entry becomes either a zero-argument
    method returning the value (keys starting with `get`) or a plain attribute.
    """
    class Double:
        instances = []

        def __init__(self, *args, **kwargs):
            Double.instances.append((args, kwargs))
            for key, value in canned.items():
                if key.startswith('get'):
                    setattr(self, key, (lambda v: (lambda: v))(value))
                else:
                    setattr(self, key, value)

        def exec(self):
            return result

    Double.__name__ = f'Fake{name}'
    assert hasattr(MW, name), name
    monkeypatch.setattr(MW, name, Double)
    return Double


# ---- IC fixtures in every lifecycle status -----------------------------------------------------

ISSUING_OK = ic_approval(UserRoles.ISSUING)

_STATUS_FIELDS = {
    IC.Status.REQUESTED: dict(),
    IC.Status.RETURNED: dict(approvals=[ic_approval(UserRoles.ISSUING, action=IC.ApprovalActions.RETURNED)]),
    IC.Status.APPROVED: dict(approvals=[ISSUING_OK]),
    IC.Status.ISOLATE_CONFIRMING: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo'),
    IC.Status.PENDING: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved'),
    IC.Status.ACTIVE: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved',
                           isolate_isolator='iso'),
    IC.Status.DEISOLATE_CONFIRMING: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved',
                                         isolate_isolator='iso', deisolate_requestor='user_turbo'),
    IC.Status.CLOSING: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved',
                            isolate_isolator='iso', deisolate_requestor='user_turbo', deisolate_issuing_action='Approved'),
    IC.Status.SANCTIONED: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved',
                               isolate_isolator='iso', sanction_isolator='iso'),
    IC.Status.CLOSED: dict(approvals=[ISSUING_OK], isolate_requestor='user_turbo', isolate_issuing_action='Approved',
                           isolate_isolator='iso', deisolate_requestor='user_turbo', deisolate_issuing_action='Approved',
                           deisolate_isolator='iso'),
}

ALL_IC_STATUSES = list(_STATUS_FIELDS)


def ic_in(status: IC.Status, **over) -> IC:
    """An IC whose `getStatus()` is exactly `status` (asserted), with `over` applied on top."""
    fields = dict(_STATUS_FIELDS[status])
    fields.update(over)
    ic = make_ic(**fields)
    assert ic.getStatus() == status, (status, ic.getStatus())
    return ic


def shift_ago(hours: int) -> datetime:
    return NOW - timedelta(hours=hours)
