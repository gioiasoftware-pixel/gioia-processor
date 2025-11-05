"""
Parser orchestratore per Stage 1 (Parse classico NO IA).

Orchestra parsing CSV/Excel, normalizzazione, validazione e calcolo metriche.
"""
import time
import logging
import pandas as pd
from typing import Tuple, Dict, Any, List, Optional
from core.config import get_config
from core.logger import log_json
from ingest.gate import route_file
from ingest.csv_parser import parse_csv
from ingest.excel_parser import parse_excel
from ingest.normalization import (
    normalize_column_name,
    map_headers,
    normalize_values
)
from ingest.validation import validate_batch, WineItemModel, wine_model_to_dict

logger = logging.getLogger(__name__)

# Colonne target richieste (conforme a "Update processor.md")
TARGET_COLUMNS = ['name', 'winery', 'vintage', 'qty', 'price', 'type']
REQUIRED_COLUMNS = ['name', 'qty']  # Colonne obbligatorie
OPTIONAL_COLUMNS = ['winery', 'vintage', 'price', 'type']  # Colonne opzionali


def calculate_schema_score(df: pd.DataFrame) -> float:
    """
    Calcola schema_score: colonne target coperte / 6 (o 5 se winery/type opzionali).
    
    Conforme a "Update processor.md" - Stage 1: Metriche.
    
    Args:
        df: DataFrame con colonne normalizzate
    
    Returns:
        schema_score (0.0-1.0)
    """
    df_columns = set(df.columns)
    
    # Conta colonne target presenti
    target_covered = 0
    for col in TARGET_COLUMNS:
        if col in df_columns:
            target_covered += 1
    
    # Schema score = colonne coperte / totale target
    # Usa 6 come denominatore (tutte le colonne target)
    schema_score = target_covered / len(TARGET_COLUMNS)
    
    logger.debug(
        f"[PARSER] Schema score: {target_covered}/{len(TARGET_COLUMNS)} columns covered = {schema_score:.2f}"
    )
    
    return schema_score


