"""
Header Detector - Identifica header multipli e ripetuti in CSV/Excel.

Rileva quando un file contiene header su più righe o header ripetuti,
dividendo il file in sezioni separate per processarle correttamente.
"""
import re
import logging
from typing import List, Tuple, Dict, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

# Keywords comuni per identificare header
HEADER_KEYWORDS = [
    'indice', 'id', 'etichetta', 'label', 'nome', 'name', 'cantina', 'winery', 'producer',
    'vintage', 'annata', 'anno', 'qty', 'quantità', 'quantity', 'pezzi', 'prezzo', 'price',
    'costo', 'tipo', 'type', 'uvaggio', 'grape', 'regione', 'region', 'nazione', 'country',
    'fornitore', 'supplier', 'classificazione', 'classification', 'doc', 'docg', 'igt',
    'gradazione', 'alcohol', 'descrizione', 'description', 'note', 'note'
]

# Keywords per identificare header di sezioni produttori/cantine
PRODUCER_SECTION_KEYWORDS = [
    'produttore', 'producer', 'cantina', 'winery', 'casa', 'azienda', 'domaine', 'chateau',
    'marca', 'brand', 'fornitore', 'supplier', 'rappresentato', 'rappresentati'
]

# Keywords per identificare righe che sono produttori (non vini)
PRODUCER_ROW_KEYWORDS = [
    'produttore', 'producer', 'cantina', 'winery', 'casa', 'azienda', 'domaine', 'chateau',
    'marca', 'brand', 'fornitore', 'supplier', 'rappresentato', 'rappresentati', 'rappresentante'
]


def is_producer_section_header(row: List[str]) -> bool:
    """
    Verifica se una riga è un header di sezione produttori/cantine.
    
    Args:
        row: Lista di valori della riga
    
    Returns:
        True se la riga sembra essere un header di sezione produttori
    """
    if len(row) < 1:
        return False
    
    # Controlla se contiene keyword di sezione produttori
    for cell in row:
        if not cell or str(cell).strip() == '':
            continue
        
        cell_lower = str(cell).strip().lower()
        for keyword in PRODUCER_SECTION_KEYWORDS:
            if keyword in cell_lower:
                # Verifica che non sia un header normale (non ha molte colonne)
                if len([c for c in row if c and str(c).strip()]) <= 3:
                    return True
    
    return False


def is_producer_row(row: List[str], current_producer: Optional[str] = None) -> bool:
    """
    Verifica se una riga rappresenta un produttore (non un vino).
    
    Una riga è un produttore se:
    - Contiene keyword di produttore E ha poche colonne con dati
    - O è una riga con solo testo (probabilmente nome produttore)
    - O ha un pattern tipico di intestazione produttore
    
    Args:
        row: Lista di valori della riga
        current_producer: Produttore corrente (per confronto)
    
    Returns:
        True se la riga sembra essere un produttore
    """
    if len(row) < 1:
        return False
    
    # Conta colonne con dati significativi
    non_empty_cells = [c for c in row if c and str(c).strip() and str(c).strip().lower() not in ['nan', 'none', 'null', '']]
    
    # Se ha solo 1-2 colonne con dati, potrebbe essere un produttore
    if len(non_empty_cells) <= 2:
        # Verifica se contiene keyword di produttore
        for cell in non_empty_cells:
            cell_lower = str(cell).strip().lower()
            for keyword in PRODUCER_ROW_KEYWORDS:
                if keyword in cell_lower:
                    return True
        
        # Se è una riga con solo testo (probabilmente nome produttore)
        # e non contiene numeri o pattern di vino
        first_cell = non_empty_cells[0] if non_empty_cells else ''
        if first_cell:
            # Non è un produttore se contiene pattern tipici di vino (anno, quantità, prezzo)
            has_wine_pattern = (
                bool(re.search(r'\b(19|20)\d{2}\b', first_cell)) or  # Anno
                bool(re.search(r'\d+\s*(bott|pezzi|pz|qty)', first_cell, re.I)) or  # Quantità
                bool(re.search(r'€|\d+[,.]\d+', first_cell))  # Prezzo
            )
            
            if not has_wine_pattern and len(first_cell) > 3:
                # Potrebbe essere un produttore se non è già il produttore corrente
                if current_producer and first_cell.lower() == current_producer.lower():
                    return False  # È lo stesso produttore, non una nuova riga produttore
                return True
    
    return False


