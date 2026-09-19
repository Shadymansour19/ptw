"""client/widgets/: the reusable building blocks (donut chart, combo boxes, busy overlay,
tab-button/timeline helpers, the PTW risk-items table) plus the pure-logic parts of the
P&ID/Wiring highlighter. Nothing here touches the network, OCR, or a real diagram.
"""

import math
import os

import pytest
from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent, QSizeF
from PyQt6.QtGui import QColor, QKeyEvent, QImage
from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QFrame, QToolButton

from models.PTW import RiskItem, RiskAssessment
from models.Isolation import IC
from widgets.DonutChart import DonutChart, DonutSegment, _Ring, _LegendRow
from widgets.CheckableComboBox import CheckableComboBox
from widgets.SearchableComboBox import SearchableComboBox
from widgets import RefreshOverlay as overlay_module
from widgets.RefreshOverlay import RefreshOverlay
from widgets.UiUtils import lightenColor, bestForegroundColor, TabButton, Timeline, TimelineEntry
from widgets import RiskPreview as risk_module
from widgets.RiskPreview import RiskItemsTable, RiskAssessmentPreview, _RiskPreviewDialog, _RiskPreviewWidget
from widgets import PidWiringHighlighter as pid

pytestmark = pytest.mark.gui

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TEST_DATA = os.path.join(ROOT, 'test_data')


# ====================================================================================
# DonutChart
# ====================================================================================

def segments(*counts, callbacks=None):
    callbacks = callbacks or [None] * len(counts)
    return [DonutSegment(f'S{i}', n, QColor('#2a78d6'), cb) for i, (n, cb) in enumerate(zip(counts, callbacks))]


class TestDonutChart:
    def test_set_segments_rebuilds_the_legend_with_percentages(self, qtbot):
        chart = DonutChart('PTWs')
        qtbot.addWidget(chart)
        chart.setSegments(segments(1, 3))
        rows = [chart._legendLayout.itemAt(i).widget() for i in range(chart._legendLayout.count())]
        rows = [r for r in rows if isinstance(r, _LegendRow)]
        assert [r.text() for r in rows] == ['  S0 — 1 (25%)', '  S1 — 3 (75%)']
        assert chart._legendLayout.count() == 4                     # stretch + 2 rows + stretch
        chart.setSegments(segments(5))
        assert chart._legendLayout.count() == 3
        assert chart._ring._segments[0].count == 5

    def test_ring_angles_are_proportional_and_clockwise_from_the_top(self, qtbot):
        ring = _Ring()
        qtbot.addWidget(ring)
        ring.setSegments(segments(1, 3, 0))
        angles, total = ring._cumulativeAngles()
        assert total == 4
        assert [(round(s), round(span)) for s, span, _ in angles] == [(0, 90), (90, 270), (360, 0)]

    def test_empty_chart_has_no_segments_and_still_paints(self, qtbot):
        ring = _Ring()
        qtbot.addWidget(ring)
        ring.resize(300, 300)
        ring.setSegments(segments(0, 0))
        assert ring._cumulativeAngles() == ([], 0)
        assert ring._segmentAt(QPointF(150, 35)) is None
        assert not ring.grab().isNull()                              # paintEvent's "No Data" path runs

    def test_hit_testing_only_inside_the_ring_band(self, qtbot):
        ring = _Ring()
        qtbot.addWidget(ring)
        ring.resize(300, 300)                    # side 296: outer r 148, inner r 81.4, center (150,150)
        ring.setSegments(segments(1, 3))
        assert ring._segmentAt(QPointF(150, 150)) is None            # the hole
        assert ring._segmentAt(QPointF(150, 0)) is None              # outside
        top_right = QPointF(150 + 115 * math.sin(math.radians(45)), 150 - 115 * math.cos(math.radians(45)))
        assert ring._segmentAt(top_right)[1].label == 'S0'
        assert ring._segmentAt(QPointF(150, 265))[1].label == 'S1'   # straight down = 180 degrees

    def test_clicking_a_segment_or_its_legend_row_fires_its_callback(self, qtbot):
        hits = []
        chart = DonutChart()
        qtbot.addWidget(chart)
        chart.setSegments(segments(1, 3, callbacks=[lambda: hits.append('S0'), None]))
        rows = [chart._legendLayout.itemAt(i).widget() for i in range(chart._legendLayout.count())]
        rows = [r for r in rows if isinstance(r, _LegendRow)]
        assert rows[0].isEnabled() and not rows[1].isEnabled()     # no callback -> inert legend row
        rows[0].click()
        assert hits == ['S0']

        ring = _Ring()
        qtbot.addWidget(ring)
        ring.resize(300, 300)
        ring.show()
        ring.setSegments(segments(1, 3, callbacks=[lambda: hits.append('ring-S0'), None]))
        qtbot.mouseClick(ring, Qt.MouseButton.LeftButton, pos=QPoint(231, 69))    # 45 degrees -> S0
        qtbot.mouseClick(ring, Qt.MouseButton.LeftButton, pos=QPoint(150, 265))   # 180 degrees -> S1, no callback
        assert hits == ['S0', 'ring-S0']

    def test_hover_shows_tooltip_only_for_clickable_segments(self, qtbot):
        ring = _Ring()
        qtbot.addWidget(ring)
        ring.resize(300, 300)
        ring.show()
        ring.setSegments(segments(1, 3, callbacks=[lambda: None, None]))
        qtbot.mouseMove(ring, QPoint(231, 69))
        qtbot.waitUntil(lambda: ring._hoverIndex == 0, timeout=1000)
        assert ring.toolTip() == 'S0: 1 (25%)'
        qtbot.mouseMove(ring, QPoint(150, 265))
        qtbot.waitUntil(lambda: ring._hoverIndex == 1, timeout=1000)
        assert ring.toolTip() == ''


