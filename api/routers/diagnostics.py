"""Router diagnostica inventario.

Consente di confrontare il CSV originale con lo stato corrente del DB
per identificare differenze (vini mancanti o extra).
"""
import logging
import re
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import User, ensure_user_tables, get_db
from ingest.header_identifier import identify_headers_and_extract
from ingest.llm_extract import deduplicate_wines
from ingest.parser import parse_classic
from ingest.validation import validate_batch, wine_model_to_dict

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _normalize_key(value: Any) -> str:
    """Normalizza stringhe per confronto case-insensitive."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip().lower()
    # comprime spazi multipli
    value = re.sub(r"\s+", " ", value)
    return value


def _wine_key(name: Any, producer: Any, vintage: Any) -> Tuple[str, str, str]:
    return (
        _normalize_key(name),
        _normalize_key(producer),
        _normalize_key(vintage)
    )


def _sanitize_wine(wine: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": wine.get("name"),
        "producer": wine.get("winery") or wine.get("producer"),
        "vintage": wine.get("vintage"),
        "qty": wine.get("qty"),
        "type": wine.get("type") or wine.get("wine_type"),
        "source_stage": wine.get("source_stage")
    }


def _sanitize_db_row(row_mapping: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": row_mapping.get("name"),
        "producer": row_mapping.get("producer"),
        "vintage": row_mapping.get("vintage"),
        "qty": row_mapping.get("quantity"),
        "type": row_mapping.get("wine_type"),
        "region": row_mapping.get("region"),
        "country": row_mapping.get("country")
    }


@router.post("/compare")
async def compare_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Confronta CSV/Excel fornito con inventario salvato nel database."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File vuoto o non leggibile")

    filename = file.filename or "upload.csv"
    ext = filename.split(".")[-1].lower() if "." in filename else "csv"

    stage0_5_wines_dicts: List[Dict[str, Any]] = []
    stage0_5_metrics: Dict[str, Any] = {
        "method": "header_identifier_stage_0_5",
        "headers_found": 0,
        "wines_extracted": 0,
        "rows_processed": 0,
        "rows_valid": 0,
        "rows_rejected": 0
    }

    stats_stage0_5 = {"rows_valid": 0, "rows_rejected": 0}

    if ext in ["csv", "tsv"]:
        try:
            stage0_5_wines_raw, metrics_stage0_5 = identify_headers_and_extract(
                file_content=content,
                file_name=filename,
                ext=ext
            )
            if stage0_5_wines_raw:
                valid_stage0_5, rejected_stage0_5, stats_stage0_5 = validate_batch(stage0_5_wines_raw)
                stage0_5_wines_dicts = [wine_model_to_dict(w) for w in valid_stage0_5]
                stage0_5_metrics.update({
                    "headers_found": metrics_stage0_5.get("headers_found", 0),
                    "wines_extracted": metrics_stage0_5.get("wines_extracted", len(stage0_5_wines_raw)),
                    "rows_processed": metrics_stage0_5.get("rows_processed", 0),
                    "rows_valid": stats_stage0_5.get("rows_valid", len(stage0_5_wines_dicts)),
                    "rows_rejected": stats_stage0_5.get("rows_rejected", len(rejected_stage0_5))
                })
            else:
                stage0_5_metrics.update(metrics_stage0_5)
        except Exception as stage0_5_error:
            logger.warning(f"[DIAGNOSTICS] Stage 0.5 fallito: {stage0_5_error}")
            stage0_5_metrics["error"] = str(stage0_5_error)

    # Stage 1 parsing classico
    try:
        stage1_wines, stage1_metrics_raw, stage1_decision = parse_classic(
            file_content=content,
            file_name=filename,
            ext=ext
        )
    except Exception as stage1_error:
        logger.error(f"[DIAGNOSTICS] Stage 1 parsing error: {stage1_error}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore Stage 1: {stage1_error}") from stage1_error

    stage1_metrics_summary = {
        "rows_total": stage1_metrics_raw.get("rows_total", 0),
        "rows_valid": stage1_metrics_raw.get("rows_valid", 0),
        "rows_rejected": stage1_metrics_raw.get("rows_rejected", 0),
        "rows_filtered_blacklist": stage1_metrics_raw.get("rows_filtered_blacklist", 0),
        "schema_score": stage1_metrics_raw.get("schema_score"),
        "decision": stage1_decision
    }

    combined_input = []
    if stage0_5_wines_dicts:
        combined_input.extend(stage0_5_wines_dicts)
    combined_input.extend(stage1_wines)

    combined_wines = deduplicate_wines(combined_input, merge_quantities=False) if combined_input else []

    file_keys = {}
    for wine in combined_wines:
        key = _wine_key(wine.get("name"), wine.get("winery") or wine.get("producer"), wine.get("vintage"))
        file_keys[key] = wine

    # Recupera dati inventario dal DB
    stmt_user = select(User).where(User.telegram_id == telegram_id, User.business_name == business_name)
    result_user = await db.execute(stmt_user)
    user = result_user.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato nel database")

    user_tables = await ensure_user_tables(db, telegram_id, business_name)
    table_inventario = user_tables["inventario"]

    fetch_stmt = sql_text(
        f"""
        SELECT id, name, producer, vintage, wine_type, region, country, quantity, selling_price
        FROM {table_inventario}
        WHERE user_id = :user_id
        """
    )
    result_rows = await db.execute(fetch_stmt, {"user_id": user.id})
    db_rows_raw = result_rows.fetchall()

    db_keys = {}
    for row in db_rows_raw:
        mapping = row._mapping  # type: ignore[attr-defined]
        key = _wine_key(mapping.get("name"), mapping.get("producer"), mapping.get("vintage"))
        db_keys[key] = mapping

    missing_keys = [key for key in file_keys.keys() if key not in db_keys]
    extra_keys = [key for key in db_keys.keys() if key not in file_keys]
    matching_count = len(file_keys.keys() & db_keys.keys())

    missing_samples = [_sanitize_wine(file_keys[key]) for key in missing_keys[:20]]
    extra_samples = [_sanitize_db_row(dict(db_keys[key])) for key in extra_keys[:20]]

    return {
        "status": "ok",
        "file_summary": {
            "filename": filename,
            "total_rows": len(combined_wines),
            "stage0_5_valid": len(stage0_5_wines_dicts),
            "stage1_valid": len(stage1_wines)
        },
        "db_summary": {
            "total_rows": len(db_rows_raw)
        },
        "diff": {
            "missing_in_db": len(missing_keys),
            "extra_in_db": len(extra_keys),
            "matching": matching_count,
            "missing_samples": missing_samples,
            "extra_samples": extra_samples
        },
        "stage_metrics": {
            "stage_0_5": stage0_5_metrics,
            "stage_1": stage1_metrics_summary
        }
    }

