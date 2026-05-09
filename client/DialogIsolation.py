from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *

from PTWData import Isolation, PTWData


class FuzzyHighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pattern = ''

    def setPattern(self, pattern):
        self.pattern = pattern.upper()

    def paint(self, painter, option, index):
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
        highlight_color = QColor('yellow')

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


class FuzzyCompleter(QCompleter):
    # Return '' so QCompleter doesn't re-filter our pre-filtered model.
    def splitPath(self, _path):
        return ['']


class DialogIsolation(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Isolation")
        self.setModal(True)
        self.isolation = None

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.typeCombo = QComboBox()
        self.boxTag = QComboBox()
        self.boxDescription = QTextEdit()
        
        self.typeCombo.addItems([t.value for t in Isolation.Types])

        self._all_tags = list(PTWData.ALL_ISOLATIONS.keys())
        self._tagsForType = {t.value: [] for t in Isolation.Types}
        for iso in PTWData.ALL_ISOLATIONS.values():
            self._tagsForType[iso.type.value].append(iso.tag)

        self.boxTag.setEditable(True)

        self._completer_model = QStringListModel(self._all_tags)
        completer = FuzzyCompleter(self._completer_model, self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.boxTag.setCompleter(completer)
        self._highlight_delegate = FuzzyHighlightDelegate()
        completer.popup().setItemDelegate(self._highlight_delegate)
        self.typeCombo.currentTextChanged.connect(self._on_type_changed)
        self.boxTag.lineEdit().textEdited.connect(self._filter_tags)
        self.boxTag.currentIndexChanged.connect(lambda: self._on_tag_selected(self.boxTag.currentText()))
        completer.activated.connect(self._on_tag_selected)
        self.boxTag.lineEdit().editingFinished.connect(
            lambda: self._on_tag_selected(self.boxTag.currentText())
        )
        self._on_type_changed()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        lyt.addRow("Type:", self.typeCombo)
        lyt.addRow("Tag:", self.boxTag)
        lyt.addRow("Description:", self.boxDescription)
        lyt.addWidget(btns)

    def _on_type_changed(self, _=None):
        tags = self._tagsForType[self.typeCombo.currentText()]
        self.boxTag.clear()
        self.boxTag.addItems(tags)
        self.boxTag.setCurrentIndex(0)
        self._completer_model.setStringList(tags)

    def _on_tag_selected(self, tag):
        isolation = PTWData.ALL_ISOLATIONS.get(tag)
        self.boxDescription.setText(isolation.description if isolation else '')

    def _filter_tags(self, text):
        self._highlight_delegate.setPattern(text)
        tags = self._tagsForType[self.typeCombo.currentText()]
        if text:
            pat = text.upper()
            tags = [t for t in tags if self._fuzzy_match(pat, t.upper())]
        self._completer_model.setStringList(tags)
        self.boxTag.completer().complete()

    @staticmethod
    def _fuzzy_match(pattern, text):
        it = iter(text)
        return all(c in it for c in pattern)

    def getIsolation(self):
        return self.isolation

    def accept(self):
        type = self.typeCombo.currentText()
        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, "Invalid Input", "Please select a tag or enter a new one.")
            return
        if not description:
            QMessageBox.warning(self, "Invalid Input", "Please enter a description.")
            return

        self.isolation = Isolation(type=type, tag=tag, description=description)
        super().accept()
