"""DialogPTW: widget <-> model mapping, type-driven requirements, validation on accept."""

import pytest
from PyQt6.QtWidgets import QDialog

from GlobalData import globalData
from models.PTW import PTW
from models.User import UserRoles, UserDepartments
from dialogs import DialogPTW as dialog_module
from dialogs.DialogPTW import DialogPTW
from network.clientRequests import ClientRequests
from conftest import make_user
from ptw_factory import ptw_payload, full_chain, running_cycle
from datetime import datetime

pytestmark = pytest.mark.gui
SPARK = 'Electrical / Mechanical Spark'


@pytest.fixture
def warnings(monkeypatch):
    """Capture QMessageBox.warning calls instead of blocking on a modal."""
    seen = []
    monkeypatch.setattr(dialog_module.QMessageBox, 'warning', staticmethod(lambda *a, **k: seen.append(a)))
    return seen


@pytest.fixture
def new_dialog(qtbot, user, warnings):
    globalData.allMIWIs.extend(['MIWI-100 Pump overhaul.pdf', 'MIWI-007 Valve.pdf'])
    dlg = DialogPTW(None, user, PTW(), None, new=True, readOnly=False, lbl='New PTW')
    qtbot.addWidget(dlg)
    return dlg


def set_combo(combo, data):
    idx = combo.findData(data)
    assert idx >= 0, data
    combo.setCurrentIndex(idx)


class TestNewPtw:
    def test_defaults_come_from_the_logged_user(self, new_dialog, user):
        assert new_dialog.boxDepartment.text() == user.getDepartment()
        assert new_dialog._requestorUsername == user.getUsername()
        assert new_dialog.boxPTWId.text() == ''
        assert new_dialog.boxPTWType.currentData() == 'Cold'
        assert new_dialog.btnMos.isChecked() and not new_dialog.btnMiwi.isChecked()

    def test_collect_data_maps_every_field(self, new_dialog):
        d = new_dialog
        set_combo(d.boxPTWType, 'Hot')
        set_combo(d.boxLocation, 'Scarab')
        set_combo(d.boxAreaClass, 'Non-Hazardous')
        set_combo(d.boxFastTrack, 'Yes')
        d.boxEquipment.setText('K-201')
        d.boxDescription.setPlainText('Weld the bracket')
        d.boxMOS.setPlainText('1. Do it')
        d.btnsTools['Power Tools'].setChecked(True)
        d.btnsHazard['Noise'].setChecked(True)
        d.boxOtherTools.setText('Ladder, Rope / Bucket;')
        d.collectData()
        p = d.ptw
        assert (p.type, p.location, p.area_class, p.fast_track) == ('Hot', 'Scarab', 'Non-Hazardous', True)
        assert (p.equipment, p.description, p.mos, p.miwi) == ('K-201', 'Weld the bracket', '1. Do it', None)
        assert p.department == 'Turbo' and p.requestor == 'user_turbo'
        assert 'Power Tools' in p.tools and {'Ladder', 'Rope', 'Bucket'} <= set(p.tools)
        assert 'Noise' in p.hazards
        assert p.id is None

    def test_switching_to_spark_forces_the_hazard_and_gas_test_controls(self, new_dialog):
        d = new_dialog
        set_combo(d.boxPTWType, 'Spark')
        assert d.btnsHazard[SPARK].isChecked() and not d.btnsHazard[SPARK].isEnabled()
        assert d.btnsControls['Initial Gas Test'].isChecked()
        assert d.btnsControls['Continuous Gas Test'].isChecked()
        # hearing protection cascades from Noise when clicked
        d.btnsHazard['Noise'].click()
        assert d.btnsControls['Hearing Protection'].isChecked()
        # and switching back to Cold strips the spark hazard again and disables the restricted tool
        set_combo(d.boxPTWType, 'Cold')
        assert not d.btnsHazard[SPARK].isChecked() and not d.btnsHazard[SPARK].isEnabled()
        assert not d.btnsTools['Power Tools'].isEnabled()

    def test_miwi_switch(self, new_dialog):
        d = new_dialog
        d.btnMiwi.setChecked(True)
        d.miwiMosSwitch()
        d.boxMiwi.setCurrentText('MIWI-007 Valve.pdf')
        d.boxEquipment.setText('X'); d.boxDescription.setPlainText('Y')
        d.collectData()
        assert d.ptw.miwi == 'MIWI-007 Valve.pdf' and d.ptw.mos is None
        assert d.boxMiwi.count() == 2

    def test_accept_blocks_invalid_and_shows_the_reason(self, new_dialog, warnings):
        d = new_dialog
        d.boxEquipment.setText('')
        d.boxDescription.setPlainText('desc')
        d.boxMOS.setPlainText('mos')
        d.accept()
        assert d.result() != QDialog.DialogCode.Accepted
        assert warnings and warnings[-1][2] == 'Equipment cannot be empty'

    def test_accept_passes_valid_data(self, new_dialog, warnings):
        d = new_dialog
        d.boxEquipment.setText('P-1')
        d.boxDescription.setPlainText('desc')
        d.boxMOS.setPlainText('mos')
        d.accept()
        assert warnings == []
        assert d.result() == QDialog.DialogCode.Accepted
        assert d.attachsToBeUploaded == []

    def test_required_attachment_is_enforced_on_accept(self, new_dialog, warnings):
        d = new_dialog
        d.boxEquipment.setText('P-1'); d.boxDescription.setPlainText('desc'); d.boxMOS.setPlainText('mos')
        d.btnsHazard['Hazardous Substance'].click()      # cascades the MSDS control -> MSDS attachment required
        assert d.btnsControls['MSDS'].isChecked()
        d.accept()
        assert warnings[-1][2] == 'Missing required attachment: MSDS'


