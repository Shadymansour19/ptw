from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QToolButton, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                              QLabel, QScrollArea, QApplication)
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor
import qtawesome as qta


def lightenColor(color: QColor, amount: float = 0.4) -> QColor:
    return QColor(
        int(color.red()   + (255 - color.red())   * amount),
        int(color.green() + (255 - color.green()) * amount),
        int(color.blue()  + (255 - color.blue())  * amount),
    )


class TabButton(QToolButton):
    TAB_BTN_STYLE = """
        QToolButton {
            background: transparent;
            border: none;
            border-radius: 12px;
            padding: 10px 20px;
            color: palette(window-text);
        }

        QToolButton:hover {
            background: rgba(128, 128, 128, 0.15);
        }

        QToolButton:pressed {
            background: rgba(128, 128, 128, 0.30);
        }

        QToolButton[selected="true"] {
            background: palette(highlight);
            color: palette(highlighted-text);
            font-weight: bold;
        }
    """

    def __init__(self, parent = None, text = '', icon = ''):
        super().__init__(parent)
        self.setText(text)
        self.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        self.iconName = icon
        highlighted_text = QApplication.palette().color(QPalette.ColorRole.HighlightedText).name()
        self.icon = qta.icon(icon) if icon else None
        self.selection_icon = qta.icon(icon, color=highlighted_text) if icon else None
        self.setStyleSheet(TabButton.TAB_BTN_STYLE)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(32, 32))

    def setIcon(self, isSelected):
        super().setIcon(self.selection_icon if isSelected and self.selection_icon else self.icon if self.icon else QIcon())

    def setHighlightColor(self, bgColor: QColor, textColor: QColor):
        self.selection_icon = qta.icon(self.iconName, color=textColor.name()) if self.iconName else None
        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
                padding: 10px 20px;
                color: palette(window-text);
            }}

            QToolButton:hover {{
                background: rgba(128, 128, 128, 0.15);
            }}

            QToolButton:pressed {{
                background: rgba(128, 128, 128, 0.30);
            }}

            QToolButton[selected="true"] {{
                background: {bgColor.name()};
                color: {textColor.name()};
                font-weight: bold;
            }}
        """)


class TimelineEntry(QWidget):
    DOT_SIZE = 14
    RAIL_WIDTH = 20
    GAP = 26

    def __init__(self, color: QColor, contentWidget: QWidget, isLast: bool = False, parent=None):
        super().__init__(parent)
        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(10)

        rail = QWidget()
        rail.setFixedWidth(self.RAIL_WIDTH)
        railLyt = QVBoxLayout(rail)
        railLyt.setContentsMargins(0, 4, 0, 0)
        railLyt.setSpacing(0)

        dot = QFrame()
        dot.setFixedSize(self.DOT_SIZE, self.DOT_SIZE)
        dot.setStyleSheet(f"background-color: {color.name()}; border-radius: {self.DOT_SIZE // 2}px;")
        railLyt.addWidget(dot, alignment=Qt.AlignmentFlag.AlignHCenter)

        if not isLast:
            line = QFrame()
            line.setFixedWidth(3)
            line.setStyleSheet("background-color: #AAAAAA;")
            railLyt.addWidget(line, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            railLyt.addStretch(1)

        # The gap lives in the content column (not as a margin on this row) so the
        # rail's line stretches through it uninterrupted, connecting to the next dot.
        contentCol = QWidget()
        contentColLyt = QVBoxLayout(contentCol)
        contentColLyt.setContentsMargins(0, 0, 0, 0)
        contentColLyt.setSpacing(0)
        contentColLyt.addWidget(contentWidget)
        if not isLast:
            contentColLyt.addSpacing(self.GAP)

        lyt.addWidget(rail)
        lyt.addWidget(contentCol, stretch=1)


class Timeline(QScrollArea):
    def __init__(self, entries: list[tuple[QColor, QWidget]], emptyText: str, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(4, 4, 4, 4)
        lyt.setSpacing(0)

        if not entries:
            lyt.addWidget(QLabel(emptyText))
        else:
            for i, (color, contentWidget) in enumerate(entries):
                lyt.addWidget(TimelineEntry(color, contentWidget, isLast=(i == len(entries) - 1)))
        lyt.addStretch(1)

        self.setWidget(container)
