from PyQt6.QtCore import Qt, pyqtSignal, QSortFilterProxyModel
from PyQt6.QtWidgets import QComboBox, QStyle, QStylePainter, QStyleOptionComboBox, QLineEdit
from PyQt6.QtGui import QStandardItemModel, QStandardItem

_SELECT_ALL = "(Select All)"


class _FilterProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        if source_row == 0:
            return True
        return super().filterAcceptsRow(source_row, source_parent)


class CheckableComboBox(QComboBox):
    filterChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._proxy = _FilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModel(self._proxy)
        self._summary_text = "(All)"
        self.view().pressed.connect(self._handleItemPressed)
        self._skip_hide = False
        self._addSelectAllItem()

        container = self.view().parentWidget()
        self._searchEdit = QLineEdit(container)
        self._searchEdit.setPlaceholderText("Search...")
        self._searchEdit.setClearButtonEnabled(True)
        self._searchEdit.textEdited.connect(self._onSearchTextChanged)
        layout = container.layout()
        layout.insertWidget(layout.indexOf(self.view()), self._searchEdit)

    def showPopup(self):
        super().showPopup()
        self._searchEdit.clear()
        self._searchEdit.setFocus()
        container = self._searchEdit.parentWidget()
        extra = self._searchEdit.sizeHint().height()
        container.resize(container.width(), container.height() + extra)
        self.view().resize(self.view().width(), self.view().height() + extra)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = self._summary_text
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._summary_text)

    def _addSelectAllItem(self):
        item = QStandardItem(_SELECT_ALL)
        item.setCheckState(Qt.CheckState.Checked)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._model.appendRow(item)

    def _onSearchTextChanged(self, text):
        self._proxy.setFilterFixedString(text)
        self._syncSelectAll()

    def _visibleRows(self):
        rows = []
        for r in range(self._proxy.rowCount()):
            source_row = self._proxy.mapToSource(self._proxy.index(r, 0)).row()
            if source_row != 0:
                rows.append(source_row)
        return rows

    def _handleItemPressed(self, index):
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
        visible = self._visibleRows()
        all_checked = all(
            self._model.item(i).checkState() == Qt.CheckState.Checked for i in visible
        )
        self._model.item(0).setCheckState(
            Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked
        )

    def hidePopup(self):
        if self._skip_hide:
            self._skip_hide = False
            return
        super().hidePopup()

    def setItems(self, texts, preserve_selection=True, sort=True):
        prev_unchecked = set()
        if preserve_selection:
            for i in range(1, self._model.rowCount()):
                item = self._model.item(i)
                if item.checkState() == Qt.CheckState.Unchecked:
                    prev_unchecked.add(item.text())
        self._searchEdit.clear()
        self._proxy.setFilterFixedString("")
        self._model.clear()
        self._addSelectAllItem()
        for text in sorted(texts) if sort else texts:
            item = QStandardItem(text)
            item.setCheckState(
                Qt.CheckState.Unchecked if (preserve_selection and text in prev_unchecked)
                else Qt.CheckState.Checked
            )
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._model.appendRow(item)
        self._syncSelectAll()
        self._updateText()

    def checkedItems(self):
        result = set()
        for i in range(1, self._model.rowCount()):
            item = self._model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(item.text())
        return result

    def isFiltering(self):
        total = self._model.rowCount() - 1
        return len(self.checkedItems()) < total

    def _updateText(self):
        total = self._model.rowCount() - 1
        checked = len(self.checkedItems())
        if total == 0 or checked == total:
            self._summary_text = "(All)"
        elif checked == 0:
            self._summary_text = "(None)"
        elif checked == 1:
            self._summary_text = next(iter(self.checkedItems()))
        else:
            self._summary_text = f"({checked}/{total})"
        self.update()
