"""Admin-only server log viewer.

Shows one collapsible panel per log file, lazily fetching a file's content
the first time it is expanded, and offers a log-level filter that
color-codes lines by severity via QTextCursor-based formatting.
"""
import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QScrollArea, QFrame, QTextEdit, QMessageBox)
import qtawesome as qta

from network.clientRequests import ClientRequests
from widgets.CheckableComboBox import CheckableComboBox
from helper.i18n import t

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_LINE_START = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
_LEVEL_RE   = re.compile(r'\[(\w+)\s*\]')

_LEVEL_COLORS = {
    "DEBUG":    ("#808080", False),
    "INFO":     ("#0288d1", False),
    "WARNING":  ("#f57c00", True),
    "ERROR":    ("#d32f2f", True),
    "CRITICAL": ("#ff1744", True),
}

_LEVEL_FMT: dict[str, QTextCharFormat] = {}


def _levelFormats() -> dict[str, QTextCharFormat]:
    """Build (and cache) a QTextCharFormat per log level from `_LEVEL_COLORS`."""
    if _LEVEL_FMT:
        return _LEVEL_FMT
    for level, (color, bold) in _LEVEL_COLORS.items():
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        _LEVEL_FMT[level] = fmt
    return _LEVEL_FMT


def _setColoredText(edit: QTextEdit, content: str, levels: set[str]):
    """Render log text into `edit`, colored by level and filtered to `levels`.

    Replaces the edit's contents entirely. Walks the content line by line
    using a single QTextCursor edit block: each line starting with a
    timestamp (`_LINE_START`) determines a new level (via `_LEVEL_RE`), which
    sets both the QTextCharFormat used to color it and whether it (and any
    non-timestamped continuation lines that follow, e.g. traceback lines)
    should be included at all — lines whose level isn't in `levels` are
    skipped rather than dimmed.
    """
    fmts = _levelFormats()
    default_fmt = QTextCharFormat()

    edit.clear()
    cursor = QTextCursor(edit.document())
    cursor.beginEditBlock()

    include = True
    current_fmt = default_fmt
    first_block = True

    for line in content.splitlines():
        if _LINE_START.match(line):
            m = _LEVEL_RE.search(line)
            level = m.group(1).strip() if m else None
            include = (level in levels) if level else True
            current_fmt = fmts.get(level, default_fmt)

        if include:
            if not first_block:
                cursor.insertBlock()
            cursor.insertText(line, current_fmt)
            first_block = False

    cursor.endEditBlock()


