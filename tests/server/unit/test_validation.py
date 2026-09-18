"""PTW.validate(), updateRequirements(), requiredAttachs(), requiredDocsToPrint()."""

import pytest

from models.PTW import PTW
from ptw_factory import make_ptw, ptw_payload

SPARK = 'Electrical / Mechanical Spark'


def test_minimal_cold_work_is_valid():
    assert make_ptw().validate() is None


@pytest.mark.parametrize("field", ['type', 'requestor', 'department', 'location', 'area_class', 'equipment', 'description'])
def test_each_core_field_is_required(field):
    err = make_ptw(**{field: ''}).validate()
    assert err == f"{field.capitalize()} cannot be empty"


def test_needs_mos_or_miwi():
    assert make_ptw(mos=None, miwi=None).validate() == "Must have either MOS or MIWI"
    assert make_ptw(mos=None, miwi='MIWI-001.pdf').validate() is None


def test_spark_permit_requires_the_spark_hazard_and_its_gas_tests():
    assert make_ptw(PTW.Types.SP).validate() == f"Hazard '{SPARK}' is required for Spark permits"
    assert make_ptw(PTW.Types.SP, hazards=[SPARK]).validate() == f"'{SPARK}' requires control 'Initial Gas Test'"
    assert make_ptw(PTW.Types.SP, hazards=[SPARK], controls=['Initial Gas Test']).validate() == \
           f"'{SPARK}' requires control 'Continuous Gas Test'"
    assert make_ptw(PTW.Types.SP, hazards=[SPARK], controls=['Initial Gas Test', 'Continuous Gas Test']).validate() is None


def test_cold_work_restrictions():
    assert make_ptw(PTW.Types.CW, tools=['Power Tools']).validate() == "Tool 'Power Tools' is not allowed for Cold permits"
    assert make_ptw(PTW.Types.CW, tools=['Non-Ex Tools']).validate() == "Tool 'Non-Ex Tools' is not allowed for Cold permits"
    assert make_ptw(PTW.Types.CW, hazards=[SPARK]).validate() == f"Hazard '{SPARK}' is not allowed for Cold permits"
    assert make_ptw(PTW.Types.CS, tools=['Power Tools']).validate() == "Tool 'Power Tools' is not allowed for Confined Space permits"


def test_hot_work_allows_power_tools_but_wants_the_checklist_attached():
    ptw = make_ptw(PTW.Types.HT, tools=['Power Tools'])
    assert ptw.requiredAttachs() == ['Power Tools Checklist']
    assert ptw.validate() == "Missing required attachment: Power Tools Checklist"
    ptw.attachs = ['Power Tools Checklist.pdf']
    assert ptw.validate() is None
    ptw.attachs = ['Power Tools Checklist-v2.pdf']       # prefix must be followed by the extension dot
    assert ptw.validate() == "Missing required attachment: Power Tools Checklist"


def test_control_cascade_to_attachment():
    ptw = make_ptw(hazards=['Hazardous Substance'])
    assert ptw.validate() == "'Hazardous Substance' requires control 'MSDS'"
    ptw.controls = ['MSDS']
    assert ptw.validate() == "Missing required attachment: MSDS"
    ptw.attachs = ['MSDS.pdf']
    assert ptw.validate() is None


def test_unknown_free_text_items_are_tolerated():
    assert make_ptw(tools=['Hand Tools', 'Ladder'], hazards=['Bees'], controls=['Net']).validate() is None


class TestUpdateRequirements:
    def test_spark_type_auto_selects_hazard_and_cascades_controls(self):
        ptw = make_ptw(PTW.Types.SP)
        ptw.updateRequirements()
        assert SPARK in ptw.hazards
        assert 'Initial Gas Test' in ptw.controls and 'Continuous Gas Test' in ptw.controls
        assert ptw.validate() is None

    def test_cold_type_strips_restricted_items(self):
        ptw = make_ptw(PTW.Types.CW, tools=['Power Tools', 'Hand Tools'], hazards=[SPARK])
        ptw.updateRequirements()
        assert 'Power Tools' not in ptw.tools and 'Hand Tools' in ptw.tools
        assert SPARK not in ptw.hazards

    def test_tool_cascades_risk_titles(self):
        ptw = make_ptw(tools=['Hand Tools', 'Camera'])
        ptw.updateRequirements()
        assert set(ptw.risks) >= {'Use of Hand Tools', 'Use of Camera'}

    def test_idempotent(self):
        ptw = make_ptw(PTW.Types.SP, hazards=['Noise', 'Dropped Objects'])
        ptw.updateRequirements()
        snapshot = (list(ptw.tools), list(ptw.hazards), list(ptw.controls), list(ptw.risks))
        ptw.updateRequirements()
        assert snapshot == (ptw.tools, ptw.hazards, ptw.controls, ptw.risks)


class TestRequiredDocsToPrint:
    def test_baseline(self):
        assert make_ptw().requiredDocsToPrint() == ['toolbox', 'audit']

    def test_hot_and_spark_share_the_hot_work_card(self):
        assert 'swc-hot-work' in make_ptw(PTW.Types.HT).requiredDocsToPrint()
        assert 'swc-hot-work' in make_ptw(PTW.Types.SP).requiredDocsToPrint()
        assert 'swc-hot-work' not in make_ptw(PTW.Types.CW).requiredDocsToPrint()

    def test_gas_test_form_follows_the_control(self):
        assert 'gas-test' in make_ptw(controls=['Initial Gas Test']).requiredDocsToPrint()

    def test_type_and_hazard_cards(self):
        assert 'swc-confined-space' in make_ptw(PTW.Types.CS).requiredDocsToPrint()
        assert 'swc-excavation' in make_ptw(PTW.Types.EX).requiredDocsToPrint()
        assert 'swc-excavation' in make_ptw(hazards=['Excavation']).requiredDocsToPrint()
        assert 'swc-working-at-height' in make_ptw(hazards=['Working at Height']).requiredDocsToPrint()
        assert 'swc-mechanical-lifting' in make_ptw(controls=['Lifting Plan']).requiredDocsToPrint()
        assert 'swc-work-near-water' in make_ptw(hazards=['Overside Working']).requiredDocsToPrint()
        assert 'swc-mobile-equipment' in make_ptw(hazards=['Moving Vehicle']).requiredDocsToPrint()

    def test_isolation_cards_come_as_a_pair(self):
        docs = make_ptw(linked_ics=['3']).requiredDocsToPrint()
        assert docs[-2:] == ['swc-energy-isolation', 'swc-de-isolation']
        docs = make_ptw(isolations=[{'type': 'Mechanical', 'tag': 'XV-1', 'description': ''}]).requiredDocsToPrint()
        assert 'swc-energy-isolation' in docs


def test_payload_survives_construction_without_status_columns():
    """A JSON payload never carries approval_status/running_status; they're derived."""
    data = ptw_payload()
    ptw = PTW(data)
    assert ptw.approval_status == PTW.ApprovalStatus.UNDER_REVIEW
    assert ptw.running_status == PTW.RunningStatus.NOT_RUNNING
    assert ptw.id is None
