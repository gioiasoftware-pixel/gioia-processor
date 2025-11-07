from __future__ import annotations

from ingest.dedup import deduplicate
from ingest.types import FieldVal, WineRow


def _fv(value, confidence=0.9, source="stage1"):
    return FieldVal(value=value, confidence=confidence, source=source, lineage={})


def _wine(name, winery, vintage, qty):
    return WineRow(
        name=_fv(name),
        winery=_fv(winery),
        supplier=_fv(None, confidence=0.0),
        vintage=_fv(vintage),
        qty=_fv(qty),
        price=_fv(None, confidence=0.0),
        type=_fv(None, confidence=0.0),
        grape_variety=_fv(None, confidence=0.0),
        region=_fv(None, confidence=0.0),
        country=_fv(None, confidence=0.0),
        classification=_fv(None, confidence=0.0),
        cost_price=_fv(None, confidence=0.0),
        alcohol_content=_fv(None, confidence=0.0),
        description=_fv(None, confidence=0.0),
        notes=_fv(None, confidence=0.0),
    )


def test_deduplicate_merges_quantities():
    rows = [
        _wine("Barolo Brunate", "Vietti", "2018", 6),
        _wine("Barolo  Brunate", "Vietti", "2018", 3),
    ]

    result = deduplicate(rows)

    assert len(result) == 1
    assert result[0].qty.value == 9.0


def test_deduplicate_keeps_distinct_wineries():
    rows = [
        _wine("Barolo Brunate", "Vietti", "2018", 6),
        _wine("Barolo Brunate", "Gaja", "2018", 6),
    ]

    result = deduplicate(rows)

    assert len(result) == 2
