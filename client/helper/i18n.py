"""Language/locale initialization and simple string-translation lookup for the client UI,
including right-to-left (RTL) layout detection.
"""

import json
import os
import logging

log = logging.getLogger("client")

_lang = 'en'
_translations: dict = {}

# client/translations/ - a sibling of this file's own client/helper/ package, NOT a
# subdirectory of it. Historically this module lived at client/i18n.py (translations/
# resolved directly underneath it) until an 2026-08-01 reorganization moved it into
# client/helper/ without updating this path, which silently broke every translation
# lookup for ~12 days: is_rtl() still flipped the layout direction correctly (a pure
# lang-code check, no file needed), but t() always fell through to its "file not found"
# empty-dict branch and returned every key untranslated - the language toggle *looked*
# like it worked (RTL layout) while translating nothing. Don't recompute this relative
# to __file__ without re-checking where translations/ actually lives.
_TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'translations')


def init(lang: str):
    """Set the active language to `lang` and load its translation dictionary, if available.

    Looks for `translations/<lang>.json` (client/translations/, a sibling of helper/); if
    the file doesn't exist, falls back to an empty translation dict so `t()` returns keys
    verbatim (i.e. English) - logged as a warning for any non-English `lang`, since that
    fallback is otherwise silent (see _TRANSLATIONS_DIR's comment for why this matters).
    """
    global _lang, _translations
    _lang = lang
    path = os.path.join(_TRANSLATIONS_DIR, f'{lang}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
    else:
        _translations = {}
        if lang != 'en':
            log.warning("i18n: no translation file found for lang=%r at %s - t() will return English keys verbatim.", lang, path)


def t(key: str) -> str:
    """Translate a string. Falls back to the key itself (English) if no translation found."""
    return _translations.get(key, key)


def is_rtl() -> bool:
    """Return True if the current language reads right-to-left (Arabic, Hebrew, Persian, Urdu)."""
    return _lang in ('ar', 'he', 'fa', 'ur')


def current_lang() -> str:
    """Return the language code set by the most recent init() call."""
    return _lang


# Cached across calls: the app's real default font (captured once, before we ever touch
# it) so switching back out of an RTL language restores it exactly, and the bundled
# Arabic UI font's registered family name (registered with Qt's font database once,
# not re-added on every call).
_ORIGINAL_FONT = None
_ARABIC_FONT_FAMILY = None


def apply_layout(app):
    """Apply the current language's layout direction to `app`, plus (only for an RTL
    language) the bundled Noto Naskh Arabic font as the app-wide UI font - none of
    Qt's own fallback fonts are guaranteed to render Arabic well on every end-user
    machine, so this is registered from the file we ship rather than relying on
    whatever's installed. Switching back to a non-RTL language restores the app's
    original default font exactly.

    Call this any time the active language may have changed: main.py at startup
    (OS-locale default, pre-login) and Login.py right after a successful login (the
    user's saved preference, which can differ from that startup default in either
    direction - so this must always run, not just when a preference happens to be set).
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFontDatabase, QFont
    from helper.utils import resource_path

    global _ORIGINAL_FONT, _ARABIC_FONT_FAMILY

    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl() else Qt.LayoutDirection.LeftToRight)

    if _ORIGINAL_FONT is None:
        _ORIGINAL_FONT = QFont(app.font())

    if not is_rtl():
        app.setFont(_ORIGINAL_FONT)
        return

    if _ARABIC_FONT_FAMILY is None:
        fontId = QFontDatabase.addApplicationFont(resource_path('fonts/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf'))
        QFontDatabase.addApplicationFont(resource_path('fonts/NotoNaskhArabic/NotoNaskhArabic-Bold.ttf'))
        families = QFontDatabase.applicationFontFamilies(fontId)
        _ARABIC_FONT_FAMILY = families[0] if families else None
        if not _ARABIC_FONT_FAMILY:
            log.warning("i18n: failed to register the bundled Noto Naskh Arabic font - falling back to the default UI font for Arabic too.")

    if _ARABIC_FONT_FAMILY:
        app.setFont(QFont(_ARABIC_FONT_FAMILY, _ORIGINAL_FONT.pointSize()))
