"""Parser orchestratore per Stage 1 (parse classico, modalità SAFE per default)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from core.config import ProcessorConfig, get_config
from core.logger import log_json
from ingest.excel_parser import parse_excel
from ingest.gate import route_file
from ingest.header_detector import parse_csv_with_multiple_headers
from ingest.dedup import deduplicate
from ingest.normalization import normalize_wine_row
from ingest.supplier_resolver import resolve_supplier_producer
from ingest.types import WineRow, fv
from ingest.validation import validate_batch, wine_model_to_dict

logger = logging.getLogger(__name__)

TARGET_COLUMNS = ["name", "winery", "vintage", "qty", "price", "type"]
REQUIRED_COLUMNS = ["name", "qty"]

DATABASE_FIELDS = [
    "name",
    "winery",
    "supplier",
    "vintage",
    "qty",
    "price",
    "type",
    "grape_variety",
    "region",
    "country",
    "classification",
    "cost_price",
    "alcohol_content",
    "description",
    "notes",
]

def _clean_csv_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1]
        text = text.replace('""', '"')
        if text in {"-", "--"}:
            text = ""
        return text
    return value


SYNONYMS: Dict[str, List[str]] = {
    "name": ["etichetta", "nome_etichetta", "nome etichetta", "label", "prodotto", "articolo", "descrizione breve", "vino"],
    "winery": ["cantina", "produttore", "azienda", "azienda agricola", "domain", "domaine"],
    "supplier": ["fornitore", "distributore", "importatore", "grossista", "supplier", "wholesaler"],
    "vintage": ["annata", "millésime", "year", "anno"],
    "qty": ["qta", "quantita", "quantità", "quantita", "pezzi", "bottiglie", "btl", "stock"],
    "price": ["prezzo", "prezzo unitario", "prezzo_unitario", "prezzo_unit", "p.u.", "€/pz", "costo", "listino"],
    "type": ["tipologia", "colore", "style", "rosso", "bianco", "rosé", "metodo"],
    "grape_variety": ["uvaggio", "vitigno", "grape variety", "varietà uva"],
    "region": ["regione", "zona", "area", "territorio"],
    "country": ["paese", "nazione", "origine", "country"],
    "classification": ["doc", "docg", "igt", "denominazione", "aoc"],
    "cost_price": ["costo", "prezzo acquisto", "costo unitario"],
    "alcohol_content": ["gradazione", "%vol", "alcol", "alcohol"],
    "description": ["descrizione", "note degustative", "dettagli"],
    "notes": ["note", "annotazioni", "osservazioni"],
}

TYPE_MAP = {
    "rosso": "Rosso",
    "red": "Rosso",
    "bianco": "Bianco",
    "white": "Bianco",
    "rosato": "Rosato",
    "rosé": "Rosato",
    "rose": "Rosato",
    "spumante": "Spumante",
    "sparkling": "Spumante",
}


def calculate_schema_score(mapping: Dict[str, Dict[str, Any]]) -> float:
    mapped_fields = {
        info["field"]
        for info in mapping.values()
        if info.get("field") in TARGET_COLUMNS
    }
    return len(mapped_fields) / len(TARGET_COLUMNS) if TARGET_COLUMNS else 0.0


def col_score(colname: str, field: str) -> float:
    """Calcola score di matching tra nome colonna e campo target."""
    normalized_col = colname.lower().strip()
    
    # Rimuovi underscore e sostituisci con spazi per matching migliore
    normalized_col_alt = normalized_col.replace('_', ' ').replace('-', ' ')
    
    # Match diretto
    base = fuzz.token_set_ratio(normalized_col, field)
    
    # Match con underscore sostituiti
    base_alt = fuzz.token_set_ratio(normalized_col_alt, field)
    
    # Match con sinonimi
    syn_scores = [
        fuzz.token_set_ratio(normalized_col, synonym.lower())
        for synonym in SYNONYMS.get(field, [])
    ]
    
    # Match sinonimi con underscore sostituiti
    syn_scores_alt = [
        fuzz.token_set_ratio(normalized_col_alt, synonym.lower())
        for synonym in SYNONYMS.get(field, [])
    ]
    
    # Prendi il miglior score
    best_syn = max(syn_scores + syn_scores_alt + [0])
    best_base = max(base, base_alt)
    
    return max(best_base, best_syn) / 100.0


def map_headers_v2(columns: List[str], cfg: ProcessorConfig) -> Dict[str, Dict[str, Any]]:
    m = len(columns)
    n = len(DATABASE_FIELDS)
    size = max(m, n)
    cost = np.ones((size, size))
    scores = np.zeros((size, size))

    for i, column in enumerate(columns):
        normalized_col = column.lower().strip()
        for j, field in enumerate(DATABASE_FIELDS):
            score = col_score(column, field)

            if normalized_col.startswith("q ") or normalized_col.startswith("q_") or normalized_col.startswith("q.") or " q" in normalized_col:
                if field not in ("qty", "min_quantity"):
                    score = min(score, 0.3)

            if normalized_col == "cantina" and field == "winery":
                score = 1.0
            
            # Fix-up per "Annata" -> vintage (match esatto)
            if normalized_col == "annata" and field == "vintage":
                score = 1.0

            scores[i, j] = score
            cost[i, j] = 1.0 - score

    row_ind, col_ind = linear_sum_assignment(cost)
    mapping: Dict[str, Dict[str, Any]] = {}

    for r, c in zip(row_ind, col_ind):
        if r < m and c < n:
            score = float(scores[r, c])
            field = DATABASE_FIELDS[c] if score >= cfg.header_confidence_th else None
            mapping[columns[r]] = {"field": field, "score": score}

    for column in columns:
        mapping.setdefault(column, {"field": None, "score": 0.0})

    # Heuristic fix-ups for common Italian inventories
    winery_column = _resolve_field_column(mapping, "winery")
    if winery_column is None:
        for column in columns:
            if column.lower().strip() == "cantina":
                # Clear previous winery assignment if any
                for other in list(mapping.keys()):
                    if mapping[other].get("field") == "winery":
                        mapping[other] = {"field": None, "score": mapping[other].get("score", 0.0)}
                mapping[column] = {"field": "winery", "score": 1.0}
                winery_column = column
                break
    elif winery_column:
        # Prefer the explicit 'Cantina' column over generic 'winery' duplicates
        for column in columns:
            if column.lower().strip() == "cantina" and column != winery_column:
                mapping[winery_column] = {"field": None, "score": mapping[winery_column].get("score", 0.0)}
                mapping[column] = {"field": "winery", "score": 1.0}
                winery_column = column
                break

    qty_column = _resolve_field_column(mapping, "qty")
    if qty_column is None:
        for column in columns:
            norm = column.lower().strip()
            if norm in {"q cantina", "q_init", "q iniziale", "q magazzino"} or norm.startswith("q "):
                mapping[column] = {"field": "qty", "score": 0.9}
                break

    return mapping


def _resolve_field_column(mapping: Dict[str, Dict[str, Any]], field: str) -> Optional[str]:
    for column, info in mapping.items():
        if info.get("field") == field:
            return column
    return None


def parse_dataframe(
    df: pd.DataFrame, cfg: ProcessorConfig, source_file: str
) -> Tuple[List[WineRow], Dict[str, Dict[str, Any]]]:
    columns = list(df.columns)
    mapping = map_headers_v2(columns, cfg)
    lower_lookup = {str(col).lower(): col for col in columns}
    rows: List[WineRow] = []

    for idx, series in df.iterrows():
        lineage_base = {"row": int(idx) if isinstance(idx, (int, float)) else 0, "file": source_file}

        def get_fv(field: str, fallbacks: Optional[List[str]] = None):
            column = _resolve_field_column(mapping, field)
            if column is not None and column in series:
                value = _clean_csv_value(series[column])
                score = float(mapping[column]["score"])
                return fv(value, score, "stage1", {**lineage_base, "column": column})

            for fb in fallbacks or []:
                candidate = lower_lookup.get(fb.lower())
                if candidate is not None and candidate in series:
                    value = _clean_csv_value(series[candidate])
                    if value not in (None, ""):
                        return fv(value, 0.4, "stage1", {**lineage_base, "column": candidate})

            return fv(None, 0.0, "stage1", {**lineage_base, "column": None})

        wine_row = WineRow(
            name=get_fv("name", ["Etichetta", "Label", "Descrizione", "Descrizione breve"]),
            winery=get_fv("winery", ["Cantina", "Produttore", "Azienda"]),
            supplier=get_fv("supplier", ["Fornitore", "Distributore", "Importatore"]),
            vintage=get_fv("vintage", ["Annata", "Anno"]),
            qty=get_fv("qty", ["Quantità", "Qta", "Bottiglie", "Pezzi"]),
            price=get_fv("price", ["Prezzo", "Prezzo Unitario", "€/pz", "Costo"]),
            type=get_fv("type", ["Tipologia", "Colore"]),
            grape_variety=get_fv("grape_variety", ["Vitigno", "Uvaggio"]),
            region=get_fv("region", ["Regione"]),
            country=get_fv("country", ["Paese", "Nazione"]),
            classification=get_fv("classification", ["DOC", "DOCG", "IGT"]),
            cost_price=get_fv("cost_price", ["Costo", "Prezzo acquisto"]),
            alcohol_content=get_fv("alcohol_content", ["Alcol", "%Vol"]),
            description=get_fv("description", ["Descrizione", "Note"]),
            notes=get_fv("notes", ["Note", "Osservazioni"]),
        )

        wine_row.raw_name = str(wine_row.name.value) if wine_row.name.value not in (None, "") else None
        wine_row.raw_winery = str(wine_row.winery.value) if wine_row.winery.value not in (None, "") else None
        wine_row.raw_supplier = (
            str(wine_row.supplier.value) if wine_row.supplier.value not in (None, "") else None
        )
        wine_row.source_file = source_file
        wine_row.source_row = lineage_base["row"]

        rows.append(wine_row)

    return rows, mapping


def _is_empty_field(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() in {"nan", "none", "null", "n/a"}
    if isinstance(value, (int, float)):
        import math
        if isinstance(value, float) and math.isnan(value):
            return True
        return value == 0
    return False
HEADER_KEYWORDS = {
    "indice",
    "id",
    "status",
    "totale",
    "categoria",
    "note",
    "filtro",
    "inventario",
    "annotazioni",
}

VALUE_KEYWORDS = {
    "indice",
    "id",
    "totale",
    "categoria",
    "inventario",
    "section",
    "page",
    "sheet",
}


def _looks_like_section_header(row: WineRow) -> bool:
    values = [
        row.name.value,
        row.winery.value,
        row.supplier.value,
        row.grape_variety.value,
        row.type.value,
    ]
    text_values = [str(v).strip().lower() for v in values if isinstance(v, str) and v and str(v).strip()]

    if not text_values:
        return False

    for text in text_values:
        if text in VALUE_KEYWORDS:
            return True
        if len(text) <= 3 and text.isalpha():
            return True

    if all(text in HEADER_KEYWORDS for text in text_values):
        return True

    return False


def _is_row_empty(row: WineRow) -> bool:
    name = row.name.value.strip() if isinstance(row.name.value, str) else ""
    if name:
        return False

    checks = [
        row.winery.value,
        row.supplier.value,
        row.qty.value,
        row.price.value,
        row.vintage.value,
        row.description.value,
        row.notes.value,
    ]
    if all(_is_empty_field(value) for value in checks):
        return True

    # Righe header/section con testo ma senza dati
    if _looks_like_section_header(row):
        return True

    return False


def _coerce_number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value)
        text = text.replace("€", "").replace(" ", "")
        text = text.replace(".", "").replace(",", ".")
        for token in text.split():
            try:
                return float(token)
            except ValueError:
                continue
        return float(text)
    except Exception:
        return None


def wine_row_to_payload(row: WineRow) -> Dict[str, Any]:
    def _sanitize(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if text.lower() in {"nan", "none", "null", "n/a"}:
            return None
        return text

    qty_value = _coerce_number(row.qty.value)
    price_value = _coerce_number(row.price.value)
    
    # Normalizza vintage: estrae anno 4 cifre (1900-2099)
    vintage_value = None
    if row.vintage.value is not None:
        try:
            # Prova prima come numero diretto
            if isinstance(row.vintage.value, (int, float)):
                import math
                if isinstance(row.vintage.value, float) and math.isnan(row.vintage.value):
                    vintage_value = None
                else:
                    year_int = int(float(row.vintage.value))
                    if 1900 <= year_int <= 2099:
                        vintage_value = year_int
            else:
                # Prova con regex per estrarre anno 4 cifre
                import re
                value_str = str(row.vintage.value).strip()
                match = re.search(r'\b(19\d{2}|20\d{2})\b', value_str)
                if match:
                    year_int = int(match.group())
                    if 1900 <= year_int <= 2099:
                        vintage_value = year_int
                else:
                    # Fallback: prova a convertire direttamente
                    try:
                        year_int = int(float(value_str))
                        if 1900 <= year_int <= 2099:
                            vintage_value = year_int
                    except (ValueError, TypeError):
                        vintage_value = None
        except Exception as e:
            logger.debug(f"[PARSER] Errore normalizzazione vintage '{row.vintage.value}': {e}")
            vintage_value = None

    wine_type = row.type.value.lower() if isinstance(row.type.value, str) else row.type.value
    mapped_type = TYPE_MAP.get(wine_type) if isinstance(wine_type, str) else None

    payload = {
        "name": str(row.name.value).strip() if isinstance(row.name.value, str) else "",
        "winery": _sanitize(row.winery.value),
        "supplier": _sanitize(row.supplier.value),
        "vintage": vintage_value,
        "qty": int(qty_value) if qty_value is not None else 0,
        "price": float(price_value) if price_value is not None else None,
        "type": mapped_type,
        "grape_variety": _sanitize(row.grape_variety.value),
        "region": _sanitize(row.region.value),
        "country": _sanitize(row.country.value),
        "classification": _sanitize(row.classification.value),
        "cost_price": _coerce_number(row.cost_price.value),
        "alcohol_content": _coerce_number(row.alcohol_content.value),
        "description": _sanitize(row.description.value),
        "notes": _sanitize(row.notes.value),
        "source_stage": "stage1",
    }

    if payload["cost_price"] is not None:
        payload["cost_price"] = float(payload["cost_price"])
    if payload["alcohol_content"] is not None:
        payload["alcohol_content"] = float(payload["alcohol_content"])

    return payload


def parse_classic(
    file_content: bytes,
    file_name: str,
    ext: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    start_time = time.time()
    config = get_config()

    try:
        stage, ext_normalized = route_file(file_content, file_name, ext)
        if stage != "csv_excel":
            raise ValueError(f"File routed to {stage}, expected csv_excel for Stage 1")

        if ext_normalized in ["csv", "tsv"]:
            df, parse_info = parse_csv_with_multiple_headers(file_content)
        elif ext_normalized in ["xlsx", "xls"]:
            df, parse_info = parse_excel(file_content)
        else:
            raise ValueError(f"Unsupported extension for Stage 1: {ext_normalized}")

        rows_total = len(df)
        logger.info("[PARSER] Parsed %s rows, %s columns", rows_total, len(df.columns))

        original_columns = list(df.columns)
        column_samples: Dict[str, List[str]] = {}
        for column in original_columns:
            samples: List[str] = []
            for value in df[column]:
                if pd.isna(value):
                    continue
                text = str(value).strip()
                if not text:
                    continue
                samples.append(text)
                if len(samples) == 5:
                    break
            column_samples[column] = samples

        wine_rows, header_mapping = parse_dataframe(df, config, file_name)

        normalized_rows: List[WineRow] = []
        filtered_empty = 0
        for wine_row in wine_rows:
            normalized = normalize_wine_row(wine_row, config)
            normalized = resolve_supplier_producer(normalized, config)
            if _is_row_empty(normalized):
                filtered_empty += 1
                continue
            normalized_rows.append(normalized)

        normalized_rows = deduplicate(normalized_rows)
        payload_rows = [wine_row_to_payload(r) for r in normalized_rows]

        valid_wines, rejected_wines, validation_stats = validate_batch(payload_rows)
        wines_data_valid = [wine_model_to_dict(wine) for wine in valid_wines]

        rows_valid = validation_stats["rows_valid"]
        rows_rejected = validation_stats["rows_rejected"]
        effective_total = max(rows_total - filtered_empty, 1)
        valid_rows_ratio = rows_valid / effective_total if effective_total else 0.0

        schema_score = calculate_schema_score(header_mapping)
        elapsed_ms = (time.time() - start_time) * 1000

        mapped_fields = {
            info["field"]
            for info in header_mapping.values()
            if info.get("field")
        }
        missing_required = [field for field in REQUIRED_COLUMNS if field not in mapped_fields]
        unmapped_columns = [
            column for column, info in header_mapping.items() if info.get("field") is None
        ]

        metrics: Dict[str, Any] = {
            "schema_score": schema_score,
            "valid_rows": valid_rows_ratio,
            "rows_total": rows_total,
            "rows_valid": rows_valid,
            "rows_rejected": rows_rejected,
            "rejection_reasons": validation_stats["rejection_reasons"],
            "elapsed_ms": elapsed_ms,
            "parse_info": parse_info,
            "header_mapping": header_mapping,
            "rows_after_filter": len(payload_rows),
            "rows_filtered_empty": filtered_empty,
            "missing_required_fields": missing_required,
            "unmapped_columns": unmapped_columns,
            "original_columns": original_columns,
            "column_samples": column_samples,
        }

        if schema_score >= config.schema_score_th and valid_rows_ratio >= config.min_valid_rows:
            decision = "save"
        else:
            decision = "escalate_to_stage2"

        log_json(
            level="info",
            message=f"Stage 1 parse completed: decision={decision}",
            file_name=file_name,
            ext=ext_normalized,
            stage="csv_parse",
            schema_score=schema_score,
            valid_rows=valid_rows_ratio,
            rows_total=rows_total,
            rows_valid=rows_valid,
            rows_rejected=rows_rejected,
            elapsed_ms=elapsed_ms,
            decision=decision,
        )

        return wines_data_valid, metrics, decision

    except Exception as exc:  # pragma: no cover - log branch
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("[PARSER] Error in Stage 1: %s", exc, exc_info=True)
        log_json(
            level="error",
            message=f"Stage 1 parse failed: {exc}",
            file_name=file_name,
            ext=ext or "unknown",
            stage="csv_parse",
            elapsed_ms=elapsed_ms,
            decision="error",
        )
        raise

