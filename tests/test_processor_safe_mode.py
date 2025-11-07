from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import ProcessorConfig
from ingest.normalization import normalize_wine_row
from ingest.parser import parse_dataframe
from ingest.supplier_resolver import classify_party


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_safe_mode_preserves_labels():
    cfg = ProcessorConfig()
    df = pd.read_csv(FIXTURES / "1_pulito.csv")
    rows, _ = parse_dataframe(df, cfg, "1_pulito.csv")
    normalized = normalize_wine_row(rows[0], cfg)

    assert normalized.name.value == "Barolo Brunate"
    assert normalized.winery.value == "Vietti"
    assert normalized.qty.value == 6
    assert float(normalized.price.value) == 75.0


def test_header_mapping_synonyms():
    cfg = ProcessorConfig()
    df = pd.read_csv(FIXTURES / "2_sinonimi.csv")
    rows, mapping = parse_dataframe(df, cfg, "2_sinonimi.csv")

    assert mapping["Label"]["field"] == "name"
    assert mapping["Produttore"]["field"] == "winery"
    assert mapping["P.U."]["field"] == "price"
    # Verifica anche normalizzazione qta
    normalized = normalize_wine_row(rows[0], cfg)
    assert normalized.qty.value == 12


def test_supplier_resolver_classifies_known_supplier():
    value = "Pellegrini S.p.A."
    assert classify_party(value) == "supplier"
