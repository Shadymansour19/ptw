from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QStyle, QStylePainter, QStyleOptionComboBox
from PyQt6.QtGui import QStandardItemModel, QStandardItem

_SELECT_ALL = "(Select All)"


class CheckableComboBox(QComboBox):
    filterChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._summary_text = "(All)"
        self.view().pressed.connect(self._handleItemPressed)
        self._skip_hide = False
        self._addSelectAllItem()

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

    def _handleItemPressed(self, index):
        row = index.row()
        item = self._model.item(row)
        new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        if row == 0:
            item.setCheckState(new_state)
            for i in range(1, self._model.rowCount()):
                self._model.item(i).setCheckState(new_state)
        else:
            item.setCheckState(new_state)
            self._syncSelectAll()
        self._skip_hide = True
        self._updateText()
        self.filterChanged.emit()

    def _syncSelectAll(self):
        all_checked = all(
            self._model.item(i).checkState() == Qt.CheckState.Checked
            for i in range(1, self._model.rowCount())
        )
        self._model.item(0).setCheckState(
            Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked
        )

    def hidePopup(self):
        if self._skip_hide:
            self._skip_hide = False
            return
        super().hidePopup()

    def setItems(self, texts, preserve_selection=True):
        prev_unchecked = set()
        if preserve_selection:
            for i in range(1, self._model.rowCount()):
                item = self._model.item(i)
                if item.checkState() == Qt.CheckState.Unchecked:
                    prev_unchecked.add(item.text())
        self._model.clear()
        self._addSelectAllItem()
        for text in sorted(texts):
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