class TabServerLogs(QWidget):
    """Admin-only widget for browsing server log files.

    Lists log files as collapsible panels (lazy-loaded on first expand) with
    a shared log-level filter, backed by `ClientRequests.getLogFiles`/`getLog`
    against the `/logs` endpoint.
    """

    def __init__(self, parent, loggedUser, title: str = "Server Logs"):
        """Build the header (level filter, Refresh button) and the scrollable log-panel container."""
        super().__init__(parent)
        self.loggedUser = loggedUser
        self._rawContent:   dict[str, str]       = {}
        self._contentEdits: dict[str, QTextEdit] = {}

        outerLayout = QVBoxLayout(self)
        outerLayout.setContentsMargins(16, 16, 16, 16)
        outerLayout.setSpacing(10)

        headerRow = QHBoxLayout()
        headerLabel = QLabel(title, font=QFont("Helvetica", 18, QFont.Weight.Bold))
        self._statusLabel = QLabel()
        self._statusLabel.setStyleSheet("color: palette(link);")

        filterLabel = QLabel("Level:")
        self._levelFilter = CheckableComboBox()
        self._levelFilter.setItems(LOG_LEVELS, sort=False, display=t)
        self._levelFilter.setFixedWidth(200)
        self._levelFilter.filterChanged.connect(self._applyFilter)

        btnRefreshLogs = QPushButton(qta.icon('fa6s.rotate-right'), " Refresh")
        btnRefreshLogs.setCursor(Qt.CursorShape.PointingHandCursor)
        btnRefreshLogs.clicked.connect(self.refresh)

        headerRow.addWidget(headerLabel)
        headerRow.addWidget(self._statusLabel)
        headerRow.addStretch()
        headerRow.addWidget(filterLabel)
        headerRow.addWidget(self._levelFilter)
        headerRow.addWidget(btnRefreshLogs)
        outerLayout.addLayout(headerRow)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._containerLayout = QVBoxLayout(self._container)
        self._containerLayout.setContentsMargins(0, 4, 0, 4)
        self._containerLayout.setSpacing(6)
        self._containerLayout.addStretch()

        scroll.setWidget(self._container)
        outerLayout.addWidget(scroll)

    def refresh(self):
        """Slot for the Refresh button clicked signal; reload the list of log files.

        Clears all existing panels and cached content, then re-fetches the
        filename list from the server and adds a collapsed panel per file.
        """
        while self._containerLayout.count() > 1:
            item = self._containerLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rawContent.clear()
        self._contentEdits.clear()
        self._statusLabel.setText("")

        def on_done(err, filenames):
            """Handle the getLogFiles response; add a panel per filename or show an error."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                self._statusLabel.setText(err)
                QMessageBox.warning(self, "Server Logs", f"Failed to refresh logs: {err}")
                return
            if not filenames:
                self._statusLabel.setText("No log files found.")
                return
            for filename in filenames:
                self._addLogEntry(filename)

        self.window()._refreshOverlay.showBusy()
        ClientRequests.getLogFiles(self.loggedUser, callback=on_done)

    def _applyFilter(self):
        """Slot for the level filter combo's filterChanged signal; re-render every loaded panel with the new level set."""
        levels = self._levelFilter.checkedItems()
        for filename, edit in self._contentEdits.items():
            raw = self._rawContent.get(filename)
            if raw is None:
                continue
            _setColoredText(edit, raw, levels)

    def _addLogEntry(self, filename: str):
        """Build and append one collapsible panel (header + content QTextEdit) for a log file."""
        entry = QFrame()
        entry.setFrameShape(QFrame.Shape.StyledPanel)
        entry.setStyleSheet(
            "QFrame { border: 2px solid rgba(128, 128, 128, 0.4); border-radius: 6px; background: rgba(128, 128, 128, 0.2); }"
        )
        entryLayout = QVBoxLayout(entry)
        entryLayout.setContentsMargins(0, 0, 0, 0)
        entryLayout.setSpacing(0)

        headerWidget = QWidget()
        headerWidget.setStyleSheet("QWidget { border: none; background: transparent; }")
        headerWidget.setCursor(Qt.CursorShape.PointingHandCursor)
        headerLayout = QHBoxLayout(headerWidget)
        headerLayout.setContentsMargins(8, 8, 8, 8)
        headerLayout.setSpacing(8)

        toggleBtn = QPushButton(qta.icon('fa6s.chevron-right'), "")
        toggleBtn.setFixedSize(26, 26)
        toggleBtn.setCheckable(True)
        toggleBtn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggleBtn.setStyleSheet("QPushButton { border: none; background: transparent; }")

        filenameLabel = QLabel(filename)
        filenameLabel.setFont(QFont("Helvetica", 14, QFont.Weight.Medium))

        headerLayout.addWidget(toggleBtn)
        headerLayout.addWidget(filenameLabel)
        headerLayout.addStretch()

        contentEdit = QTextEdit()
        contentEdit.setReadOnly(True)
        contentEdit.setFont(QFont("Courier New", 12))
        contentEdit.setVisible(False)
        contentEdit.setMinimumHeight(200)
        contentEdit.setMaximumHeight(600)
        contentEdit.setStyleSheet(
            "QTextEdit { border: none; border-top: 2px solid rgba(128, 128, 128, 0.4); border-radius: 0px; background: transparent; }"
        )

        self._contentEdits[filename] = contentEdit

        def onToggle(checked, fn=filename, edit=contentEdit):
            """Slot for the panel's toggle button toggled signal; expand/collapse its content.

            On expand, shows the content edit and, the first time only,
            lazily fetches the file's content from the server (caching it in
            `self._rawContent`) before rendering it colored/filtered;
            subsequent expands just re-render the cached content. On
            collapse, just hides the content edit.
            """
            if checked:
                toggleBtn.setIcon(qta.icon('fa6s.chevron-down'))
                edit.setVisible(True)
                if fn not in self._rawContent:
                    edit.setPlainText("Loading…")

                    def on_done(err, content):
                        """Handle the getLog response; cache and render the fetched content, or show an error."""
                        self.window()._refreshOverlay.hideBusy()
                        if err:
                            edit.setPlainText(f"Error: {err}")
                            return
                        self._rawContent[fn] = content or ""
                        _setColoredText(edit, self._rawContent[fn], self._levelFilter.checkedItems())

                    self.window()._refreshOverlay.showBusy()
                    ClientRequests.getLog(self.loggedUser, fn, callback=on_done)
                else:
                    _setColoredText(edit, self._rawContent[fn], self._levelFilter.checkedItems())
            else:
                toggleBtn.setIcon(qta.icon('fa6s.chevron-right'))
                edit.setVisible(False)

        toggleBtn.toggled.connect(onToggle)
        headerWidget.mousePressEvent = lambda event: toggleBtn.toggle()
        entryLayout.addWidget(headerWidget)
        entryLayout.addWidget(contentEdit)

        self._containerLayout.insertWidget(self._containerLayout.count() - 1, entry)
