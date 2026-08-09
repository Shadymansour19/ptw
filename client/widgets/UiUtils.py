"""Small reusable UI building blocks and color helpers shared across the client's
dialogs: colored tab-bar buttons (`TabButton`) and the vertical timeline used to render
approval/isolation history panes (`Timeline`/`TimelineEntry`, see DialogPTW/DialogIC via
TabbedDialog)."""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QToolButton, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                              QLabel, QScrollArea, QSizePolicy)
from PyQt6.QtGui import QFont, QIcon, QColor
import qtawesome as qta


def lightenColor(color: QColor, amount: float = 0.4) -> QColor:
    """Blend `color` toward white by `amount` (0 = unchanged, 1 = pure white) and
    return the resulting QColor."""
    return QColor(
        int(color.red()   + (255 - color.red())   * amount),
        int(color.green() + (255 - color.green()) * amount),
        int(color.blue()  + (255 - color.blue())  * amount),
    )


def bestForegroundColor(bgColor: QColor) -> QColor:
    """Pick whichever of black/white reads better as text/icon color on top of `bgColor`,
    based on its perceived luminance (ITU-R BT.601 weights). Used to keep TabButton text
    legible against arbitrary, data-driven bar colors instead of a manually curated one."""
    luminance = 0.299 * bgColor.red() + 0.587 * bgColor.green() + 0.114 * bgColor.blue()
    return QColor('black') if luminance > 140 else QColor('white')


class TabButton(QToolButton):
    """Tab-bar button used by TabbedDialog: shows an optional qtawesome icon plus text,
    toggles a bold "selected" look, and can be recolored to contrast an arbitrary bar
    background via `setHighlightColor()`."""

    # Default look before any bar color has been applied (see setHighlightColor below) -
    # tracks the OS palette live, same as any other unstyled/theme-aware widget would.
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

    # Filled in by setHighlightColor() once a bar color is known. Unlike TAB_BTN_STYLE,
    # colors here are literal hex (not palette(...) keywords), since they're picked to
    # contrast a specific bar background rather than to follow the OS theme.
    _HIGHLIGHT_STYLE_TEMPLATE = """
        QToolButton {{
            background: transparent;
            border: none;
            border-radius: 12px;
            padding: 10px 20px;
            color: {unselectedText};
        }}

        QToolButton:hover {{
            background: rgba(128, 128, 128, 0.15);
        }}

        QToolButton:pressed {{
            background: rgba(128, 128, 128, 0.30);
        }}

        QToolButton[selected="true"] {{
            background: {selectedBg};
            color: {selectedText};
            font-weight: bold;
        }}
    """

    def __init__(self, parent = None, text = '', icon = ''):
        """Build the button with the given `text` and optional qtawesome `icon` name,
        using the default (palette-following) unselected style until a bar color is
        applied via `setHighlightColor()`."""
        super().__init__(parent)
        self.setText(text)
        self.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        self.iconName = icon
        self.icon = qta.icon(icon) if icon else None
        self.selection_icon = self.icon
        self.setStyleSheet(TabButton.TAB_BTN_STYLE)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(32, 32))
        # QToolButton defaults to a fixed horizontal size (clamped to its sizeHint).
        # MinimumExpanding keeps that computed size as a floor (so it never shrinks
        # narrower than its icon/text/padding need) while letting it grow to fill extra
        # bar width - see TabbedDialog.addTab, which gives each button an equal stretch.
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

    def setIcon(self, isSelected):
        """Push the appropriate pre-colored icon for the button's current state: the
        selected-state icon when `isSelected` is True (falling back to the unselected
        one if none was set), the unselected icon otherwise, or a null icon if neither
        was set."""
        super().setIcon(self.selection_icon if isSelected and self.selection_icon else self.icon if self.icon else QIcon())

    def setHighlightColor(self, selectedBgColor: QColor, selectedTextColor: QColor, unselectedTextColor: QColor):
        """Recolor this button's text and both icon states: `selectedBgColor`/`selectedTextColor`
        for when it's the active tab, `unselectedTextColor` otherwise. Callers (see
        TabbedDialog.setTabBarColor) are expected to have already picked all three for
        readability against the bar's actual background."""
        self.icon = qta.icon(self.iconName, color=unselectedTextColor.name()) if self.iconName else None
        self.selection_icon = qta.icon(self.iconName, color=selectedTextColor.name()) if self.iconName else None
        self.setStyleSheet(self._HIGHLIGHT_STYLE_TEMPLATE.format(
            unselectedText=unselectedTextColor.name(),
            selectedBg=selectedBgColor.name(),
            selectedText=selectedTextColor.name(),
        ))
        # The stylesheet above repaints the text immediately, but the actual QIcon shown
        # by the widget is only ever pushed via setIcon() below - without this, the old
        # (stale-colored) icon stays on screen until something else happens to call
        # setIcon() again, e.g. the next tab switch. Reapply it now, for whichever
        # selected/unselected state currently applies, so icon and text recolor together.
        self.setIcon(isSelected=bool(self.property("selected")))


class TimelineEntry(QWidget):
    """One row of a `Timeline`: a colored dot on a vertical rail (connected to the next
    entry's dot by a line, unless it's the last one) alongside an arbitrary content
    widget."""

    DOT_SIZE = 14
    RAIL_WIDTH = 20
    GAP = 26

    def __init__(self, color: QColor, contentWidget: QWidget, isLast: bool = False, parent=None):
        """Lay out the rail (dot, plus a connecting line unless `isLast`) next to
        `contentWidget`, with `color` filling the dot."""
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
    """Scrollable vertical timeline of colored dots and content widgets, used to render
    approval/isolation history panes (see DialogPTW/DialogIC via TabbedDialog). Shows
    `emptyText` in place of the rail when there are no entries."""

    def __init__(self, entries: list[tuple[QColor, QWidget]], emptyText: str, parent=None):
        """Build a `TimelineEntry` row for each `(color, contentWidget)` pair in
        `entries`, in order, or show `emptyText` if `entries` is empty."""
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