def is_header_row(row: List[str], min_columns: int = 3) -> bool:
    """
    Verifica se una riga è probabilmente un header.
    
    Args:
        row: Lista di valori della riga
        min_columns: Numero minimo di colonne per essere considerato header
    
    Returns:
        True se la riga sembra essere un header
    """
    if len(row) < min_columns:
        return False
    
    # Conta quante colonne contengono keyword di header
    header_matches = 0
    total_non_empty = 0
    
    for cell in row:
        if not cell or str(cell).strip() == '':
            continue
        
        cell_lower = str(cell).strip().lower()
        total_non_empty += 1
        
        # Verifica se contiene keyword di header
        for keyword in HEADER_KEYWORDS:
            if keyword in cell_lower:
                header_matches += 1
                break
    
    # Se almeno 2 colonne contengono keyword di header, è probabilmente un header
    # O se tutte le colonne non vuote sono keyword (header completo)
    if total_non_empty == 0:
        return False
    
    match_ratio = header_matches / total_non_empty if total_non_empty > 0 else 0
    
    # Header se: almeno 2 keyword O match_ratio > 0.4 (40% delle colonne sono keyword)
    is_header = header_matches >= 2 or (match_ratio > 0.4 and total_non_empty >= min_columns)
    
    return is_header


def detect_multiple_headers(
    file_content: bytes,
    encoding: str,
    separator: str,
    max_rows_to_check: int = 500
) -> List[Tuple[int, List[str]]]:
    """
    Identifica tutte le righe header nel file (inclusi header multipli/ripetuti).
    
    Args:
        file_content: Contenuto file (bytes)
        encoding: Encoding file
        separator: Separatore CSV
    
    Returns:
        Lista di tuple (row_index, header_columns) per ogni header trovato
    """
    try:
        text = file_content.decode(encoding, errors='ignore')
        lines = text.split('\n')
        
        headers_found = []
        
        # Analizza prime max_rows_to_check righe per trovare header
        for idx, line in enumerate(lines[:max_rows_to_check]):
            if not line.strip():
                continue
            
            # Split riga per separatore
            row = [cell.strip() for cell in line.split(separator)]
            
            # Verifica se è un header
            if is_header_row(row):
                headers_found.append((idx, row))
                logger.debug(
                    f"[HEADER_DETECTOR] Header trovato alla riga {idx}: "
                    f"{row[:5]}..." if len(row) > 5 else str(row)
                )
        
        logger.info(
            f"[HEADER_DETECTOR] Trovati {len(headers_found)} header nel file "
            f"(prime {max_rows_to_check} righe analizzate)"
        )
        
        return headers_found
        
    except Exception as e:
        logger.warning(f"[HEADER_DETECTOR] Errore rilevamento header multipli: {e}")
        return []


def split_file_by_headers(
    file_content: bytes,
    encoding: str,
    separator: str,
    headers_found: List[Tuple[int, List[str]]]
) -> List[Tuple[int, bytes]]:
    """
    Divide il file in sezioni basate su header multipli.
    
    Ogni sezione inizia con un header e contiene tutte le righe fino al prossimo header.
    
    Args:
        file_content: Contenuto file (bytes)
        encoding: Encoding file
        separator: Separatore CSV
        headers_found: Lista di (row_index, header_columns) trovati
    
    Returns:
        Lista di tuple (section_index, section_content_bytes) per ogni sezione
    """
    if len(headers_found) <= 1:
        # Nessun header multiplo, ritorna file intero
        return [(0, file_content)]
    
    try:
        text = file_content.decode(encoding, errors='ignore')
        lines = text.split('\n')
        
        sections = []
        
        # Crea sezioni: ogni sezione inizia con un header e finisce prima del prossimo
        for section_idx, (header_idx, header_columns) in enumerate(headers_found):
            # Indice inizio sezione (header incluso)
            start_idx = header_idx
            
            # Indice fine sezione (prima del prossimo header, o fine file)
            if section_idx < len(headers_found) - 1:
                end_idx = headers_found[section_idx + 1][0]
            else:
                end_idx = len(lines)
            
            # Estrai righe della sezione
            section_lines = lines[start_idx:end_idx]
            section_text = '\n'.join(section_lines)
            section_bytes = section_text.encode(encoding)
            
            sections.append((section_idx, section_bytes))
            
            logger.debug(
                f"[HEADER_DETECTOR] Sezione {section_idx}: righe {start_idx}-{end_idx-1} "
                f"({len(section_lines)} righe, header: {header_columns[:3]}...)"
            )
        
        logger.info(
            f"[HEADER_DETECTOR] File diviso in {len(sections)} sezioni basate su header multipli"
        )
        
        return sections
        
    except Exception as e:
        logger.error(f"[HEADER_DETECTOR] Errore divisione file per header: {e}", exc_info=True)
        # Fallback: ritorna file intero
        return [(0, file_content)]


