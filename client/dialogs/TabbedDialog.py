"""Shared tabbed-dialog infrastructure used by DialogPTW/DialogIC.

Owns the mechanics common to both dialogs: the colored tab bar of icon+label
TabButtons driving a QStackedWidget, the Back/Next/Finish/Cancel button row, and
tab-bar recoloring with automatically readable text/icon colors. Subclasses embed
these pieces into their own layout and supply the actual tab content.
"""

from functools import partial

from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtGui import QColor, QCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QDialog, QWidget, QHBoxLayout, QStackedWidget, QPushButton,
                              QGraphicsOpacityEffect)
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
        Back/Next buttons' enabled state) synced to the stack;
      - `self.btnFAB`, a floating action button pinned above the Back/Next/Finish/Cancel
        row (see `_updateFabPosition`) that fades to `_FAB_MIN_OPACITY` when the cursor is
        far from it and eases back to fully solid as the cursor nears it (see
        `_updateFabProximity` - same proximity effect as MainWindow's own FAB). Hidden by
        default; a subclass overrides `updateFabForTab()` to call `_setFabAction(icon,
        tooltip, callback)` for whichever of its tabs has an "add new" action (hiding it,
        via `_hideFab()`, for every other tab) - re-run automatically on every tab switch.
        A single shared Ctrl+N shortcut runs whatever action is currently configured (a
        no-op on a tab with none), so every tab's "add new" action is reachable the same
        way regardless of which one it is.

    Subclasses still own their overall QDialog layout, window flags/title, and the
    `stack.currentChanged` wiring (connect it to `stackTabChanged` and call it once after
    all tabs are added, exactly as before).
    """

    # See _updateFabProximity(): the FAB fades to _FAB_MIN_OPACITY once the cursor is
    # _FAB_FADE_RADIUS px or further from it, and eases back to fully solid as the
    # cursor comes within _FAB_SOLID_RADIUS. Kept in sync with MainWindow's own FAB.
    _FAB_PROXIMITY_CHECK_INTERVAL_MS = 60
    _FAB_SOLID_RADIUS = 40
    _FAB_FADE_RADIUS = 80
    _FAB_MIN_OPACITY = 0.3

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

        # Floating action button - same look/proximity-fade behavior as MainWindow's FAB
        # (see class-level _FAB_* constants above). Built before subclasses assemble their
        # own layout, so it isn't yet on top of the tab pages/button row it floats over -
        # showEvent() below raises it once everything else exists, and positions it using
        # btnCancel's own geometry since the button row's height isn't otherwise known here.
        self.btnFAB = QPushButton(self)
        self.btnFAB.setFixedSize(60, 60)
        self.btnFAB.setIconSize(QSize(32, 32))
        self.btnFAB.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 30px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.btnFAB.clicked.connect(self.btnFABHandler)
        self._fabCallback = None
        self.btnFAB.hide()  # shown per-tab by updateFabForTab(), once a subclass has one to offer

        # One shared shortcut for whichever FAB action the current tab has configured
        # (a no-op via btnFABHandler if none is set) - so every tab's "add new" action
        # is reachable the same way, not just by clicking the floating button.
        self._fabShortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self._fabShortcut.activated.connect(self.btnFABHandler)

        self._fabOpacityEffect = QGraphicsOpacityEffect(self.btnFAB)
        self.btnFAB.setGraphicsEffect(self._fabOpacityEffect)
        self._fabOpacityEffect.setOpacity(self._FAB_MIN_OPACITY)
        self._fabProximityTimer = QTimer(self)
        self._fabProximityTimer.setInterval(self._FAB_PROXIMITY_CHECK_INTERVAL_MS)
        self._fabProximityTimer.timeout.connect(self._updateFabProximity)
        self._fabProximityTimer.start()

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
        self.updateFabForTab(self.stack.currentWidget())

    def updateFabForTab(self, tab: QWidget):
        """Hook for subclasses: decide whether/how the floating action button should
        appear for `tab`, the now-current stack page - call `_setFabAction()` for a tab
        that has an "add new" action, `_hideFab()` otherwise. Re-run automatically by
        `stackTabChanged()` on every tab switch; a subclass whose FAB eligibility can
        also change without a tab switch (e.g. toggling some other control) should call
        it again itself when that happens. Base implementation just hides the FAB."""
        self._hideFab()

    def _setFabAction(self, icon: str, tooltip: str, callback):
        """Configure and show the floating action button for the current tab: `icon` (a
        qtawesome icon name, rendered white for contrast against the button's blue), the
        hover `tooltip` (the shared "[Ctrl+N]" hint is appended automatically, since
        every tab's FAB action shares that one shortcut), and the no-arg `callback` to
        run on click. Called by a subclass's `updateFabForTab()` override."""
        self.btnFAB.setIcon(qta.icon(icon, color='white'))
        self.btnFAB.setToolTip(f"{tooltip} [Ctrl+N]")
        self._fabCallback = callback
        self.btnFAB.show()

    def _hideFab(self):
        """Hide the floating action button - the current tab has no FAB action. Called by
        a subclass's `updateFabForTab()` override."""
        self.btnFAB.hide()
        self._fabCallback = None

    def btnFABHandler(self):
        """Slot for the floating action button's click: run whichever callback the
        current tab configured via `_setFabAction()` (a no-op if none is set, though in
        practice the button is hidden whenever that's the case)."""
        if self._fabCallback:
            self._fabCallback()

    def _updateFabPosition(self):
        """Reposition the floating action button just above the Back/Next/Finish/Cancel
        row - found via btnCancel's own position, since that row's exact height isn't
        otherwise known here - and to the corresponding side of the dialog: the right
        for English, the left for Arabic, mirroring MainWindow's own FAB placement."""
        margin = 16
        x = margin if is_rtl() else self.width() - self.btnFAB.width() - margin
        y = self.btnCancel.y() - self.btnFAB.height() - margin
        self.btnFAB.move(x, max(0, y))

    def resizeEvent(self, event):
        """Qt resize event override: reposition the floating action button whenever the
        dialog is resized."""
        self._updateFabPosition()
        super().resizeEvent(event)

    def showEvent(self, event):
        """Qt show event override: raise the floating action button above every tab page
        (it's built before subclasses assemble their own layout, so plain creation-order
        z-stacking wouldn't otherwise put it on top) and position it now that the
        dialog's real layout geometry is available."""
        self.btnFAB.raise_()
        self._updateFabPosition()
        super().showEvent(event)

    def done(self, r):
        """Qt override for QDialog's shared accept/reject/close path: stop the FAB's
        proximity-polling timer before the dialog actually closes."""
        self._fabProximityTimer.stop()
        super().done(r)

    def _updateFabProximity(self):
        """Polled by `_fabProximityTimer`: fade the floating action button toward
        `_FAB_MIN_OPACITY` as the cursor moves away from it, and back to fully solid as
        the cursor comes within `_FAB_SOLID_RADIUS` - proximity rather than just direct
        hover, since QSS `:hover` alone only reacts once the cursor is already over the
        button. Same formula as MainWindow._updateFabProximity."""
        if not self.isVisible():
            return
        cursor = self.mapFromGlobal(QCursor.pos())
        rect = self.btnFAB.geometry()
        dx = max(rect.left() - cursor.x(), 0, cursor.x() - rect.right())
        dy = max(rect.top() - cursor.y(), 0, cursor.y() - rect.bottom())
        distance = (dx ** 2 + dy ** 2) ** 0.5
        if distance <= self._FAB_SOLID_RADIUS:
            opacity = 1.0
        elif distance >= self._FAB_FADE_RADIUS:
            opacity = self._FAB_MIN_OPACITY
        else:
            span = self._FAB_FADE_RADIUS - self._FAB_SOLID_RADIUS
            frac = (distance - self._FAB_SOLID_RADIUS) / span
            opacity = 1.0 - frac * (1.0 - self._FAB_MIN_OPACITY)
        self._fabOpacityEffect.setOpacity(opacity)
