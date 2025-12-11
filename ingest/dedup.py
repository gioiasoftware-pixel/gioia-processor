from __future__ import annotations

import re
import unicodedata
from typing import List

from rapidfuzz import fuzz

from ingest.reconcile import reconcile_rows
from ingest.types import WineRow


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = re.sub(r"\b(docg?|igt|aoc|d\.?o\.?c\.?)\b", "", normalized)
    normalized = re.sub(r"[^a-z0-9 ]", " ", normalized)
    return " ".join(normalized.split())


def same_wine(first: WineRow, second: WineRow) -> bool:
    if not (first.name.value and second.name.value):
        return False

    name_score = fuzz.token_set_ratio(
        _normalize_token(str(first.name.value)), _normalize_token(str(second.name.value))
    )

    winery_score = 0
    if first.winery.value and second.winery.value:
        winery_score = fuzz.token_set_ratio(
            _normalize_token(str(first.winery.value)),
            _normalize_token(str(second.winery.value)),
        )

    vintage_compatible = (
        first.vintage.value == second.vintage.value
        or first.vintage.value in (None, "")
        or second.vintage.value in (None, "")
    )

    return name_score >= 90 and (winery_score >= 88 or winery_score == 0) and vintage_compatible


def deduplicate(rows: List[WineRow]) -> List[WineRow]:
    deduped: List[WineRow] = []

    for row in rows:
        merged = False
        for index, existing in enumerate(deduped):
            if same_wine(row, existing):
                if isinstance(row.qty.value, (int, float)) and isinstance(existing.qty.value, (int, float)):
                    existing.qty.value = float(existing.qty.value) + float(row.qty.value)
                deduped[index] = reconcile_rows(existing, row)
                merged = True
                break
        if not merged:
            deduped.append(row)

    return deduped