def process_section_with_producers(
    section_lines: List[str],
    separator: str,
    encoding: str
) -> pd.DataFrame:
    """
    Processa una sezione CSV riconoscendo righe produttori e applicandole ai vini successivi.
    
    Args:
        section_lines: Righe della sezione (prima riga è header)
        separator: Separatore CSV
        encoding: Encoding file
    
    Returns:
        DataFrame con vini processati (winery applicato da righe produttore)
    """
    if len(section_lines) < 2:
        return pd.DataFrame()
    
    # Prima riga è header
    header_line = section_lines[0]
    header_columns = [c.strip() for c in header_line.split(separator)]
    
    # Verifica se è una sezione produttori
    is_producer_section = is_producer_section_header(header_columns)
    
    wines_data = []
    current_producer = None
    
    # Processa righe dati
    for line_idx, line in enumerate(section_lines[1:], start=1):
        if not line.strip():
            continue
        
        row = [c.strip() for c in line.split(separator)]
        
        # Verifica se è una riga produttore
        if is_producer_row(row, current_producer):
            # Estrai nome produttore (prima colonna non vuota)
            producer_name = None
            for cell in row:
                if cell and cell.strip() and cell.strip().lower() not in ['nan', 'none', 'null', '']:
                    producer_name = cell.strip()
                    break
            
            if producer_name:
                current_producer = producer_name
                logger.debug(
                    f"[HEADER_DETECTOR] Trovato produttore nella sezione: '{current_producer}' "
                    f"(riga {line_idx})"
                )
            continue  # Salta riga produttore, non è un vino
        
        # È una riga vino: crea dict con dati
        wine_dict = {}
        for col_idx, col_name in enumerate(header_columns):
            if col_idx < len(row):
                wine_dict[col_name] = row[col_idx]
            else:
                wine_dict[col_name] = ''
        
        # Applica produttore corrente se disponibile e winery non presente
        if current_producer:
            # Se winery non è presente o è vuoto, usa produttore corrente
            winery_col = None
            for col in ['winery', 'cantina', 'producer', 'produttore']:
                if col in wine_dict:
                    winery_col = col
                    break
            
            if not winery_col or not wine_dict.get(winery_col) or wine_dict[winery_col].strip() == '':
                # Aggiungi colonna winery se non esiste
                if 'winery' not in wine_dict:
                    wine_dict['winery'] = current_producer
                else:
                    wine_dict[winery_col] = current_producer
                
                logger.debug(
                    f"[HEADER_DETECTOR] Applicato produttore '{current_producer}' al vino riga {line_idx}"
                )
        
        wines_data.append(wine_dict)
    
    if not wines_data:
        return pd.DataFrame()
    
    # Crea DataFrame da lista di dict
    df = pd.DataFrame(wines_data)
    
    logger.info(
        f"[HEADER_DETECTOR] Sezione processata: {len(wines_data)} vini, "
        f"produttore corrente: {current_producer or 'N/A'}"
    )
    
    return df


