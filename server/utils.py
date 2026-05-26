from typing import Iterable, Mapping
from types import SimpleNamespace


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
