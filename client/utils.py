import sys
import os
from typing import Iterable, Mapping
from types import SimpleNamespace


def resource_path(filename):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def objToDict(obj):
    if isinstance(obj, (str, bytes, int, float, bool, type(None))):
        return obj
    if isinstance(obj, Mapping):
        return {k: objToDict(v) for k, v in obj.items()}
    if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        return type(obj)(objToDict(v) for v in obj)
    if hasattr(obj, "__dict__"):
        return {k: objToDict(v) for k, v in vars(obj).items()}
    return obj


def parseTabularFile(filepath: str, headers: list[str]) -> list[list[str]]:
    """Reads a .xlsx or .csv file and returns its data rows (header row excluded) as plain
    stripped strings, each reordered to match `headers` regardless of the file's own column
    order or header casing/whitespace/newlines. Blank rows are NOT skipped — callers decide
    whether/how to filter them, so their own row-numbering can still match the source file.
    Raises ValueError listing any of `headers` not found in the file."""
    if filepath.lower().endswith('.csv'):
        import csv
        with open(filepath, newline='', encoding='utf-8-sig') as f:
            allRows = [tuple(row) for row in csv.reader(f)]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        allRows = list(ws.iter_rows(values_only=True))
        wb.close()

    if not allRows:
        return []

    def normalize(s):
        return ' '.join(str(s or '').replace('\n', ' ').split()).lower()

    headerIndex = {normalize(h): i for i, h in enumerate(allRows[0])}
    missing = [h for h in headers if normalize(h) not in headerIndex]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(h.replace(chr(10), ' ') for h in missing)}")

    rows = []
    for row in allRows[1:]:
        record = []
        for h in headers:
            idx = headerIndex[normalize(h)]
            value = row[idx] if idx < len(row) else None
            record.append(str(value).strip() if value is not None else '')
        rows.append(record)
    return rows


def dictToObj(data):
    if isinstance(data, (str, bytes, int, float, bool, type(None))):
        return data
    if isinstance(data, Mapping):
        obj = SimpleNamespace()
        for k, v in data.items():
            setattr(obj, k, dictToObj(v))
        return obj
    if isinstance(data, list):
        return [dictToObj(v) for v in data]
    if isinstance(data, tuple):
        return tuple(dictToObj(v) for v in data)
    if isinstance(data, set):
        return {dictToObj(v) for v in data}
    return data
