"""Reusable editable combo box with fuzzy-match autocomplete that still accepts free
text not present in its item list."""

from PyQt6.QtCore import Qt, QStringListModel, QRect, pyqtSignal
from PyQt6.QtWidgets import (QStyledItemDelegate, QApplication, QStyle, QStyleOptionViewItem,
                              QCompleter, QComboBox)
from PyQt6.QtGui import QFont, QPalette


class _FuzzyHighlightDelegate(QStyledItemDelegate):
    """Item delegate for the completer popup: bolds and highlight-colors the characters
    of each row's text that matched the current fuzzy search pattern, in match order."""

    def __init__(self, parent=None):
        """Initialize the delegate with no active highlight pattern."""
        super().__init__(parent)
        self.pattern = ''

    def setPattern(self, pattern):
        """Set the (uppercased) fuzzy pattern to highlight matches against."""
        self.pattern = pattern.upper()

    def paint(self, painter, option, index):
        """Draw the row's background/selection normally, then overlay its text
        character-by-character, bolding and coloring whichever characters matched the
        pattern as a subsequence (see `_fuzzyMatch`)."""
        text = index.data(Qt.ItemDataRole.DisplayRole) or ''
        if not text or not self.pattern:
            super().paint(painter, option, index)
            return

        matched = set()
        j = 0
        for i, ch in enumerate(text.upper()):
            if j < len(self.pattern) and ch == self.pattern[j]:
                matched.add(i)
                j += 1

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''

        painter.save()
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        is_selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        text_color = opt.palette.highlightedText().color() if is_selected else opt.palette.text().color()
        highlight_color = opt.palette.color(QPalette.ColorRole.Highlight)

        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, opt.widget) + 1
        x = opt.rect.x() + margin
        normal_font = QFont(opt.font)
        bold_font = QFont(opt.font)
        bold_font.setBold(True)

        for i, ch in enumerate(text):
            if i in matched:
                painter.setFont(bold_font)
                painter.setPen(highlight_color)
            else:
                painter.setFont(normal_font)
                painter.setPen(text_color)
            w = painter.fontMetrics().horizontalAdvance(ch)
            painter.drawText(QRect(x, opt.rect.y(), w, opt.rect.height()), Qt.AlignmentFlag.AlignVCenter, ch)
            x += w

        painter.restore()


class _FuzzyCompleter(QCompleter):
    """QCompleter that disables Qt's own prefix filtering, since the popup's model is
    already fuzzy-filtered by `SearchableComboBox._filterItems`."""

    # Return '' so QCompleter doesn't re-filter our pre-filtered model.
    def splitPath(self, _path):
        """Return a single empty path segment so QCompleter matches every row in the
        (already fuzzy-filtered) model instead of re-filtering by prefix."""
        return ['']


class SearchableComboBox(QComboBox):
    """Editable combobox with fuzzy-matching autocomplete that also accepts values not in its list."""

    itemSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        """Set up the editable combo box, its fuzzy-matching completer and highlight
        delegate, and the signal connections that emit `itemSelected` whenever the
        current text is chosen, typed, or committed."""
        super().__init__(parent)
        self._items = []
        self.setEditable(True)

        self._completer_model = QStringListModel(self)
        completer = _FuzzyCompleter(self._completer_model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(completer)
        self._highlight_delegate = _FuzzyHighlightDelegate()
        completer.popup().setItemDelegate(self._highlight_delegate)

        self.lineEdit().textEdited.connect(self._filterItems)
        self.currentIndexChanged.connect(lambda: self.itemSelected.emit(self.currentText()))
        completer.activated.connect(self.itemSelected.emit)
        self.lineEdit().editingFinished.connect(lambda: self.itemSelected.emit(self.currentText()))

    def setItems(self, items):
        """Replace the combo box's contents with `items`, select the first entry, and
        refresh the completer's backing model to match."""
        self._items = list(items)
        self.clear()
        self.addItems(self._items)
        if self._items:
            self.setCurrentIndex(0)
        self._completer_model.setStringList(self._items)

    def _filterItems(self, text):
        """Slot for the line edit's `textEdited` signal: update the popup's highlight
        pattern, narrow the completer's model to items fuzzy-matching `text`, and
        re-trigger the popup so it reflects the new filter immediately."""
        self._highlight_delegate.setPattern(text)
        items = self._items
        if text:
            pat = text.upper()
            items = [t for t in items if self._fuzzyMatch(pat, t.upper())]
        self._completer_model.setStringList(items)
        self.completer().complete()

    @staticmethod
    def _fuzzyMatch(pattern, text):
        """Return True if every character of `pattern` occurs in `text` in the same
        order, as a subsequence - characters need not be contiguous (e.g. "ac" matches
        "abc")."""
        it = iter(text)
        return all(c in it for c in pattern)
