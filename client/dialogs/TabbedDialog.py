"""Shared tabbed-dialog infrastructure used by DialogPTW/DialogIC.

Owns the mechanics common to both dialogs: the colored tab bar of icon+label
TabButtons driving a QStackedWidget, the Back/Next/Finish/Cancel button row, and
tab-bar recoloring with automatically readable text/icon colors. Subclasses embed
these pieces into their own layout and supply the actual tab content.
"""

from functools import partial

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDialog, QWidget, QHBoxLayout, QStackedWidget, QPushButton
import qtawesome as qta

from widgets.UiUtils import TabButton, lightenColor, bestForegroundColor
from helper.i18n import t, is_rtl


class TabbedDialog(QDialog):
    """
    Base class for dialogs whose content is organized as a colored bar of icon+label
    TabButtons driving a QStackedWidget (see DialogPTW, DialogIC). Provides:

      - `self.tabsContainer` / `self.stack` / `self.tabsBtnsMap`, built here so subclasses
        just place them in their own layout;
      - `addTab()` to register a page and its TabButton together;
      - `setTabBarColor()` to recolor the bar and automatically pick readable text/icon
        colors for both the selected and unselected TabButtons against it;
      - `self.btnBack` / `self.btnNext` / `self.btnFinish` / `self.btnCancel`, wired to page
        the stack and accept/reject the dialog - `bottomButtonsLayout()` assembles them into
        a row for subclasses to drop into their own layout;
      - `stackTabChanged()`, keeping every TabButton's selected/icon state (and the
        Back/Next buttons' enabled state) synced to the stack.

    Subclasses still own their overall QDialog layout, window flags/title, and the
    `stack.currentChanged` wiring (connect it to `stackTabChanged` and call it once after
    all tabs are added, exactly as before).
    """

    def __init__(self, parent=None):
        """Build the empty tab bar, stack, and Back/Next/Finish/Cancel buttons.

        Subclasses call this via super().__init__(), then populate tabs with
        addTab() and place tabsContainer/stack/bottomButtonsLayout() into their
        own layout.
        """
        super().__init__(parent)

        self.tabsContainer = QWidget()
        self._tabsLyt = QHBoxLayout(self.tabsContainer)
        self._tabsLyt.setSpacing(2)
        self._tabsLyt.setContentsMargins(8, 8, 8, 8)

        self.stack = QStackedWidget()
        self.tabsBtnsMap: dict[TabButton, QWidget] = {}

        # qtawesome icons are plain pixmaps - Qt only auto-mirrors its own QStyle-drawn
        # standard icons for RTL, so a directional icon like a chevron has to be picked
        # by hand here to still point the way "back"/"next" actually lie on screen.
        backIcon, nextIcon = ('fa6s.chevron-right', 'fa6s.chevron-left') if is_rtl() else ('fa6s.chevron-left', 'fa6s.chevron-right')
        self.btnBack = QPushButton(qta.icon(backIcon), t('Back'))
        self.btnNext = QPushButton(qta.icon(nextIcon), t('Next'))
        self.btnFinish = QPushButton(qta.icon('fa6s.check'), t('Finish'))
        self.btnCancel = QPushButton(qta.icon('fa6s.xmark'), t('Cancel'))
        self.btnNext.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() + 1))
        self.btnBack.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() - 1))
        self.btnCancel.clicked.connect(self.reject)
        self.btnFinish.clicked.connect(self.accept)

    def bottomButtonsLayout(self) -> QHBoxLayout:
        """Build the Back/Next/Finish/Cancel row for a subclass to add to its own layout.
        Back/Next page the stack; Finish/Cancel accept/reject the dialog."""
        lytBtns = QHBoxLayout()
        lytBtns.setContentsMargins(8, 8, 8, 8)
        lytBtns.addStretch()
        lytBtns.addWidget(self.btnBack, stretch=0)
        lytBtns.addWidget(self.btnNext, stretch=0)
        lytBtns.addWidget(self.btnFinish, stretch=0)
        lytBtns.addWidget(self.btnCancel, stretch=0)
        return lytBtns

    def addTab(self, text: str, icon: str, page: QWidget) -> TabButton:
        """Create a TabButton for `page`, wire it to switch the stack to it, and append it
        to the bar. `page` must already be built - this only registers it as a tab."""
        btn = TabButton(self.stack, text, icon)
        btn.clicked.connect(partial(self.stack.setCurrentWidget, page))
        self.stack.addWidget(page)
        # Equal stretch so the buttons share out any extra bar width instead of leaving it
        # blank (see TabButton's MinimumExpanding size policy, which lets them grow here).
        self._tabsLyt.addWidget(btn, stretch=1)
        self.tabsBtnsMap[btn] = page
        return btn

    def setTabBarColor(self, bgColor: QColor, accentColor: QColor = None):
        """Recolor the bar to `bgColor`, with an accent border and selected-tab background
        (auto-lightened unless `accentColor` is given), and recolor every registered
        TabButton's text/icon so it stays readable: unselected against `bgColor`, selected
        against `accentColor`."""
        accentColor = accentColor or lightenColor(bgColor)
        self.tabsContainer.setStyleSheet(f"""
            QWidget {{
                background: {bgColor.name()};
                border-bottom: 4px solid {accentColor.name()};
                border-right: 4px solid {accentColor.name()};
                border-bottom-right-radius: 20px;
            }}
        """)
        unselectedText = bestForegroundColor(bgColor)
        selectedText = bestForegroundColor(accentColor)
        for btn in self.tabsBtnsMap:
            btn.setHighlightColor(accentColor, selectedText, unselectedText)

    def stackTabChanged(self):
        """Sync tab-button selection state and Back/Next enabled-state to the stack.

        Slot for stack.currentChanged (emitted whenever the current page changes,
        whether via a TabButton click, Alt+N shortcut, or Back/Next): marks the
        TabButton matching the new current index as selected (and every other one
        unselected), refreshes each button's icon/style accordingly, and enables
        Back/Next only when a previous/next page actually exists.
        """
        tabIdx = self.stack.currentIndex()
        for i, btn in enumerate(self.tabsBtnsMap.keys()):
            btn.setProperty("selected", i == tabIdx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setIcon(isSelected=(i == tabIdx))
            btn.update()
        self.btnNext.setEnabled(tabIdx < self.stack.count() - 1)
        self.btnBack.setEnabled(tabIdx > 0)