def parse_classic(
    file_content: bytes,
    file_name: str,
    ext: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Orchestratore Stage 1: Parse classico (NO IA).
    
    Flow:
    1. Routing (gate.py)
    2. Parse (csv_parser o excel_parser)
    3. Header cleaning (normalization)
    4. Header mapping (normalization con rapidfuzz)
    5. Value normalization (normalization)
    6. Validation (validation.py)
    7. Calcolo metriche (schema_score, valid_rows)
    8. Decisione (passare a Stage 2 o SALVA)
    
    Conforme a "Update processor.md" - Stage 1: Parse classico.
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file (se None, estrae da file_name)
    
    Returns:
        Tuple (wines_data, metrics, decision):
        - wines_data: Lista dict con vini validi (WineItemModel convertiti)
        - metrics: Dict con metriche (schema_score, valid_rows, rows_total, rows_valid, etc.)
        - decision: 'save' se OK, 'escalate_to_stage2' se necessario Stage 2
    """
    start_time = time.time()
    config = get_config()
    
    try:
        # Stage 0: Routing
        stage, ext_normalized = route_file(file_content, file_name, ext)
        
        if stage != 'csv_excel':
            raise ValueError(f"File routed to {stage}, expected csv_excel for Stage 1")
        
        # Stage 1: Parse
        if ext_normalized in ['csv', 'tsv']:
            df, parse_info = parse_csv(file_content)
        elif ext_normalized in ['xlsx', 'xls']:
            df, parse_info = parse_excel(file_content)
        else:
            raise ValueError(f"Unsupported extension for Stage 1: {ext_normalized}")
        
        rows_total = len(df)
        logger.info(f"[PARSER] Parsed {rows_total} rows, {len(df.columns)} columns")
        
        # Header cleaning: normalizza nomi colonne
        original_columns = list(df.columns)
        df.columns = [normalize_column_name(col) for col in df.columns]
        
        # Header mapping: usa rapidfuzz per mappare a colonne standard
        header_mapping = map_headers(
            original_columns,
            confidence_threshold=config.header_confidence_th,
            use_extended=True
        )
        
        # Applica mapping (rinomina colonne)
        if header_mapping:
            # Inverti mapping: da {original: standard} a {standard: original}
            # Ma dobbiamo mappare usando i nomi normalizzati
            reverse_mapping = {}
            for orig_col, std_col in header_mapping.items():
                normalized_orig = normalize_column_name(orig_col)
                if normalized_orig in df.columns:
                    reverse_mapping[normalized_orig] = std_col
            
            # Rinomina colonne
            df = df.rename(columns=reverse_mapping)
            logger.info(f"[PARSER] Header mapping applied: {len(header_mapping)} columns mapped")
        
        # Calcola schema_score (prima della normalizzazione valori)
        schema_score = calculate_schema_score(df)
        
        # Value normalization: normalizza valori per ogni riga
        wines_data = []
        for index, row in df.iterrows():
            try:
                # Converte riga in dict
                row_dict = row.to_dict()
                
                # Normalizza valori
                normalized_row = normalize_values(row_dict)
                
                # Filtra SOLO righe chiaramente vuote o placeholder
                # Stage 1 deve pulire ma NON togliere vini validi - lascia che Stage 3 gestisca righe incomplete
                name = normalized_row.get('name', '').strip()
                
                # Name invalido: vuoto o placeholder
                is_invalid_name = (
                    not name or 
                    len(name) == 0 or 
                    name.lower() in ['nan', 'none', 'null', 'n/a', 'na', 'undefined', '', ' ']
                )
                
                # Verifica se la riga ha dati significativi (potrebbe essere un vino anche senza name valido)
                has_meaningful_data = (
                    normalized_row.get('winery') or 
                    normalized_row.get('qty', 0) > 0 or 
                    normalized_row.get('price') is not None or
                    normalized_row.get('vintage') is not None
                )
                
                # Riga completamente vuota: name invalido E nessun dato significativo
                is_completely_empty = is_invalid_name and not has_meaningful_data
                
                # Conserva se: name valido OPPURE ha dati significativi (lascia che Stage 3 gestisca)
                if not is_completely_empty:
                    wines_data.append(normalized_row)
                else:
                    logger.debug(
                        f"[PARSER] Riga {index} scartata: completamente vuota "
                        f"(name='{name[:30] if name else 'EMPTY'}', has_data={has_meaningful_data})"
                    )
            except Exception as e:
                logger.warning(f"[PARSER] Error normalizing row {index}: {e}")
                continue
        
        # Validation: valida con Pydantic
        valid_wines, rejected_wines, validation_stats = validate_batch(wines_data)
        
        # Converti WineItemModel in dict per compatibilità
        wines_data_valid = [wine_model_to_dict(wine) for wine in valid_wines]
        
        rows_valid = validation_stats['rows_valid']
        rows_rejected = validation_stats['rows_rejected']
        
        # Calcola valid_rows
        valid_rows = rows_valid / rows_total if rows_total > 0 else 0.0
        
        # Calcola metriche
        elapsed_ms = (time.time() - start_time) * 1000
        
        metrics = {
            'schema_score': schema_score,
            'valid_rows': valid_rows,
            'rows_total': rows_total,
            'rows_valid': rows_valid,
            'rows_rejected': rows_rejected,
            'rejection_reasons': validation_stats['rejection_reasons'],
            'elapsed_ms': elapsed_ms,
            'parse_info': parse_info,
            'header_mapping': header_mapping
        }
        
        # Decisione: se supera soglie → SALVA, altrimenti → Stage 2
        if schema_score >= config.schema_score_th and valid_rows >= config.min_valid_rows:
            decision = 'save'
            logger.info(
                f"[PARSER] Stage 1 SUCCESS: schema_score={schema_score:.2f} >= {config.schema_score_th}, "
                f"valid_rows={valid_rows:.2f} >= {config.min_valid_rows} → SALVA"
            )
        else:
            decision = 'escalate_to_stage2'
            logger.info(
                f"[PARSER] Stage 1 INSUFFICIENT: schema_score={schema_score:.2f} < {config.schema_score_th} "
                f"or valid_rows={valid_rows:.2f} < {config.min_valid_rows} → Stage 2"
            )
        
        # Logging JSON strutturato
        log_json(
            level='info',
            message=f"Stage 1 parse completed: decision={decision}",
            file_name=file_name,
            ext=ext_normalized,
            stage='csv_parse',
            schema_score=schema_score,
            valid_rows=valid_rows,
            rows_total=rows_total,
            rows_valid=rows_valid,
            rows_rejected=rows_rejected,
            elapsed_ms=elapsed_ms,
            decision=decision
        )
        
        return wines_data_valid, metrics, decision
        
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"[PARSER] Error in Stage 1: {e}", exc_info=True)
        
        # Log errore
        log_json(
            level='error',
            message=f"Stage 1 parse failed: {str(e)}",
            file_name=file_name,
            ext=ext or 'unknown',
            stage='csv_parse',
            elapsed_ms=elapsed_ms,
            decision='error'
        )
        
        raise

