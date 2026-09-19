"""IC, MOS and risk-assessment PDFs plus the logo QR helpers: render to temp files, read back."""

import os

import pytest
import qrcode
from PIL import Image as PILImage
from pypdf import PdfReader

from GlobalData import globalData
from models.PTW import PTW, RiskAssessment, RiskItem
from network.clientRequests import ClientRequests
from reports import ReportGenerator as rg_module
from reports.ReportGenerator import ReportGenerator
from models.User import UserRoles
from ptw_factory import ptw_payload, make_ic, ic_approval

A4_PORTRAIT = (595.28, 841.89)
A4_LANDSCAPE = (841.89, 595.28)
ARABIC_REASON = 'استبدال حشية المضخة الرئيسية'


@pytest.fixture
def opened(monkeypatch):
    """Capture every file the generator would open in a viewer, instead of opening it."""
    files = []
    monkeypatch.setattr(ReportGenerator, 'openPDF', staticmethod(lambda path: files.append(path)))
    monkeypatch.setattr(rg_module.subprocess, 'call', lambda args, *a, **k: files.append(args[-1]))
    monkeypatch.setattr(rg_module.os, 'startfile', lambda path: files.append(path), raising=False)
    yield files
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass


@pytest.fixture
def offline_requests(monkeypatch):
    monkeypatch.setattr(ClientRequests, 'getIcAttachmentNames', staticmethod(lambda user, icid: (None, [])))


@pytest.fixture
def qr_payloads(monkeypatch):
    """Record every payload handed to qrcode (the PNG itself cannot be decoded without an
    extra library, so the QR content is checked at the encoder boundary instead)."""
    payloads = []

    class Recording(qrcode.QRCode):
        def add_data(self, data, *a, **k):
            payloads.append(data)
            return super().add_data(data, *a, **k)

    monkeypatch.setattr(rg_module.qrcode, 'QRCode', Recording)
    return payloads


@pytest.fixture(autouse=True)
def qr_files(monkeypatch):
    """Every QR PNG the generator writes (the reports never delete theirs), removed afterwards."""
    made = []
    original = ReportGenerator._qrWithLogoFromRows

    def recording(basicInfo, filePrefix):
        path = original(basicInfo, filePrefix)
        made.append(path)
        return path

    monkeypatch.setattr(ReportGenerator, '_qrWithLogoFromRows', staticmethod(recording))
    yield made
    for f in made:
        try:
            os.remove(f)
        except OSError:
            pass


def text_of(path):
    return '\n'.join((page.extract_text() or '') for page in PdfReader(path).pages)


def page_texts(path):
    return [(page.extract_text() or '') for page in PdfReader(path).pages]


def flat(text):
    """Whitespace-normalised: table headers wrap ('Lock\nBox#'), so match on words."""
    return ' '.join(text.split())


def fonts_of(path):
    fonts = set()
    for page in PdfReader(path).pages:
        res = page.get('/Resources') or {}
        for f in (res.get('/Font') or {}).values():
            fonts.add(str(f.get_object().get('/BaseFont')))
    return fonts


def assert_page_size(path, expected):
    for i, page in enumerate(PdfReader(path).pages):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        assert abs(w - expected[0]) < 1 and abs(h - expected[1]) < 1, f"page {i} is {w}x{h}"


def make_full_ic(**over):
    data = dict(
        id='5', reason='Gasket replacement', requestor_timestamp='01/09/2026 08:00:00',
        items=[
            {'tag': 'V-101', 'description': 'Suction valve', 'state': 'close', 'lock_num': 'L-1', 'lock_box_num': 'LB-2'},
            {'tag': 'V-102', 'description': 'Discharge valve', 'state': 'open', 'lock_num': '', 'lock_box_num': ''},
        ],
        approvals=[ic_approval(UserRoles.ISSUING)],
        isolate_requestor='user_turbo', isolate_requestor_timestamp='01/09/2026 09:00:00',
        isolate_issuing='issuing', isolate_issuing_timestamp='01/09/2026 09:10:00', isolate_issuing_action='Approved',
        isolate_isolator='isolator_x', isolate_isolator_timestamp='01/09/2026 09:30:00',
    )
    data.update(over)
    ic = make_ic(**data)
    ic.linked_ptws = ['42', '43']
    return ic