# ====================================================================================
# CheckableComboBox
# ====================================================================================

class TestCheckableComboBox:
    @pytest.fixture
    def combo(self, qtbot):
        c = CheckableComboBox()
        qtbot.addWidget(c)
        c.setItems(['b', 'a', 'c'])
        return c

    def texts(self, combo):
        return [combo._model.item(i).text() for i in range(combo._model.rowCount())]

    def test_set_items_sorts_checks_everything_and_pins_select_all(self, combo):
        assert self.texts(combo) == ['(Select All)', 'a', 'b', 'c']
        assert combo.checkedItems() == {'a', 'b', 'c'} and not combo.isFiltering()
        assert combo._summary_text == '(All)'
        combo.setItems(['z', 'y'], sort=False)
        assert self.texts(combo) == ['(Select All)', 'z', 'y']

    def test_set_checked_only_updates_summary_and_emits(self, combo, qtbot):
        with qtbot.waitSignal(combo.filterChanged, timeout=1000):
            combo.setCheckedOnly({'a'})
        assert combo.checkedItems() == {'a'} and combo.isFiltering() and combo._summary_text == 'a'
        combo.setCheckedOnly({'a', 'b'})
        assert combo._summary_text == '(2/3)'
        combo.setCheckedOnly(set())
        assert combo._summary_text == '(None)' and combo.checkedItems() == set()
        assert combo._model.item(0).checkState() == Qt.CheckState.Unchecked
        combo.setCheckedOnly({'a', 'b', 'c'})
        assert combo._summary_text == '(All)' and combo._model.item(0).checkState() == Qt.CheckState.Checked

    def test_pressing_rows_toggles_them_and_select_all_toggles_all(self, combo):
        fired = []
        combo.filterChanged.connect(lambda: fired.append(1))
        combo._handleItemPressed(combo._proxy.index(2, 0))          # 'b'
        assert combo.checkedItems() == {'a', 'c'} and combo._summary_text == '(2/3)'
        assert combo._model.item(0).checkState() == Qt.CheckState.Unchecked
        combo._handleItemPressed(combo._proxy.index(0, 0))          # (Select All) while partial -> all on
        assert combo.checkedItems() == {'a', 'b', 'c'}
        combo._handleItemPressed(combo._proxy.index(0, 0))          # again -> all off
        assert combo.checkedItems() == set() and combo._summary_text == '(None)'
        assert fired == [1, 1, 1]
        assert combo._skip_hide                                       # the popup is kept open after a press
        combo.hidePopup()
        assert not combo._skip_hide

    def test_search_narrows_visible_rows_and_select_all_acts_on_them_only(self, combo):
        combo._onSearchTextChanged('a')
        assert combo._visibleRows() == [1]
        combo._handleItemPressed(combo._proxy.index(0, 0))          # (Select All) -> unchecks only 'a'
        assert combo.checkedItems() == {'b', 'c'}
        combo._onSearchTextChanged('')
        assert combo._visibleRows() == [1, 2, 3]
        assert combo._model.item(0).checkState() == Qt.CheckState.Unchecked

    def test_display_function_translates_labels_but_filters_on_values(self, qtbot):
        c = CheckableComboBox()
        qtbot.addWidget(c)
        c.setItems(['Prod', 'Mech'], display={'Prod': 'Production', 'Mech': 'Mechanical'}.get)
        assert self.texts(c) == ['(Select All)', 'Mechanical', 'Production']   # sorted by displayed text
        assert c.checkedItems() == {'Mech', 'Prod'}
        c.setCheckedOnly({'Prod'})
        assert c._summary_text == 'Production'

    def test_reset_preserves_unchecked_values_and_checks_new_ones(self, combo):
        combo.setCheckedOnly({'b', 'c'})
        combo.setItems(['a', 'b', 'd'])
        assert combo.checkedItems() == {'b', 'd'}
        combo.setItems(['a', 'b'], preserve_selection=False)
        assert combo.checkedItems() == {'a', 'b'}


