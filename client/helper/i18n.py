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