class TestIcReport:
    def test_active_ic_report(self, qapp, known_users, offline_requests, opened):
        ic = make_full_ic()
        assert ic.getStatus() == 'Active'
        assert ReportGenerator.icReport(known_users['issuing'], ic) is None
        assert len(opened) == 1 and os.path.basename(opened[0]).startswith('ic-5-') and opened[0].endswith('.pdf')
        assert_page_size(opened[0], A4_LANDSCAPE)
        pages = page_texts(opened[0])
        # summary / items / linked PTWs / approvals / isolation-cycle signatures
        assert len(pages) >= 5
        text = '\n'.join(pages)
        for needle in ('IC#', '5', 'Mechanical', 'Active', 'Gasket replacement', 'Turbo', 'Prod', 'P-101',
                       'User Turbo',                                  # requestor resolved to a display name
                       'V-101', 'Suction valve', 'L-1', 'LB-2', 'V-102', 'open',
                       'PTW #42', 'PTW #43',
                       'Isolate Requested', 'Isolate Approved', 'Isolate Carried Out',
                       'Sanction for Test', 'Re-isolation', 'De-isolation', 'De-isolate Confirmed'):
            assert needle in text, needle
        assert 'isolator_x' in text                                   # unknown username printed verbatim
        assert 'Issuing' in text and 'Long Term' in text and 'No' in text
        for i, page in enumerate(pages, start=1):
            assert f'Page {i} of {len(pages)}' in page

    def test_summary_is_the_first_page_and_items_the_second(self, qapp, known_users, offline_requests, opened):
        ReportGenerator.icReport(known_users['issuing'], make_full_ic())
        pages = page_texts(opened[0])
        assert 'Summery' in pages[0] and 'Status' in pages[0]
        assert 'Isolation Items' in pages[1] and 'Lock Box#' in flat(pages[1])
        assert 'Linked PTWs' in pages[2]
        assert 'Approvals' in pages[3]

    def test_long_term_and_psic_chain(self, qapp, known_users, offline_requests, opened):
        ic = make_full_ic(long_term=True, long_term_reason='Awaiting spare parts', is_psic=True,
                          approvals=[ic_approval(UserRoles.ISSUING), ic_approval(UserRoles.COORDINATOR)])
        ReportGenerator.icReport(known_users['coord'], ic)
        text = text_of(opened[0])
        assert 'Yes - Awaiting spare parts' in text
        # PSIC: every stage of the chain gets a signature slot, approved ones carry a name
        for label in ('Issuing', 'Coordinator', 'PDH', 'PGM', 'SOD', 'DFGM'):
            assert label in text, label
        assert 'Coord' in text

    def test_ic_without_items_or_links_skips_those_sections(self, qapp, offline_requests, opened):
        ic = make_ic(id='9')
        ic.linked_ptws = []
        from conftest import make_user
        assert ReportGenerator.icReport(make_user(), ic) is None
        text = text_of(opened[0])
        assert 'Isolation Items' not in text and 'Linked PTWs' not in text
        assert 'Requested' in text                                    # getStatus() of a brand-new IC
        assert 'User Turbo' not in text                               # nobody in allUsers -> raw username

    def test_arabic_reason_uses_the_bundled_font(self, qapp, known_users, offline_requests, opened):
        ic = make_full_ic(reason=ARABIC_REASON, items=[{'tag': 'V-1', 'description': 'صمام السحب', 'state': 'close'}])
        ReportGenerator.icReport(known_users['issuing'], ic)
        assert any('Naskh' in f or 'Arabic' in f for f in fonts_of(opened[0])), fonts_of(opened[0])


