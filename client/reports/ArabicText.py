"""Arabic-aware text prep for PDF reports.

ReportLab has no bidi/text-shaping support of its own - it just draws characters in
strict logical left-to-right sequence, and its built-in fonts (Helvetica et al.) carry
no Arabic glyphs at all. Everything here exists to bridge that gap for any report field
that might hold Arabic text (descriptions, reasons, names - anywhere a user can type
free text, regardless of the app's own UI language):

  - `arabic_reshaper` rewrites each Arabic letter into its correct joined/contextual
    presentation form (Arabic letters change shape depending on their neighbors).
  - `python-bidi`'s `get_display()` then reorders the string into left-to-right
    *visual* order per the Unicode Bidi Algorithm, so drawing it left-to-right (as
    ReportLab always does) produces the correct right-to-left reading order.
  - Since a single ReportLab font can't cover both scripts (see `ReportGenerator.
    _registerArabicFonts()` - Noto Naskh Arabic has no Latin letters, and Helvetica
    has no Arabic ones), `pdfMarkup()` splits the bidi-reordered string into
    contiguous script runs and wraps each in its own ReportLab Paragraph `<font>` tag.

Font choice: Noto Naskh Arabic (client/fonts/NotoNaskhArabic/, OFL-1.1), not the more
generic-looking Noto Sans Arabic used here originally - real Naskh book/print
proportions read as an actual document rather than UI chrome, and (checked directly
against this exact reshape+bidi+draw pipeline, which does no real OpenType ligature
substitution) it renders cleanly without the join artifacts that a more calligraphic
font like Amiri can show, or the outright broken/disconnected glyphs that Noto Kufi
Arabic and Scheherazade produce here.
"""

import re
import html

import arabic_reshaper
from bidi import get_display

REGULAR_FONT_NAME = 'NotoNaskhArabic'
BOLD_FONT_NAME = 'NotoNaskhArabic-Bold'

# Arabic, Arabic Supplement, Arabic Extended-A, and the Arabic Presentation Forms
# blocks - covers both plain letters and (after reshaping) their joined forms.
_ARABIC_RE = re.compile(r'[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]')


def containsArabic(text: str) -> bool:
    """Return True if `text` has at least one Arabic-script character."""
    return bool(text) and bool(_ARABIC_RE.search(text))


def bidiVisual(text: str) -> str:
    """Reshape Arabic letters into their joined presentation forms and reorder the
    whole string into left-to-right visual order, ready to hand straight to
    ReportLab's `drawString`/plain `Table` cells. A no-op for plain Latin/numeric
    text (`arabic_reshaper` only touches Arabic-block characters)."""
    if not containsArabic(text):
        return text
    return get_display(arabic_reshaper.reshape(text))


def isRtlBase(text: str) -> bool:
    """Return True if `text`'s first strong (Arabic or Latin-letter) character is
    Arabic - i.e. whether it should read as a right-to-left paragraph overall.
    Mirrors the same "first strong character" rule Qt's own text widgets use to
    auto-detect a paragraph's base direction (see client/helper/i18n.py's is_rtl()
    for the equivalent whole-app-language check)."""
    if not text:
        return False
    for ch in text:
        if _ARABIC_RE.match(ch):
            return True
        if ch.isalpha():
            return False
    return False


def pdfMarkup(text: str, bold: bool = False) -> str:
    """Convert `text` into ReportLab Paragraph mini-XML, safe to embed directly in a
    `Paragraph(...)` string: bidi-reorder/reshape it, then wrap each contiguous
    Arabic-script run in a `<font name="...">` tag switching to an Arabic-capable
    font (`REGULAR_FONT_NAME`/`BOLD_FONT_NAME`, registered in ReportGenerator.py),
    since the surrounding paragraph style's own font (Helvetica et al.) has no
    Arabic glyphs. Non-Arabic runs are left in the style's default font, XML-escaped.
    A no-op (beyond escaping) for plain Latin/numeric text.
    """
    if not text:
        return text
    if not containsArabic(text):
        return html.escape(text)

    visual = bidiVisual(text)
    fontName = BOLD_FONT_NAME if bold else REGULAR_FONT_NAME

    runs = []
    current = []
    currentIsArabic = None
    for ch in visual:
        chIsArabic = bool(_ARABIC_RE.match(ch))
        # Neutral characters (spaces, digits, punctuation) join whichever run they're
        # adjacent to rather than splitting it, so e.g. "12" or a space inside an
        # Arabic run doesn't fragment into its own (pointlessly font-tagged) run.
        isBoundary = ch.isalpha() and (currentIsArabic is not None) and (chIsArabic != currentIsArabic)
        if isBoundary:
            runs.append((currentIsArabic, ''.join(current)))
            current = []
        current.append(ch)
        if ch.isalpha():
            currentIsArabic = chIsArabic
    if current:
        runs.append((currentIsArabic, ''.join(current)))

    parts = []
    for runIsArabic, run in runs:
        escaped = html.escape(run)
        if runIsArabic:
            parts.append(f'<font name="{fontName}">{escaped}</font>')
        else:
            parts.append(escaped)
    return ''.join(parts)
