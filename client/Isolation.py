import enum
from typing import Iterable


class Isolation:
    class Tags(enum.StrEnum):
        XV7231A = enum.auto()
        XV7231B = enum.auto()
        XV7231C = enum.auto()
        XV7231D = enum.auto()
        XV7231E = enum.auto()

    def __init__(self, id: str='', tag: str='', sequence: Iterable[str]=[], linked_ptws_id: Iterable[str]=[]):
        self.id = id 
        self.tag = tag
        self.linked_ptws_id = linked_ptws_id
        self.sequence = sequence

    def setAll(self, data: dict):
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception as e:
                    pass
        return self