# ====================================================================================
# SearchableComboBox
# ====================================================================================

class TestSearchableComboBox:
    @pytest.fixture
    def combo(self, qtbot):
        c = SearchableComboBox()
        qtbot.addWidget(c)
        c.setItems(['Pump', 'Valve', 'Compressor'])
        c.show()
        return c

    def test_set_items_selects_the_first_and_feeds_the_completer(self, combo):
        assert combo.count() == 3 and combo.currentText() == 'Pump'
        assert combo._completer_model.stringList() == ['Pump', 'Valve', 'Compressor']
        combo.setItems([])
        assert combo.count() == 0 and combo.currentText() == ''

    @pytest.mark.parametrize('pattern, text, ok', [
        ('AC', 'ABC', True), ('CA', 'ABC', False), ('', 'ABC', True), ('ABCD', 'ABC', False), ('CMP', 'COMPRESSOR', True),
    ])
    def test_fuzzy_match_is_an_ordered_subsequence(self, pattern, text, ok):
        assert SearchableComboBox._fuzzyMatch(pattern, text) is ok

    def test_typing_filters_the_completer_case_insensitively(self, combo, qtbot):
        combo.lineEdit().clear()
        qtbot.keyClicks(combo.lineEdit(), 'cmp')
        assert combo._completer_model.stringList() == ['Compressor']
        assert combo._highlight_delegate.pattern == 'CMP'
        combo.lineEdit().clear()
        qtbot.keyClicks(combo.lineEdit(), 'v')
        assert combo._completer_model.stringList() == ['Valve']
        assert combo.count() == 3                                   # the real item list is untouched

    def test_free_text_and_explicit_selection(self, combo, qtbot):
        combo.setCurrentText('Not In List')
        assert combo.currentText() == 'Not In List'
        with qtbot.waitSignal(combo.itemSelected, timeout=1000) as blocker:
            combo.setCurrentIndex(2)
        assert blocker.args == ['Compressor'] and combo.currentText() == 'Compressor'


# ====================================================================================
# RefreshOverlay
# ====================================================================================

