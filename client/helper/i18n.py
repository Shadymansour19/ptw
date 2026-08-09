"""Language/locale initialization and simple string-translation lookup for the client UI,
including right-to-left (RTL) layout detection.
"""

import json
import os

_lang = 'en'
_translations: dict = {}


def init(lang: str):
    """Set the active language to `lang` and load its translation dictionary, if available.

    Looks for `helper/translations/<lang>.json`; if the file doesn't exist, falls back to an
    empty translation dict so `t()` returns keys verbatim (i.e. English).
    """
    global _lang, _translations
    _lang = lang
    dir_path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(dir_path, 'translations', f'{lang}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
    else:
        _translations = {}


def t(key: str) -> str:
    """Translate a string. Falls back to the key itself (English) if no translation found."""
    return _translations.get(key, key)


def is_rtl() -> bool:
    """Return True if the current language reads right-to-left (Arabic, Hebrew, Persian, Urdu)."""
    return _lang in ('ar', 'he', 'fa', 'ur')


def current_lang() -> str:
    """Return the language code set by the most recent init() call."""
    return _lang
