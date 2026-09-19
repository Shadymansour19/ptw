"""reports/ArabicText.py: script detection, base-direction rule and ReportLab font-run markup."""

import re

import pytest

from reports.ArabicText import containsArabic, bidiVisual, isRtlBase, pdfMarkup, REGULAR_FONT_NAME, BOLD_FONT_NAME

ARABIC = 'مضخة'                       # "pump"
PRESENTATION_FORMS = re.compile(r'^[ﭐ-﷿ﹰ-﻿]+$')
FONT_TAG = re.compile(r'<font name="([^"]+)">(.*?)</font>')


class TestDetection:
    @pytest.mark.parametrize('text, expected', [
        ('', False), (None, False), ('Pump P-101', False), ('123 !?', False),
        (ARABIC, True), ('Pump ' + ARABIC, True), ('۱۲', True),      # Extended Arabic-Indic digits
    ])
    def test_contains_arabic(self, text, expected):
        assert containsArabic(text) is expected

    @pytest.mark.parametrize('text, expected', [
        ('', False), ('Hello', False), ('123', False), ('!!!', False),
        (ARABIC, True),
        (ARABIC + ' Hello', True),               # first strong character wins ...
        ('Hello ' + ARABIC, False),
        ('123 ' + ARABIC, True),                 # ... digits and punctuation are skipped over
        ('(P-101) ' + ARABIC, False),            # the Latin letter in the tag comes first
    ])
    def test_is_rtl_base(self, text, expected):
        assert isRtlBase(text) is expected


class TestBidiVisual:
    def test_latin_is_untouched(self):
        assert bidiVisual('Pump P-101') == 'Pump P-101'
        assert bidiVisual('') == ''

    def test_arabic_is_reshaped_into_presentation_forms_and_reversed(self):
        visual = bidiVisual(ARABIC)
        assert visual != ARABIC
        assert len(visual) == len(ARABIC)
        assert PRESENTATION_FORMS.match(visual), visual
        # visual order is reversed: the logical last letter (ة) is drawn first, in its final form
        assert visual[0] == 'ﺔ'      # ARABIC LETTER TEH MARBUTA FINAL FORM


class TestPdfMarkup:
    def test_empty_and_none_pass_through(self):
        assert pdfMarkup('') == ''
        assert pdfMarkup(None) is None

    def test_plain_text_is_only_xml_escaped(self):
        assert pdfMarkup('Weld <bracket> & grind') == 'Weld &lt;bracket&gt; &amp; grind'
        assert '<font' not in pdfMarkup('P-101')

    def test_pure_arabic_is_one_regular_font_run(self):
        markup = pdfMarkup(ARABIC)
        runs = FONT_TAG.findall(markup)
        assert len(runs) == 1
        font, body = runs[0]
        assert font == REGULAR_FONT_NAME
        assert body == bidiVisual(ARABIC)
        assert markup == f'<font name="{REGULAR_FONT_NAME}">{body}</font>'

    def test_bold_uses_the_bold_face(self):
        assert FONT_TAG.findall(pdfMarkup(ARABIC, bold=True))[0][0] == BOLD_FONT_NAME

    def test_mixed_text_keeps_latin_runs_outside_the_font_tag(self):
        markup = pdfMarkup(f'Pump {ARABIC} P-101')
        runs = FONT_TAG.findall(markup)
        assert len(runs) == 1
        assert PRESENTATION_FORMS.match(runs[0][1].strip())
        # LTR base paragraph: Latin runs stay where they were, in the style's own font
        assert markup.startswith('Pump ')
        assert markup.endswith('</font>P-101')
        assert re.sub(FONT_TAG, '', markup).split() == ['Pump', 'P-101']
        assert markup.count('<font') == 1

    def test_neutral_characters_do_not_split_a_run(self):
        # digits and spaces adjacent to Arabic letters travel inside the same font run
        markup = pdfMarkup(f'{ARABIC} 101 {ARABIC}')
        runs = FONT_TAG.findall(markup)
        assert len(runs) == 1
        assert '101' in runs[0][1]
        assert markup == f'<font name="{REGULAR_FONT_NAME}">{runs[0][1]}</font>'

    def test_two_arabic_runs_around_a_latin_word(self):
        markup = pdfMarkup(f'{ARABIC} Pump {ARABIC}')
        runs = FONT_TAG.findall(markup)
        assert len(runs) == 2
        assert re.sub(FONT_TAG, '', markup).strip() == 'Pump'

    def test_markup_characters_inside_arabic_text_are_escaped(self):
        markup = pdfMarkup(f'{ARABIC} <& Pump')
        assert '&lt;' in markup and '&amp;' in markup
        assert '<&' not in markup