class TestRefreshOverlay:
    @pytest.fixture(autouse=True)
    def reset_manager(self):
        overlay_module._manager.count = 0
        yield
        overlay_module._manager.count = 0

    @pytest.fixture
    def window(self, qtbot):
        w = QWidget()
        w.resize(400, 300)
        edit = QLineEdit(w)
        edit.setObjectName('edit')
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
        edit.setFocus()
        return w

    def test_busy_is_refcounted_and_hides_at_the_next_cycle_boundary(self, window, qtbot):
        overlay = RefreshOverlay(window)
        assert not overlay.isVisible() and overlay_module._manager._overlays[window] is overlay
        overlay.showBusy()
        assert overlay.isVisible() and overlay_module._manager.count == 1
        assert overlay.geometry() == window.rect()
        overlay.showBusy()
        overlay.hideBusy()
        assert overlay_module._manager.count == 1 and overlay.isVisible() and not overlay._pendingHide
        overlay.hideBusy()
        assert overlay_module._manager.count == 0
        assert overlay.isVisible() and overlay._pendingHide        # waits for the typing cycle to finish
        with qtbot.waitSignal(overlay.hidden, timeout=1000):
            overlay._onCycleBoundary()
        assert not overlay.isVisible() and not overlay._pendingHide

    def test_a_new_refresh_cancels_a_queued_hide(self, window):
        overlay = RefreshOverlay(window)
        overlay.showBusy()
        overlay.hideBusy()
        assert overlay._pendingHide
        overlay.showBusy()
        assert not overlay._pendingHide
        overlay._onCycleBoundary()
        assert overlay.isVisible()                                   # still busy, boundary is a no-op
        overlay.hideBusy()
        overlay._onCycleBoundary()
        assert not overlay.isVisible()

    def test_overlay_on_a_hidden_window_hides_immediately(self, qtbot):
        w = QWidget()
        qtbot.addWidget(w)
        overlay = RefreshOverlay(w)
        overlay.showBusy()
        assert overlay_module._manager.count == 1 and not overlay.isVisible()
        with qtbot.waitSignal(overlay.hidden, timeout=1000):
            overlay.hideBusy()
        assert overlay_module._manager.count == 0 and not overlay._pendingHide

    def test_busy_from_one_window_dims_every_visible_window(self, window, qtbot):
        other = QWidget()
        other.resize(200, 100)
        qtbot.addWidget(other)
        other.show()
        qtbot.waitExposed(other)
        overlay = RefreshOverlay(window)
        overlay.showBusy()
        made = overlay_module._manager._overlays.get(other)
        assert isinstance(made, RefreshOverlay) and made.isVisible()  # created on demand for `other`
        overlay.hideBusy()
        overlay._onCycleBoundary()
        made._onCycleBoundary()
        assert not overlay.isVisible() and not made.isVisible()

    def test_overlay_steals_focus_and_swallows_keys_then_restores_focus(self, window, qtbot):
        edit = window.findChild(QLineEdit, 'edit')
        overlay = RefreshOverlay(window)
        overlay.showBusy()
        qtbot.waitUntil(lambda: window.focusWidget() is overlay, timeout=1000)
        qtbot.keyClicks(overlay, 'abc')
        assert edit.text() == ''
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert overlay.event(ev) is True and ev.isAccepted()
        assert overlay.focusNextPrevChild(True) is False
        overlay.hideBusy()
        overlay._onCycleBoundary()
        assert window.focusWidget() is edit

    def test_overlay_tracks_the_window_size(self, window):
        overlay = RefreshOverlay(window)
        window.resize(640, 480)
        assert overlay.geometry() == window.rect()


# ====================================================================================
# UiUtils
# ====================================================================================

class TestUiUtils:
    @pytest.mark.parametrize('rgb, amount, expected', [
        ((0, 0, 0), 0.5, (127, 127, 127)), ((10, 20, 30), 0.0, (10, 20, 30)), ((10, 20, 30), 1.0, (255, 255, 255)),
        ((200, 100, 0), 0.4, (222, 162, 102)),
    ])
    def test_lighten_color(self, rgb, amount, expected):
        assert lightenColor(QColor(*rgb), amount).getRgb()[:3] == expected

    @pytest.mark.parametrize('rgb, expected', [
        ((0, 0, 0), 'white'), ((255, 255, 255), 'black'), ((140, 140, 140), 'white'), ((141, 141, 141), 'black'),
        ((255, 0, 0), 'white'), ((0, 255, 0), 'black'),
    ])
    def test_best_foreground_color_flips_at_the_luminance_threshold(self, rgb, expected):
        assert bestForegroundColor(QColor(*rgb)) == QColor(expected)

    def test_tab_button_recolors_text_and_icon_together(self, qtbot):
        btn = TabButton(text='Risks', icon='fa6s.triangle-exclamation')
        qtbot.addWidget(btn)
        assert btn.text() == 'Risks' and 'palette(window-text)' in btn.styleSheet()
        before = btn.icon
        btn.setProperty('selected', True)
        btn.setHighlightColor(QColor('#112233'), QColor('#ffffff'), QColor('#000000'))
        assert '#112233' in btn.styleSheet() and '#ffffff' in btn.styleSheet() and 'palette(' not in btn.styleSheet()
        assert btn.icon is not before and btn.selection_icon is not btn.icon
        assert not btn.icon.isNull()

    def test_tab_button_without_an_icon_pushes_a_null_icon(self, qtbot):
        btn = TabButton(text='Plain')
        qtbot.addWidget(btn)
        assert btn.icon is None and btn.selection_icon is None
        btn.setIcon(True)
        assert QToolButton.icon(btn).isNull()        # the instance attribute shadows QToolButton.icon()

    def test_timeline_renders_entries_or_the_empty_text(self, qtbot):
        empty = Timeline([], 'Nothing yet')
        qtbot.addWidget(empty)
        labels = [l.text() for l in empty.widget().findChildren(QLabel)]
        assert labels == ['Nothing yet'] and empty.widget().findChildren(TimelineEntry) == []
        full = Timeline([(QColor('red'), QLabel('first')), (QColor('green'), QLabel('second'))], 'Nothing yet')
        qtbot.addWidget(full)
        entries = full.widget().findChildren(TimelineEntry)
        assert len(entries) == 2
        assert [l.text() for l in full.widget().findChildren(QLabel)] == ['first', 'second']
        # every entry but the last draws the connecting line (a second QFrame) under its dot
        rails = [[f for f in e.findChildren(QFrame) if not isinstance(f, QLabel)] for e in entries]
        assert [len(r) for r in rails] == [2, 1]
        assert '#ff0000' in rails[0][0].styleSheet() and '#008000' in rails[1][0].styleSheet()   # dot colors


