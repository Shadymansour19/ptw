import json
import os

_lang = 'en'
_translations: dict = {}


def init(lang: str):
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
    return _lang in ('ar', 'he', 'fa', 'ur')


def current_lang() -> str:
    return _lang
