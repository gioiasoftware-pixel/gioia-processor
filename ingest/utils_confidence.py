from __future__ import annotations

from .types import FieldVal


def can_override(old: FieldVal, new_conf: float, policy: str, delta: float) -> bool:
    if (old.value in (None, "", 0) or old.value is None) and old.confidence == 0:
        return True
    if policy == "SAFE":
        return new_conf >= old.confidence + delta
    return new_conf >= old.confidence


def pick_better(a: FieldVal, b: FieldVal) -> FieldVal:
    if b.confidence > a.confidence:
        return b
    if b.confidence < a.confidence:
        return a
    preferred_order = ("stage1", "stage0.5", "stage2", "ocr", "stage3", "post")
    try:
        return a if preferred_order.index(a.source) <= preferred_order.index(b.source) else b
    except ValueError:
        return a

