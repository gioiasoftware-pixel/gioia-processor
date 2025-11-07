from __future__ import annotations

from ingest.types import WineRow
from ingest.utils_confidence import pick_better


def reconcile_rows(primary: WineRow, secondary: WineRow) -> WineRow:
    field_names = [
        name
        for name in primary.__dataclass_fields__.keys()
        if name not in {"raw_name", "raw_winery", "raw_supplier", "source_file", "source_row"}
    ]

    for field_name in field_names:
        best = pick_better(getattr(primary, field_name), getattr(secondary, field_name))
        setattr(primary, field_name, best)

    primary.raw_name = primary.raw_name or secondary.raw_name
    primary.raw_winery = primary.raw_winery or secondary.raw_winery
    primary.raw_supplier = primary.raw_supplier or secondary.raw_supplier

    if primary.source_file is None:
        primary.source_file = secondary.source_file
    if primary.source_row is None:
        primary.source_row = secondary.source_row

    return primary