# ====================================================================================
# RiskPreview: RiskItemsTable
# ====================================================================================

def ri(hazard='Fire', effect='Burns', free='3B', ctrl='Extinguisher', ctrl_a='1A', ev='Low'):
    return RiskItem(hazard, effect, free, ctrl, ctrl_a, ev)


class TestRiskItemsTable:
    def test_table_mirrors_and_mutates_the_live_item_list(self, qtbot):
        items = [ri(), ri(hazard='Noise')]
        table = RiskItemsTable(None, items, readonly=False)
        qtbot.addWidget(table)
        assert table.tbl.rowCount() == 2
        assert [table.tbl.item(0, c).text() for c in range(6)] == ['Fire', 'Burns', '3B', 'Extinguisher', '1A', 'Low']
        assert table.addItem(ri(hazard='Dust')) is True
        assert len(items) == 3 and table.tbl.rowCount() == 3
        got = table.getRiskItems()
        assert [g.hazard for g in got] == ['Fire', 'Noise', 'Dust'] and got[0] is not items[0]

    def test_duplicates_are_rejected_case_and_whitespace_insensitively(self, qtbot):
        items = [ri()]
        table = RiskItemsTable(None, items, readonly=False)
        qtbot.addWidget(table)
        assert table.addItem(ri(hazard='  fire ', effect='BURNS')) is False
        assert len(items) == 1 and table.tbl.rowCount() == 1
        assert table._isDuplicate(ri(), excludeRow=0) is False

    def test_validate_reports_the_first_bad_row(self, qtbot):
        table = RiskItemsTable(None, [ri(), ri(hazard='Noise', free='3b'), ri(hazard='', effect='')], readonly=False)
        qtbot.addWidget(table)
        assert table.validate() == 'Row 2: Free Analysis must be a single digit followed by a single uppercase letter'
        table.tbl.item(1, 2).setText('3B')
        table.tbl.item(1, 4).setText('AA')
        assert table.validate() == 'Row 2: Controlled Analysis must be a single digit followed by a single uppercase letter'
        table.tbl.item(1, 4).setText('1A')
        assert table.validate() == 'Row 3: please fill in all fields'
        table.tbl.removeRow(2)
        assert table.validate() is None

    def test_delete_selected_rows_after_confirmation(self, qtbot, monkeypatch):
        items = [ri(), ri(hazard='Noise'), ri(hazard='Dust')]
        table = RiskItemsTable(None, items, readonly=False)
        qtbot.addWidget(table)
        answers = iter([risk_module.QMessageBox.StandardButton.No, risk_module.QMessageBox.StandardButton.Yes])
        monkeypatch.setattr(risk_module.QMessageBox, 'question', staticmethod(lambda *a, **k: next(answers)))
        table.tbl.selectRow(1)
        table.deleteSelectedRows()
        assert len(items) == 3                                        # declined
        table.deleteSelectedRows()
        assert [i.hazard for i in items] == ['Fire', 'Dust'] and table.tbl.rowCount() == 2

    def test_parse_risk_items_file_validates_rows_and_keeps_source_numbering(self):
        items, errors = RiskItemsTable._parseRiskItemsFile(os.path.join(TEST_DATA, 'test_risk_items.xlsx'))
        # the sheet's columns are in a different order and carry an extra 'Note' column
        assert [i.hazard for i in items] == ['Falling objects', 'Excessive noise', 'Excessive noise', 'Excavation collapse']
        assert (items[1].free_analysis, items[1].ctrl_analysis) == ('2B', '1A')     # upper-cased from '2b'/'1a'
        assert (items[0].effect, items[0].ctrl, items[0].eval) == ('Head/hand injury', 'Hard hat, gloves', 'Low')
        assert errors == ['Row 5: Free/Controlled Analysis must be a digit followed by an uppercase letter',
                          'Row 6: missing required field(s)']

    def test_parse_rejects_a_file_missing_a_required_column(self, tmp_path):
        path = tmp_path / 'bad.csv'
        path.write_text('Hazard,Effect\nFire,Burns\n')
        with pytest.raises(ValueError, match='Missing required column'):
            RiskItemsTable._parseRiskItemsFile(str(path))

    def test_import_from_excel_adds_valid_rows_and_reports_skips(self, qtbot, monkeypatch):
        items = []
        table = RiskItemsTable(None, items, readonly=False)
        qtbot.addWidget(table)
        monkeypatch.setattr(risk_module.QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (os.path.join(TEST_DATA, 'test_risk_items.xlsx'), '')))
        infos = []
        monkeypatch.setattr(risk_module.QMessageBox, 'information', staticmethod(lambda *a: infos.append(a[2])))
        table.importRiskItemsFromExcel()
        assert [i.hazard for i in items] == ['Falling objects', 'Excessive noise', 'Excavation collapse']
        assert table.tbl.rowCount() == 3
        assert infos == ['\n'.join([
            '3 item(s) imported.',
            '1 duplicate(s) skipped.',
            '2 row(s) skipped due to errors:',
            ' • Row 5: Free/Controlled Analysis must be a digit followed by an uppercase letter',
            ' • Row 6: missing required field(s)',
        ])]

    def test_import_cancelled_or_unreadable(self, qtbot, monkeypatch, tmp_path):
        table = RiskItemsTable(None, [], readonly=False)
        qtbot.addWidget(table)
        monkeypatch.setattr(risk_module.QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: ('', '')))
        table.importRiskItemsFromExcel()
        assert table.tbl.rowCount() == 0
        bad = tmp_path / 'bad.csv'
        bad.write_text('Hazard,Effect\nFire,Burns\n')
        monkeypatch.setattr(risk_module.QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: (str(bad), '')))
        warned = []
        monkeypatch.setattr(risk_module.QMessageBox, 'warning', staticmethod(lambda *a: warned.append(a[1:])))
        table.importRiskItemsFromExcel()
        assert warned and warned[0][0] == 'Import Failed' and 'Missing required column' in warned[0][1]

    def test_preview_factory_picks_dialog_or_widget_and_hides_editing_when_readonly(self, qtbot):
        ra = RiskAssessment(title='Lifting', risks=[ri()])
        popup = RiskAssessmentPreview(None, ra, readonly=False, popup=True)
        inline = RiskAssessmentPreview(None, ra, readonly=True, popup=False)
        qtbot.addWidget(popup)
        qtbot.addWidget(inline)
        assert isinstance(popup, _RiskPreviewDialog) and isinstance(inline, _RiskPreviewWidget)
        assert popup.windowTitle() == 'Edit mode - Lifting'
        assert popup.table.riskItems is ra.risks and inline.table.riskItems is ra.risks
        assert popup.layout().indexOf(popup.btnAddItems) == -1        # buttons live in a nested row layout
        assert popup.btnAddItems.parent() is popup and inline.btnAddItems.parent() is None
        assert [i.hazard for i in inline.getRiskItems()] == ['Fire']

    def test_finish_blocks_an_invalid_table(self, qtbot, monkeypatch):
        ra = RiskAssessment(title='Lifting', risks=[ri(free='bad')])
        popup = RiskAssessmentPreview(None, ra, readonly=False, popup=True)
        qtbot.addWidget(popup)
        warned = []
        monkeypatch.setattr(risk_module.QMessageBox, 'warning', staticmethod(lambda *a: warned.append(a[2])))
        popup._onFinish()
        assert popup.result() != risk_module.QDialog.DialogCode.Accepted
        assert warned == ['Row 1: Free Analysis must be a single digit followed by a single uppercase letter']
        ra.risks[0].free_analysis = '3B'
        popup.table._updateRow(ra.risks[0], 0)
        popup._onFinish()
        assert popup.result() == risk_module.QDialog.DialogCode.Accepted