class TestMosReport:
    def test_steps_become_bullets_under_the_ptw_header(self, qapp, opened):
        ReportGenerator.MOSReport('1. Isolate\n2. Drain\n3. Replace gasket', '42', 'Replace pump gasket')
        assert len(opened) == 1 and os.path.basename(opened[0]).startswith('mos-42-')
        assert_page_size(opened[0], A4_PORTRAIT)
        text = text_of(opened[0])
        for needle in ('MOS for PTW# 42', 'Replace pump gasket', 'Method of Statement', '1. Isolate', '2. Drain', '3. Replace gasket'):
            assert needle in text, needle
        assert len(PdfReader(opened[0]).pages) == 1

    def test_empty_mos_produces_nothing(self, qapp, opened):
        assert ReportGenerator.MOSReport('', '42', 'title') is None
        assert ReportGenerator.MOSReport(None, '42', 'title') is None
        assert opened == []

    def test_long_mos_repeats_the_header_on_every_page(self, qapp, opened):
        steps = '\n'.join(f'{i}. Step number {i}' for i in range(1, 121))
        ReportGenerator.MOSReport(steps, '7', 'Long job')
        pages = page_texts(opened[0])
        assert len(pages) >= 3
        for page in pages:
            assert 'MOS for PTW# 7' in page
        assert '120. Step number 120' in pages[-1]

    def test_arabic_title_and_steps(self, qapp, opened):
        ReportGenerator.MOSReport('عزل المضخة\nتفريغ الخط', '3', ARABIC_REASON)
        assert any('Naskh' in f or 'Arabic' in f for f in fonts_of(opened[0]))
        assert 'MOS for PTW# 3' in text_of(opened[0])


def risk_assessment(ptw_id=None, title='Use of Hand Tools', n=1):
    return RiskAssessment(title=title, date='19/09/2026', ptw_id=ptw_id, risks=[
        RiskItem(hazard=f'Pinch point {i}\nSharp edges', effect='Hand injury', free_analysis='3C',
                 ctrl='Wear gloves\n\nInspect tools', ctrl_analysis='1A', eval='Acceptable')
        for i in range(1, n + 1)
    ])


class TestRiskAssessmentReport:
    def test_generic_assessment_table(self, qapp, opened):
        ReportGenerator.riskAssessmentReport(risk_assessment())
        assert len(opened) == 1 and os.path.basename(opened[0]).startswith('risk-None-')
        assert_page_size(opened[0], A4_LANDSCAPE)
        text = flat(text_of(opened[0]))
        for needle in ('Use of Hand Tools', 'Hazard', 'Effect', 'Free Analysis', 'Controlled Analysis', 'Control', 'Evaluation',
                       'Pinch point 1', 'Sharp edges', 'Hand injury', 'Wear gloves', 'Inspect tools', 'Acceptable', '3C', '1A'):
            assert needle in text, needle
        assert 'Specific Risk Assessment' not in text               # no PTW -> generic header
        # 2 hazard + 1 effect + 2 control lines (the blank control line is dropped); pypdf
        # extracts Helvetica's bullet glyph as either the character itself or DEL (0x7f)
        assert text.count('•') + text.count('\x7f') == 5

    def test_ptw_specific_header_and_numbering(self, qapp, opened):
        ReportGenerator.riskAssessmentReport(risk_assessment(ptw_id=7, n=3))
        assert os.path.basename(opened[0]).startswith('risk-7-')
        text = text_of(opened[0])
        assert 'PTW#7 - Specific Risk Assessment' in text
        for row in ('1', '2', '3'):
            assert f'\n{row}\n' in f'\n{text}\n' or f' {row}\n' in text or f'\n{row} ' in text, row
        assert 'Pinch point 3' in text

    def test_severity_and_likelihood_are_split_out_of_the_analysis_code(self, qapp, opened):
        ra = RiskAssessment(title='T', risks=[RiskItem(hazard='H', effect='E', free_analysis='5E', ctrl='C', ctrl_analysis='2B', eval='X')])
        ReportGenerator.riskAssessmentReport(ra)
        lines = [l.strip() for l in text_of(opened[0]).splitlines()]
        for cell in ('5', 'E', '5E', '2', 'B', '2B'):
            assert cell in lines, cell

    def test_blank_analysis_does_not_crash(self, qapp, opened):
        ra = RiskAssessment(title='T', risks=[RiskItem(hazard='H', effect=None, free_analysis=None, ctrl='', ctrl_analysis='', eval=None)])
        assert ReportGenerator.riskAssessmentReport(ra) is None
        assert len(opened) == 1 and 'H' in text_of(opened[0])

    def test_nothing_to_report(self, qapp, opened):
        assert ReportGenerator.riskAssessmentReport(None) is None
        assert ReportGenerator.riskAssessmentReport(RiskAssessment(title='empty')) is None
        assert opened == []

    def test_many_rows_repeat_the_header_row(self, qapp, opened):
        ReportGenerator.riskAssessmentReport(risk_assessment(ptw_id=1, n=25))
        pages = page_texts(opened[0])
        assert len(pages) >= 2
        for page in pages:
            assert 'Free Analysis' in flat(page) and 'PTW#1 - Specific Risk Assessment' in page