def parse_csv_with_multiple_headers(
    file_content: bytes,
    separator: Optional[str] = None,
    encoding: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Parse CSV identificando e gestendo header multipli/ripetuti.
    
    Se trova header multipli, divide il file in sezioni e le processa separatamente,
    poi unisce i risultati.
    
    Args:
        file_content: Contenuto file (bytes)
        separator: Separatore CSV (se None, auto-rileva)
        encoding: Encoding file (se None, auto-rileva)
    
    Returns:
        Tuple (DataFrame unificato, detection_info)
    """
    from ingest.csv_parser import detect_encoding, detect_delimiter
    
    # Rileva encoding e separator se non forniti
    if encoding is None:
        encoding, enc_confidence = detect_encoding(file_content)
    else:
        enc_confidence = 1.0
    
    if separator is None:
        separator = detect_delimiter(file_content, encoding)
    
    # Identifica header multipli
    headers_found = detect_multiple_headers(file_content, encoding, separator)
    
    detection_info = {
        'encoding': encoding,
        'encoding_confidence': enc_confidence,
        'separator': separator,
        'multiple_headers_detected': len(headers_found) > 1,
        'headers_count': len(headers_found),
        'method': 'multiple_headers' if len(headers_found) > 1 else 'single_header'
    }
    
    # Se non ci sono header multipli, parse normale
    if len(headers_found) <= 1:
        import io
        df = pd.read_csv(
            io.BytesIO(file_content),
            sep=separator,
            encoding=encoding,
            on_bad_lines='skip',
            engine='python',
            skipinitialspace=True,
            dtype=str
        )
        detection_info['rows'] = len(df)
        detection_info['columns'] = len(df.columns)
        return df, detection_info
    
    # Header multipli: divide e processa sezioni
    sections = split_file_by_headers(file_content, encoding, separator, headers_found)
    
    all_dataframes = []
    
    for section_idx, section_bytes in sections:
        try:
            # Decodifica sezione per processare righe produttori
            section_text = section_bytes.decode(encoding, errors='ignore')
            section_lines = section_text.split('\n')
            section_lines = [l for l in section_lines if l.strip()]  # Rimuovi righe vuote
            
            if len(section_lines) < 2:
                continue
            
            # Processa sezione riconoscendo righe produttori
            df_section = process_section_with_producers(section_lines, separator, encoding)
            
            if len(df_section) > 0:
                all_dataframes.append(df_section)
                logger.info(
                    f"[HEADER_DETECTOR] Sezione {section_idx} processata: "
                    f"{len(df_section)} vini, {len(df_section.columns)} colonne"
                )
        except Exception as e:
            logger.warning(
                f"[HEADER_DETECTOR] Errore processing sezione {section_idx}: {e}, saltata",
                exc_info=True
            )
            # Fallback: parse normale sezione
            try:
                import io
                df_section = pd.read_csv(
                    io.BytesIO(section_bytes),
                    sep=separator,
                    encoding=encoding,
                    on_bad_lines='skip',
                    engine='python',
                    skipinitialspace=True,
                    dtype=str
                )
                if len(df_section) > 0:
                    all_dataframes.append(df_section)
            except Exception as fallback_error:
                logger.warning(
                    f"[HEADER_DETECTOR] Fallback parsing fallito per sezione {section_idx}: {fallback_error}"
                )
                continue
    
    if not all_dataframes:
        # Nessuna sezione valida, fallback a parse normale
        logger.warning("[HEADER_DETECTOR] Nessuna sezione valida, fallback a parse normale")
        import io
        df = pd.read_csv(
            io.BytesIO(file_content),
            sep=separator,
            encoding=encoding,
            on_bad_lines='skip',
            engine='python',
            skipinitialspace=True,
            dtype=str
        )
        detection_info['rows'] = len(df)
        detection_info['columns'] = len(df.columns)
        return df, detection_info
    
    # Unisci tutti i DataFrame
    # Normalizza colonne prima di unire (potrebbero avere nomi leggermente diversi)
    normalized_dfs = []
    for df in all_dataframes:
        # Normalizza nomi colonne (lowercase, rimuovi spazi)
        df.columns = [str(col).strip().lower() for col in df.columns]
        normalized_dfs.append(df)
    
    # Unisci (concat) - mantiene tutte le colonne
    df_combined = pd.concat(normalized_dfs, ignore_index=True)
    
    logger.info(
        f"[HEADER_DETECTOR] File con header multipli processato: "
        f"{len(sections)} sezioni → {len(df_combined)} righe totali, "
        f"{len(df_combined.columns)} colonne"
    )
    
    detection_info['rows'] = len(df_combined)
    detection_info['columns'] = len(df_combined.columns)
    detection_info['sections_processed'] = len(sections)
    
    return df_combined, detection_info