# ====================================================================================
# PidWiringHighlighter: pure helpers
# ====================================================================================

class TestPidWiringHighlighterHelpers:
    @pytest.mark.parametrize('rect, expected', [
        ([0.5, 0.5, 0.1, 0.1], [0.485, 0.485, 0.13, 0.13]),           # 15% of the box on each side
        ([0.0, 0.0, 0.1, 0.1], [0.0, 0.0, 0.13, 0.13]),               # clamped at the page's top-left
        ([0.5, 0.5, 0.01, 0.01], [0.495, 0.495, 0.02, 0.02]),         # tiny box: the absolute floor pads it
    ])
    def test_pad_rect(self, rect, expected):
        assert pid._padRect(rect) == pytest.approx(expected)

    def test_pad_rect_never_leaves_the_page(self):
        x, y, w, h = pid._padRect([0.95, 0.95, 0.05, 0.05])
        assert x + w == pytest.approx(1.0) and y + h == pytest.approx(1.0)

    def test_normalize_strips_whitespace_and_case(self):
        assert pid._normalize(' MOV - 101\tA ') == 'mov-101a'
        assert pid._normalize('') == ''

    def test_group_words_into_lines_and_union_box(self):
        data = {
            'text': ['MOV', '', '101', 'V-2'],
            'block_num': [1, 1, 1, 2], 'par_num': [1, 1, 1, 1], 'line_num': [1, 1, 1, 1],
            'left': [10, 0, 40, 100], 'top': [20, 0, 22, 200], 'width': [25, 0, 30, 20], 'height': [10, 0, 8, 10],
        }
        lines = pid._groupWordsIntoLines(data)
        assert [text for text, _ in lines] == ['MOV 101', 'V-2']
        assert pid._unionBox(lines[0][1]) == (10, 20, 60, 10)
        assert pid._unionBox(lines[1][1]) == (100, 200, 20, 10)

    def test_color_for_state(self):
        assert pid._colorForState(IC.IsolationItem.States.OPEN) == (255, 0, 0)
        assert pid._colorForState(IC.IsolationItem.States.CLOSE) == (0, 160, 0)
        assert pid._colorForState('anything else') == (128, 128, 128)
        assert pid._colorForState('') == (128, 128, 128)

    def test_target_size_scales_the_long_side_to_the_render_ceiling(self):
        assert pid._targetSizeForPage(QSizeF(200, 100)) == pid.QSize(4000, 2000)
        assert pid._targetSizeForPage(QSizeF(100, 400)) == pid.QSize(1000, 4000)
        assert pid._targetSizeForPage(QSizeF(0, 0)) == pid.QSize(4000, 4000)

    def test_flatten_on_white_replaces_transparency(self):
        img = QImage(4, 4, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        img.setPixelColor(1, 1, QColor(0, 0, 0))
        flat = pid._flattenOnWhite(img)
        assert not flat.hasAlphaChannel()
        assert flat.pixelColor(0, 0) == QColor('white') and flat.pixelColor(1, 1) == QColor('black')
        opaque = QImage(2, 2, QImage.Format.Format_RGB32)
        assert pid._flattenOnWhite(opaque) is opaque

    def test_burn_in_without_highlights_copies_the_file_unchanged(self, tmp_path):
        src = tmp_path / 'diagram.png'
        img = QImage(20, 20, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        img.save(str(src))
        out = pid.burnInHighlights(str(src), [])
        assert out != str(src) and out.endswith('.png')
        assert open(out, 'rb').read() == src.read_bytes()
        os.remove(out)

    def test_burn_in_image_tints_only_the_highlighted_box(self, tmp_path):
        src = tmp_path / 'diagram.png'
        img = QImage(20, 20, QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.white)
        img.save(str(src))
        out = pid.burnInHighlights(str(src), [IC.Highlight('V-1', 0, [0.5, 0.5, 0.5, 0.5], IC.IsolationItem.States.OPEN)])
        result = QImage(out)
        assert result.size() == img.size()
        assert result.pixelColor(2, 2) == QColor('white')
        tinted = result.pixelColor(17, 17)
        assert tinted.red() == 255 and tinted.green() < 200 and tinted.blue() < 200      # 40% red over white
        os.remove(out)