class TestQrHelpers:
    def test_ptw_qr_payload_and_png(self, qapp, known_users, qr_payloads, qr_files):
        ptw = PTW(ptw_payload(id=42, type='Hot', equipment='K-201', description='Weld the bracket'))
        path = ReportGenerator._makeQrWithLogo(ptw)
        assert qr_files == [path]
        assert os.path.basename(path).startswith('qr-42-') and path.endswith('.png')
        # no run cycle yet -> no performing authority; every other field is the display form
        assert qr_payloads == ['PTW#: 42\nType: Hot\nStatus: Under Review\nDepartment: Turbo\nRequestor: User Turbo\n'
                               'PA: None\nLocation: Phase VII\nEquipment: K-201\nDescription: Weld the bracket']
        with PILImage.open(path) as img:
            assert img.format == 'PNG' and img.mode == 'RGB'
            w, h = img.size
            assert w == h and w % 20 == 0 and w >= (21 + 4) * 20        # box_size 20, border 2 modules
            # the logo badge is composited over the centre: a white pixel where a QR's
            # dense centre modules would otherwise be black somewhere in the badge area
            assert any(img.getpixel((w // 2 + dx, h // 2 + dy)) == (255, 255, 255)
                       for dx in range(-w // 12, w // 12, 4) for dy in range(-h // 12, h // 12, 4))

    def test_ptw_qr_falls_back_to_none_for_unknown_users(self, qapp, qr_payloads, qr_files):
        ptw = PTW(ptw_payload(id=3, requestor='ghost'))
        ReportGenerator._makeQrWithLogo(ptw)
        assert 'Requestor: None' in qr_payloads[0] and 'PA: None' in qr_payloads[0]

    def test_ic_qr_payload(self, qapp, known_users, qr_payloads, qr_files):
        ic = make_full_ic()
        path = ReportGenerator._makeQrWithLogoIC(ic)
        assert os.path.basename(path).startswith('qr-ic-5-')
        assert qr_payloads == ['IC#: 5\nType: Mechanical\nStatus: Active\nRequestor Dept: Turbo\nExecution Dept: Prod\n'
                               'Requestor: User Turbo\nLocation: Phase VII\nEquipment: P-101\nReason: Gasket replacement']

    @pytest.mark.xfail(strict=True, reason="Known bug: client/reports/ReportGenerator.py:100 only catches "
                       "qrcode.exceptions.DataOverflowError, but qrcode 8.2 raises ValueError('Invalid version (was 41...)') "
                       "from QRCode.best_fit before it ever reaches its own DataOverflowError, so the Q->L->truncate fallback "
                       "is dead and an over-long description crashes the whole PTW/IC report instead of degrading the QR")
    def test_oversized_payload_degrades_error_correction_then_truncates(self, qapp, qr_payloads, qr_files):
        ptw = PTW(ptw_payload(id=1, description='وصف طويل جدا ' * 400))       # multi-byte, far past any QR version
        path = ReportGenerator._makeQrWithLogo(ptw)
        assert os.path.exists(path)
        assert len(qr_payloads) == 3                                          # Q, L, then truncated L
        assert qr_payloads[0] == qr_payloads[1]
        assert len(qr_payloads[2].encode('utf-8')) <= 1400
        assert qr_payloads[0].startswith(qr_payloads[2])                      # a clean prefix, no split code point

    def test_payload_that_fits_at_level_q_is_encoded_once(self, qapp, qr_payloads, qr_files):
        path = ReportGenerator._qrWithLogoFromRows([['A', '1'], ['B', '2']], 'x')
        assert qr_payloads == ['A: 1\nB: 2']
        assert os.path.basename(path).startswith('qr-x-') and qr_files == [path]