class TestViewExisting:
    @pytest.fixture
    def stub_requests(self, monkeypatch):
        monkeypatch.setattr(ClientRequests, 'getPtwAttachmentNames', staticmethod(lambda user, pid: (None, ['MSDS.pdf'])))
        monkeypatch.setattr(ClientRequests, 'getPTWSpecificRiskAssessment', staticmethod(lambda user, pid: (None, None)))

    def test_read_only_view_of_a_running_ptw(self, qtbot, known_users, stub_requests, warnings):
        viewer = known_users['coord']
        ptw = PTW(ptw_payload(id=42, approvals=full_chain('Cold'), run_cycles=[running_cycle(datetime(2026, 9, 1, 8, 0), ia='issuing')],
                              hazards=['Hazardous Substance'], controls=['MSDS']))
        dlg = DialogPTW(None, viewer, ptw, None, new=False, readOnly=True, lbl='PTW #42')
        qtbot.addWidget(dlg)
        assert dlg.boxPTWId.text() == '42'
        assert dlg.boxPerforming.text() == 'User Turbo'          # resolved through globalData.allUsers
        assert dlg.boxRequestor.text() == 'User Turbo'
        assert not dlg.boxPTWType.isEnabled() and dlg.boxDescription.isReadOnly()
        assert all(not b.isEnabled() for b in dlg.btnsTools.values())
        assert dlg.btnsControls['MSDS'].isChecked()
        assert hasattr(dlg, 'tabHistory') and hasattr(dlg, 'tabLinkage')
        assert dlg.stack.indexOf(dlg.tabHistory) >= 0
        assert warnings == []
        # accepting a read-only view never validates
        dlg.accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_new_dialog_has_no_history_tab(self, new_dialog):
        assert not hasattr(new_dialog, 'tabHistory')

    def test_edit_mode_keeps_existing_values(self, qtbot, known_users, stub_requests, warnings):
        ptw = PTW(ptw_payload(id=7, equipment='E-7', tools=['Hand Tools', 'Crowbar'], approvals=[]))
        dlg = DialogPTW(None, known_users['user_turbo'], ptw, None, new=False, readOnly=False, lbl='Edit')
        qtbot.addWidget(dlg)
        assert dlg.boxEquipment.text() == 'E-7'
        assert dlg.btnsTools['Hand Tools'].isChecked()
        assert dlg.boxOtherTools.text() == 'Crowbar'
        assert dlg.boxDepartment.text() == 'Turbo'
        dlg.collectData()
        assert set(dlg.ptw.tools) == {'Hand Tools', 'Crowbar'}
        assert dlg.ptw.id == '7'
