from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Any, Dict, Union

Source = Literal["stage0.5", "stage1", "stage2", "stage3", "ocr", "post"]

Val = Union[str, int, float, None]


@dataclass
class FieldVal:
    value: Val
    confidence: float = 0.0
    source: Source = "stage1"
    lineage: Dict[str, Any] = field(default_factory=dict)


def fv(value: Val, conf: float, source: Source, lineage: Dict[str, Any]) -> FieldVal:
    return FieldVal(value=value, confidence=conf, source=source, lineage=lineage)


@dataclass
class WineRow:
    name: FieldVal
    winery: FieldVal
    supplier: FieldVal
    vintage: FieldVal
    qty: FieldVal
    price: FieldVal
    type: FieldVal
    grape_variety: FieldVal
    region: FieldVal
    country: FieldVal
    classification: FieldVal
    cost_price: FieldVal
    alcohol_content: FieldVal
    description: FieldVal
    notes: FieldVal
    raw_name: Optional[str] = None
    raw_winery: Optional[str] = None
    raw_supplier: Optional[str] = None
    source_file: Optional[str] = None
    source_row: Optional[int] = None









