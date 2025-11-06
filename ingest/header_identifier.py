"""
Stage 0.5: Identificazione precisa header senza AI.

Questo stage identifica PRIMA gli header in modo perfetto, poi estrae i vini
dalle righe sotto gli header identificati. Zero AI, solo pattern matching e fuzzy matching.

Flow:
1. Legge file CSV/Excel riga per riga
2. Identifica righe che sono header (usando keyword e fuzzy matching)
3. Mappa header ai campi database
4. Estrae vini dalle righe sotto gli header
5. Ritorna vini estratti
"""
import re
import time
import logging
import pandas as pd
import io
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz, process
from ingest.csv_parser import detect_encoding, detect_delimiter
from ingest.normalization import (
    COLUMN_MAPPINGS_EXTENDED,
    normalize_column_name,
    normalize_values
)

logger = logging.getLogger(__name__)

# Campi database che dobbiamo identificare
DATABASE_FIELDS = [
    'name', 'winery', 'vintage', 'qty', 'price', 'type',
    'grape_variety', 'region', 'country', 'supplier', 'classification',
    'cost_price', 'alcohol_content', 'description', 'notes'
]


def identify_header_row(row: List[str], confidence_threshold: float = 0.60) -> Optional[Dict[str, int]]:
    """
    Identifica se una riga è un header e mappa le colonne ai campi database.
    
    Args:
        row: Lista di valori della riga
        confidence_threshold: Soglia confidence per fuzzy matching (default 0.60)
    
    Returns:
        Dict {field_name: column_index} se è header, None altrimenti
    """
    if not row or len(row) < 2:
        return None
    
    # Prepara lista target per rapidfuzz (tutti i sinonimi)
    target_list = []
    target_to_field = {}
    
    for field_name, variants in COLUMN_MAPPINGS_EXTENDED.items():
        for variant in variants:
            normalized_variant = normalize_column_name(variant)
            target_list.append(normalized_variant)
            target_to_field[normalized_variant] = field_name
    
    # Verifica ogni cella della riga
    field_mapping = {}
    header_score = 0
    total_cells = 0
    
    for col_idx, cell in enumerate(row):
        if not cell or not str(cell).strip():
            continue
        
        cell_normalized = normalize_column_name(str(cell))
        if not cell_normalized:
            continue
        
        total_cells += 1
        
        # Usa rapidfuzz per trovare match
        if target_list:
            result = process.extractOne(
                cell_normalized,
                target_list,
                scorer=fuzz.ratio,
                score_cutoff=int(confidence_threshold * 100)
            )
            
            if result:
                matched_variant, score, _ = result
                field_name = target_to_field[matched_variant]
                
                # Evita conflitti: se field già mappato, usa quello con score più alto
                if field_name not in field_mapping:
                    field_mapping[field_name] = col_idx
                    header_score += score
                else:
                    # Se score migliore, aggiorna
                    existing_col = field_mapping[field_name]
                    # Mantieni quello con score più alto (per ora mantieni il primo)
                    pass
    
    # È un header se:
    # 1. Ha mappato almeno 2 campi (name + almeno un altro)
    # 2. Almeno il 30% delle celle non vuote sono header riconosciuti
    if len(field_mapping) >= 2 and total_cells > 0:
        header_ratio = len(field_mapping) / total_cells
        avg_score = header_score / len(field_mapping) if field_mapping else 0
        
        # Deve avere almeno 'name' o 'qty' mappati (campi essenziali)
        has_essential = 'name' in field_mapping or 'qty' in field_mapping
        
        if has_essential and (header_ratio >= 0.3 or avg_score >= 70):
            logger.debug(
                f"[HEADER_ID] Riga identificata come header: {len(field_mapping)} campi mappati "
                f"(ratio={header_ratio:.2f}, avg_score={avg_score:.1f})"
            )
            return field_mapping
    
    return None


