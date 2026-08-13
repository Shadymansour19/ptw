"""Reusable multi-select checkbox combo box: a closed combo box that summarizes how
many of its items are checked, with a searchable, checkbox-per-row popup and a
"(Select All)" pseudo-item pinned to the top."""

from PyQt6.QtCore import Qt, pyqtSignal, QSortFilterProxyModel
from PyQt6.QtWidgets import QComboBox, QStyle, QStylePainter, QStyleOptionComboBox, QLineEdit
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from helper.i18n import t

_SELECT_ALL = "(Select All)"


class _FilterProxyModel(QSortFilterProxyModel):
    """Filter proxy used by the popup's search box: always keeps row 0 (the
    "(Select All)" pseudo-item) visible, filtering normally on every other row."""

    def filterAcceptsRow(self, source_row, source_parent):
        """Accept row 0 unconditionally; delegate filtering to the base class otherwise."""
        if source_row == 0:
            return True
        return super().filterAcceptsRow(source_row, source_parent)


class CheckableComboBox(QComboBox):
    """Multi-select combo box: each popup row has its own checkbox plus a
    "(Select All)" row that checks/unchecks every currently visible row, and a search
    box to filter rows by text. The closed box shows a summary ("(All)", "(None)", the
    single checked item's text, or "(n/total)") instead of a normal current-item text.
    Emits `filterChanged` whenever the checked set changes.

    Every row's *filter value* (what `checkedItems()`/`setCheckedOnly()` operate on,
    and what `setItems()` is keyed by) is stashed in `Qt.ItemDataRole.UserRole`,
    separately from its *displayed text* - so a column can show a translated label
    (e.g. a department name in Arabic) while filtering/comparison still happens on
    the real underlying value, exactly like `TablePTWs._cellFilterText()`'s existing
    "prefer UserRole over the label" pattern for table cells. Passing `display=None`
    (every pre-existing caller) makes value and displayed text the same string, so
    this is fully backward compatible."""

    filterChanged = pyqtSignal()

    def __init__(self, parent=None):
        """Build the popup's checkable item model/proxy and insert the search box and
        "(Select All)" row."""
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._proxy = _FilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModel(self._proxy)
        self._summary_text = t("(All)")
        self.view().pressed.connect(self._handleItemPressed)
        self._skip_hide = False
        self._addSelectAllItem()

        container = self.view().parentWidget()
        self._searchEdit = QLineEdit(container)
        self._searchEdit.setPlaceholderText(t("Search..."))
        self._searchEdit.setClearButtonEnabled(True)
        self._searchEdit.textEdited.connect(self._onSearchTextChanged)
        layout = container.layout()
        layout.insertWidget(layout.indexOf(self.view()), self._searchEdit)

    def showPopup(self):
        """Clear/focus the search box and grow the popup to fit it, then show as usual."""
        super().showPopup()
        self._searchEdit.clear()
        self._searchEdit.setFocus()
        container = self._searchEdit.parentWidget()
        extra = self._searchEdit.sizeHint().height()
        container.resize(container.width(), container.height() + extra)
        self.view().resize(self.view().width(), self.view().height() + extra)

    def paintEvent(self, event):
        """Draw the closed combo box with the selection-summary text in place of the
        (nonexistent) current item's text."""
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = self._summary_text
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._summary_text)

    def _addSelectAllItem(self):
        """Insert the always-checked, always-visible "(Select All)" row at position 0."""
        item = QStandardItem(t(_SELECT_ALL))
        item.setCheckState(Qt.CheckState.Checked)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._model.appendRow(item)

    def _onSearchTextChanged(self, text):
        """Triggered as the user types in the search box: re-filter the popup rows to
        `text` and resync the "(Select All)" checkbox to the now-visible rows."""
        self._proxy.setFilterFixedString(text)
        self._syncSelectAll()

    def _visibleRows(self):
        """Return source-model row indices currently passing the search filter,
        excluding the "(Select All)" row itself."""
        rows = []
        for r in range(self._proxy.rowCount()):
            source_row = self._proxy.mapToSource(self._proxy.index(r, 0)).row()
            if source_row != 0:
                rows.append(source_row)
        return rows

    def _handleItemPressed(self, index):
        """Triggered by clicking a popup row: toggle its check state (or, for the
        "(Select All)" row, toggle every currently visible row to match), keep the
        popup open, refresh the summary text, and emit `filterChanged`."""
        row = self._proxy.mapToSource(index).row()
        item = self._model.item(row)
        new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        if row == 0:
            item.setCheckState(new_state)
            for i in self._visibleRows():
                self._model.item(i).setCheckState(new_state)
        else:
            item.setCheckState(new_state)
            self._syncSelectAll()
        self._skip_hide = True
        self._updateText()
        self.filterChanged.emit()

    def _syncSelectAll(self):
        """Check the "(Select All)" row only if every currently visible row is checked."""
        visible = self._visibleRows()
        all_checked = all(
            self._model.item(i).checkState() == Qt.CheckState.Checked for i in visible
        )
        self._model.item(0).setCheckState(
            Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked
        )

    def hidePopup(self):
        """Suppress one hide request if `_skip_hide` is set (a checkbox click just
        toggled a row and shouldn't also close the popup), otherwise hide normally."""
        if self._skip_hide:
            self._skip_hide = False
            return
        super().hidePopup()

    def setItems(self, values, preserve_selection=True, sort=True, display=None):
        """Replace the popup's rows with one per entry in `values`, all checked by default.

        Args:
            values: the real filter values (e.g. raw English department names),
                even when `display` translates them for what's actually shown.
            preserve_selection: If True, values that match a previously unchecked
                item's value stay unchecked; everything else (including new values)
                is checked. Matches on the value (UserRole), not the displayed
                text, so this still works correctly across a language change.
            sort: If True, sort by the *displayed* text (so e.g. an Arabic list
                sorts the way an Arabic reader expects), not the raw value.
            display: optional value -> display text function. Defaults to
                identity (`str`), so value and displayed text are the same -
                the original behavior, for every caller that doesn't pass this.
        """
        display = display or str
        prev_unchecked = set()
        if preserve_selection:
            for i in range(1, self._model.rowCount()):
                item = self._model.item(i)
                if item.checkState() == Qt.CheckState.Unchecked:
                    prev_unchecked.add(item.data(Qt.ItemDataRole.UserRole))
        self._searchEdit.clear()
        self._proxy.setFilterFixedString("")
        self._model.clear()
        self._addSelectAllItem()
        ordered = sorted(values, key=display) if sort else values
        for value in ordered:
            item = QStandardItem(display(value))
            item.setData(value, Qt.ItemDataRole.UserRole)
            item.setCheckState(
                Qt.CheckState.Unchecked if (preserve_selection and value in prev_unchecked)
                else Qt.CheckState.Checked
            )
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._model.appendRow(item)
        self._syncSelectAll()
        self._updateText()

    def checkedItems(self):
        """Return the set of *values* (not displayed text - see `setItems()`)
        currently checked, excluding "(Select All)"."""
        result = set()
        for i in range(1, self._model.rowCount()):
            item = self._model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(item.data(Qt.ItemDataRole.UserRole))
        return result

    def setCheckedOnly(self, values: set):
        """Check exactly the items whose *value* (not displayed text) is in `values`,
        uncheck every other item, then refresh the summary text and emit `filterChanged`."""
        for i in range(1, self._model.rowCount()):
            item = self._model.item(i)
            item.setCheckState(
                Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in values else Qt.CheckState.Unchecked
            )
        self._syncSelectAll()
        self._updateText()
        self.filterChanged.emit()

    def isFiltering(self):
        """Return True if fewer than all items are currently checked."""
        total = self._model.rowCount() - 1
        return len(self.checkedItems()) < total

    def _updateText(self):
        """Recompute the closed-box summary text from the current checked count -
        the single-checked-item case shows that item's *displayed* text, not its
        (possibly untranslated) underlying value."""
        total = self._model.rowCount() - 1
        checkedRows = [i for i in range(1, self._model.rowCount())
                       if self._model.item(i).checkState() == Qt.CheckState.Checked]
        checked = len(checkedRows)
        if total == 0 or checked == total:
            self._summary_text = t("(All)")
        elif checked == 0:
            self._summary_text = t("(None)")
        elif checked == 1:
            self._summary_text = self._model.item(checkedRows[0]).text()
        else:
            self._summary_text = f"({checked}/{total})"
        self.update()
