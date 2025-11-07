from __future__ import annotations

import pathlib
import re
from functools import lru_cache
from typing import Literal

import yaml
from rapidfuzz import fuzz

from copy import deepcopy

from core.config import ProcessorConfig
from core.logger_diff import log_field_override
from ingest.types import WineRow
from ingest.utils_confidence import can_override

SUPPLIER_HINTS = [
    "srl",
    "spa",
    "sas",
    "distrib",
    "distribuzioni",
    "bevande",
    "import",
    "importazioni",
    "wholesale",
    "trading",
]


@lru_cache(maxsize=1)
def _load_datasets() -> tuple[set[str], set[str]]:
    base_path = pathlib.Path(__file__).resolve().parent.parent / "data"
    suppliers_file = base_path / "suppliers.yml"
    wineries_file = base_path / "wineries.yml"

    suppliers: set[str] = set()
    wineries: set[str] = set()

    if suppliers_file.exists():
        with suppliers_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            suppliers = {entry.lower() for entry in data.get("suppliers", [])}

    if wineries_file.exists():
        with wineries_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            wineries = {entry.lower() for entry in data.get("wineries", [])}

    return suppliers, wineries


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_known_supplier(value: str) -> bool:
    suppliers, _ = _load_datasets()
    normalized = _normalize(value)
    return any(fuzz.partial_ratio(normalized, supplier) >= 90 for supplier in suppliers)


def is_known_winery(value: str) -> bool:
    _, wineries = _load_datasets()
    normalized = _normalize(value)
    return any(fuzz.partial_ratio(normalized, winery) >= 90 for winery in wineries)


def classify_party(text: str | None) -> Literal["supplier", "winery", "unknown"]:
    if not text:
        return "unknown"

    lowered = text.lower()

    if is_known_supplier(lowered):
        return "supplier"
    if is_known_winery(lowered):
        return "winery"
    if any(hint in lowered for hint in SUPPLIER_HINTS):
        return "supplier"

    return "unknown"


def resolve_supplier_producer(row: WineRow, cfg: ProcessorConfig) -> WineRow:
    policy = (cfg.normalization_policy or "SAFE").upper()
    delta = cfg.llm_strict_override_delta

    supplier_before = deepcopy(row.supplier)
    winery_before = deepcopy(row.winery)

    if isinstance(row.winery.value, str) and classify_party(row.winery.value) == "supplier":
        if can_override(row.supplier, row.winery.confidence, policy, delta):
            row.supplier.value = row.winery.value
            row.supplier.confidence = max(row.supplier.confidence, row.winery.confidence)
            original_winery = row.raw_winery
            if original_winery and original_winery != row.supplier.value:
                row.winery.value = original_winery
            else:
                row.winery.value = None
            row.winery.confidence = min(row.winery.confidence, 0.2)
            log_field_override("supplier", supplier_before, row.supplier)
            log_field_override("winery", winery_before, row.winery)
            supplier_before = deepcopy(row.supplier)
            winery_before = deepcopy(row.winery)

    if (
        (row.winery.value in (None, ""))
        and isinstance(row.supplier.value, str)
        and classify_party(row.supplier.value) == "winery"
    ):
        prev_winery = deepcopy(row.winery)
        row.winery.value = row.supplier.value
        row.winery.confidence = max(row.winery.confidence, row.supplier.confidence - 0.1)
        log_field_override("winery", prev_winery, row.winery)

    return row

