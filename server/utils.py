"""Generic recursive converters between plain Python containers/namespaces and
model objects with attribute-based state, used to (de)serialize DB rows and
domain objects for JSON responses."""

from typing import Iterable, Mapping
from types import SimpleNamespace


def objToDict(obj):
    """Recursively convert an object graph (models, namespaces, dicts, lists,
    tuples, sets, ...) into plain dicts/lists/scalars suitable for jsonify().

    Args:
        obj: any value; objects exposing __dict__ are converted via vars().

    Returns:
        The equivalent structure built from dicts, lists/tuples/etc., and
        primitive scalars.
    """
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
    """Recursively convert nested dicts/lists/tuples/sets (e.g. a parsed JSON
    payload) into SimpleNamespace objects with equivalent attributes, so
    downstream code can access fields with dot notation.

    Args:
        data: any value; Mapping instances become SimpleNamespace objects.

    Returns:
        The equivalent structure with mappings replaced by SimpleNamespace.
    """
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