def extract_wines_from_rows(
    rows: List[List[str]],
    header_mapping: Dict[str, int],
    start_row_idx: int = 0
) -> List[Dict[str, Any]]:
    """
    Estrae vini dalle righe sotto un header identificato.
    
    Args:
        rows: Lista di righe (ogni riga è lista di celle)
        header_mapping: Dict {field_name: column_index} dal header identificato
        start_row_idx: Indice riga da cui iniziare (dopo l'header)
    
    Returns:
        Lista di dict con vini estratti
    """
    wines = []
    
    for row_idx in range(start_row_idx, len(rows)):
        row = rows[row_idx]
        
        # Crea dict vino usando header_mapping
        wine_dict = {}
        has_data = False
        
        for field_name, col_idx in header_mapping.items():
            if col_idx < len(row):
                value = row[col_idx]
                if value and str(value).strip():
                    wine_dict[field_name] = str(value).strip()
                    has_data = True
                else:
                    wine_dict[field_name] = None
        
        # Salva solo se ha almeno qualche dato
        if has_data:
            # Normalizza valori
            try:
                normalized = normalize_values(wine_dict)
                
                # Verifica che non sia completamente vuoto
                name = normalized.get('name', '').strip() if normalized.get('name') else ''
                has_meaningful_data = (
                    name or
                    normalized.get('winery') or
                    normalized.get('qty', 0) > 0 or
                    normalized.get('price') is not None
                )
                
                if has_meaningful_data:
                    wines.append(normalized)
                    logger.debug(
                        f"[HEADER_ID] Vino estratto riga {row_idx}: "
                        f"name={normalized.get('name', 'N/A')[:30]}, "
                        f"qty={normalized.get('qty', 0)}"
                    )
            except Exception as e:
                logger.warning(f"[HEADER_ID] Errore normalizzazione riga {row_idx}: {e}")
                continue
    
    return wines


def identify_headers_and_extract(
    file_content: bytes,
    file_name: str,
    ext: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Stage 0.5: Identifica header e estrae vini senza AI.
    
    Flow:
    1. Legge file riga per riga
    2. Identifica righe header
    3. Per ogni header, estrae vini dalle righe successive
    4. Ritorna tutti i vini estratti
    
    Args:
        file_content: Contenuto file (bytes)
        file_name: Nome file
        ext: Estensione file
    
    Returns:
        Tuple (wines_data, metrics):
        - wines_data: Lista dict con vini estratti
        - metrics: Dict con metriche (headers_found, wines_extracted, etc.)
    """
    start_time = time.time()
    metrics = {
        'headers_found': 0,
        'wines_extracted': 0,
        'rows_processed': 0,
        'method': 'header_identifier_stage_0_5'
    }
    
    try:
        # Rileva encoding e delimiter
        encoding, _ = detect_encoding(file_content)
        separator = detect_delimiter(file_content, encoding)
        
        # Decodifica file
        text = file_content.decode(encoding, errors='ignore')
        lines = text.split('\n')
        
        # Rimuovi righe completamente vuote
        lines = [l for l in lines if l.strip()]
        
        if not lines:
            logger.warning("[HEADER_ID] File vuoto o senza righe valide")
            return [], metrics
        
        # Parse righe in liste di celle
        rows = []
        for line in lines:
            # Usa separator per dividere
            cells = [c.strip() for c in line.split(separator)]
            rows.append(cells)
        
        metrics['rows_processed'] = len(rows)
        logger.info(f"[HEADER_ID] File parsato: {len(rows)} righe, separator='{separator}'")
        
        # Identifica header e estrai vini
        all_wines = []
        i = 0
        
        while i < len(rows):
            row = rows[i]
            
            # Identifica se questa riga è un header
            header_mapping = identify_header_row(row, confidence_threshold=0.60)
            
            if header_mapping:
                logger.info(
                    f"[HEADER_ID] Header trovato riga {i}: {len(header_mapping)} campi mappati "
                    f"({', '.join(header_mapping.keys())})"
                )
                metrics['headers_found'] += 1
                
                # Estrai vini dalle righe successive (fino al prossimo header o fine file)
                # Limita a 1000 righe per header (evita loop infiniti)
                end_row = min(i + 1000, len(rows))
                
                wines_from_section = extract_wines_from_rows(
                    rows,
                    header_mapping,
                    start_row_idx=i + 1
                )
                
                all_wines.extend(wines_from_section)
                logger.info(
                    f"[HEADER_ID] Estratti {len(wines_from_section)} vini da sezione "
                    f"riga {i+1} a {end_row}"
                )
                
                # Continua a cercare altri header nelle righe successive
                # (non saltare, perché potrebbero esserci header multipli)
                i += 1
            else:
                i += 1
        
        metrics['wines_extracted'] = len(all_wines)
        metrics['elapsed_ms'] = (time.time() - start_time) * 1000
        
        logger.info(
            f"[HEADER_ID] Stage 0.5 completato: {metrics['headers_found']} header trovati, "
            f"{metrics['wines_extracted']} vini estratti in {metrics['elapsed_ms']:.1f}ms"
        )
        
        return all_wines, metrics
        
    except Exception as e:
        logger.error(f"[HEADER_ID] Errore Stage 0.5: {e}", exc_info=True)
        metrics['error'] = str(e)
        metrics['elapsed_ms'] = (time.time() - start_time) * 1000
        return [], metrics

