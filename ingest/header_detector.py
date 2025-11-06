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

# Mapping completo campi database → keyword per identificare righe header/sezioni
# Usato per riconoscere righe che sono valori di campi specifici (non vini)
DATABASE_FIELD_KEYWORDS = {
    'winery': [
        'produttore', 'producer', 'cantina', 'winery', 'casa', 'azienda', 'domaine', 'chateau',
        'marca', 'brand', 'casa vinicola', 'fattoria', 'azienda vinicola', 'casa produttrice',
        'produttore vino', 'azienda produttrice', 'marca vino', 'brand vino', 'cantina produttrice',
        'fattoria vinicola', 'casa vinicola', 'domaine', 'château', 'chateau'
    ],
    'name': [
        'nome', 'name', 'vino', 'wine', 'wine name', 'nome vino', 'denominazione', 'etichetta',
        'prodotto', 'articolo', 'descrizione', 'titolo', 'label', 'nome prodotto', 'denominazione vino'
    ],
    'grape_variety': [
        'uvaggio', 'grape', 'grape variety', 'varietà', 'varietà uve', 'vitigno', 'vitigni',
        'ceppo', 'ceppi', 'uva', 'uve', 'grape variety', 'varietà uva', 'uvaggio vino',
        'vitigno principale', 'varietà principale', 'grape varietal', 'varietal'
    ],
    'region': [
        'regione', 'region', 'zona', 'area', 'territorio', 'terroir', 'zona di produzione',
        'area di produzione', 'territorio di produzione', 'zona vinicola', 'area vinicola',
        'territorio vinicolo', 'zona geografica', 'area geografica', 'territorio geografico'
    ],
    'country': [
        'nazione', 'country', 'paese', 'nazione di origine', 'paese di origine', 'origine',
        'nazione produzione', 'paese produzione', 'nazione vinicola', 'paese vinicolo',
        'nazione di produzione', 'paese di produzione', 'nazione origine', 'paese origine'
    ],
    'supplier': [
        'fornitore', 'supplier', 'rappresentato', 'rappresentati', 'rappresentante',
        'importatore', 'distributore', 'fornitore vino', 'supplier wine', 'importatore vino',
        'distributore vino', 'fornitore principale', 'supplier principale', 'rappresentato da',
        'rappresentati da', 'importato da', 'distribuito da', 'fornito da'
    ],
    'classification': [
        'classificazione', 'classification', 'denominazione', 'denomination', 'doc', 'docg',
        'igt', 'igp', 'vdt', 'aoc', 'aop', 'do', 'doca', 'denominazione di origine',
        'denominazione origine', 'classificazione vino', 'denominazione vino', 'docg vino',
        'doc vino', 'igt vino', 'igp vino', 'vdt vino', 'aoc vino', 'aop vino'
    ],
    'type': [
        'tipo', 'type', 'wine_type', 'categoria', 'tipo vino', 'categoria vino',
        'colore', 'color', 'stile', 'style', 'tipo prodotto', 'categoria prodotto'
    ],
    'vintage': [
        'vintage', 'annata', 'anno', 'year', 'anno produzione', 'vintage year',
        'anno vendemmia', 'vendemmia', 'yr', 'anno vinificazione', 'year vintage'
    ],
    'alcohol_content': [
        'gradazione', 'alcohol', 'alcohol content', 'gradazione alcolica', 'alcol',
        'percentuale alcolica', 'alcohol %', 'alc %', 'gradazione %', 'alcohol content %',
        'percentuale alcol', 'alcol %', 'gradazione alcol', 'alcohol percentage'
    ],
    'description': [
        'descrizione', 'description', 'note descrittive', 'descrizione vino', 'description wine',
        'note prodotto', 'descrizione prodotto', 'descrizione articolo', 'note articolo'
    ],
    'notes': [
        'note', 'notes', 'osservazioni', 'observations', 'note aggiuntive', 'note extra',
        'note vino', 'notes wine', 'osservazioni vino', 'note prodotto', 'notes product'
    ]
}

# Keywords per identificare header di sezioni (qualsiasi campo database)
SECTION_HEADER_KEYWORDS = []
for field_keywords in DATABASE_FIELD_KEYWORDS.values():
    SECTION_HEADER_KEYWORDS.extend(field_keywords)
SECTION_HEADER_KEYWORDS = list(set(SECTION_HEADER_KEYWORDS))  # Rimuovi duplicati

# Keywords per identificare righe che sono valori di campi (non vini)
FIELD_VALUE_ROW_KEYWORDS = SECTION_HEADER_KEYWORDS.copy()


def detect_field_from_row(row: List[str]) -> Optional[str]:
    """
    Identifica quale campo database rappresenta questa riga (se è un header di sezione).
    
    Args:
        row: Lista di valori della riga
    
    Returns:
        Nome campo database (es. 'winery', 'region', 'grape_variety') o None
    """
    if len(row) < 1:
        return None
    
    # Conta colonne non vuote
    non_empty_cells = [c for c in row if c and str(c).strip()]
    
    # Se ha poche colonne (<= 3), potrebbe essere un header di sezione
    if len(non_empty_cells) <= 3:
        # Controlla ogni cella per keyword di campi database
        for cell in non_empty_cells:
            cell_lower = str(cell).strip().lower()
            
            # Cerca match in tutti i campi database
            for field_name, keywords in DATABASE_FIELD_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in cell_lower:
                        logger.debug(
                            f"[HEADER_DETECTOR] Riga identificata come header '{field_name}': "
                            f"keyword '{keyword}' trovata in '{cell_lower}'"
                        )
                        return field_name
    
    return None


def is_section_header_row(row: List[str]) -> bool:
    """
    Verifica se una riga è un header di sezione (qualsiasi campo database).
    
    Args:
        row: Lista di valori della riga
    
    Returns:
        True se la riga sembra essere un header di sezione
    """
    return detect_field_from_row(row) is not None


def detect_field_value_row(
    row: List[str],
    current_field_values: Dict[str, str]
) -> Optional[Tuple[str, str]]:
    """
    Identifica se una riga rappresenta un valore di campo database (non un vino).
    
    Una riga è un valore di campo se:
    - Ha poche colonne con dati (1-2)
    - Non contiene pattern tipici di vino (anno, quantità, prezzo)
    - Potrebbe essere un valore di campo (produttore, regione, uvaggio, etc.)
    
    Args:
        row: Lista di valori della riga
        current_field_values: Dict con valori correnti dei campi (per evitare duplicati)
    
    Returns:
        Tuple (field_name, field_value) se è un valore di campo, None altrimenti
    """
    if len(row) < 1:
        return None
    
    # Conta colonne con dati significativi
    non_empty_cells = [
        c for c in row 
        if c and str(c).strip() and str(c).strip().lower() not in ['nan', 'none', 'null', '']
    ]
    
    # Se ha solo 1-2 colonne con dati, potrebbe essere un valore di campo
    if len(non_empty_cells) <= 2:
        first_cell = non_empty_cells[0] if non_empty_cells else ''
        
        if not first_cell or len(first_cell) < 2:
            return None
        
        # Non è un valore di campo se contiene pattern tipici di vino
        has_wine_pattern = (
            bool(re.search(r'\b(19|20)\d{2}\b', first_cell)) or  # Anno
            bool(re.search(r'\d+\s*(bott|pezzi|pz|qty|quantità)', first_cell, re.I)) or  # Quantità
            bool(re.search(r'€|\d+[,.]\d+\s*(eur|euro|€)', first_cell, re.I))  # Prezzo
        )
        
        if has_wine_pattern:
            return None  # È probabilmente un vino, non un valore di campo
        
        # Verifica se è già un valore corrente (evita duplicati)
        first_cell_lower = first_cell.lower().strip()
        for field_name, current_value in current_field_values.items():
            if current_value and first_cell_lower == current_value.lower().strip():
                return None  # È lo stesso valore, non una nuova riga
        
        # Prova a identificare il campo guardando il contesto
        # Se la riga contiene keyword di un campo, è probabilmente quel campo
        for field_name, keywords in DATABASE_FIELD_KEYWORDS.items():
            for keyword in keywords:
                if keyword in first_cell_lower:
                    # Verifica che non sia solo una keyword (deve essere un valore)
                    if len(first_cell) > len(keyword) + 2:  # Valore più lungo della keyword
                        logger.debug(
                            f"[HEADER_DETECTOR] Riga identificata come valore '{field_name}': "
                            f"'{first_cell}' (keyword '{keyword}' trovata)"
                        )
                        return (field_name, first_cell.strip())
        
        # Se non ha keyword ma è solo testo senza pattern vino, potrebbe essere un valore generico
        # Prova a inferire il campo dal contesto (se abbiamo già altri valori)
        # Per ora, se è solo testo senza pattern, assumiamo che sia winery (più comune)
        if len(first_cell) > 3 and not has_wine_pattern:
            # Potrebbe essere winery, region, grape_variety, etc.
            # Per sicurezza, proviamo winery (più comune come header di sezione)
            logger.debug(
                f"[HEADER_DETECTOR] Riga identificata come possibile valore 'winery': "
                f"'{first_cell}' (solo testo, nessun pattern vino)"
            )
            return ('winery', first_cell.strip())
    
    return None


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


def process_section_with_field_values(
    section_lines: List[str],
    separator: str,
    encoding: str
) -> pd.DataFrame:
    """
    Processa una sezione CSV riconoscendo righe che sono valori di campi database
    (produttore, regione, uvaggio, nazione, etc.) e applicandole ai vini successivi.
    
    Args:
        section_lines: Righe della sezione (prima riga è header)
        separator: Separatore CSV
        encoding: Encoding file
    
    Returns:
        DataFrame con vini processati (campi applicati da righe header)
    """
    if len(section_lines) < 2:
        return pd.DataFrame()
    
    # Prima riga è header
    header_line = section_lines[0]
    header_columns = [c.strip() for c in header_line.split(separator)]
    
    # Identifica tipo sezione (se è un header di campo specifico)
    section_field = detect_field_from_row(header_columns)
    
    wines_data = []
    # Mantieni valori correnti per tutti i campi database
    current_field_values: Dict[str, str] = {}
    
    # Processa righe dati
    for line_idx, line in enumerate(section_lines[1:], start=1):
        if not line.strip():
            continue
        
        row = [c.strip() for c in line.split(separator)]
        
        # Verifica se è una riga valore di campo (non un vino)
        field_value = detect_field_value_row(row, current_field_values)
        
        if field_value:
            field_name, field_value_str = field_value
            # Aggiorna valore corrente del campo
            current_field_values[field_name] = field_value_str
            
            logger.debug(
                f"[HEADER_DETECTOR] Trovato valore campo '{field_name}': '{field_value_str}' "
                f"(riga {line_idx})"
            )
            continue  # Salta riga valore campo, non è un vino
        
        # È una riga vino: crea dict con dati
        wine_dict = {}
        for col_idx, col_name in enumerate(header_columns):
            if col_idx < len(row):
                wine_dict[col_name] = row[col_idx]
            else:
                wine_dict[col_name] = ''
        
        # Applica valori correnti dei campi se non presenti nel vino
        for field_name, field_value_str in current_field_values.items():
            if not field_value_str:
                continue
            
            # Trova colonna corrispondente al campo
            field_col = None
            field_keywords = DATABASE_FIELD_KEYWORDS.get(field_name, [])
            
            # Cerca colonna che corrisponde al campo
            for col_name in wine_dict.keys():
                col_lower = str(col_name).lower().strip()
                for keyword in field_keywords:
                    if keyword in col_lower:
                        field_col = col_name
                        break
                if field_col:
                    break
            
            # Se colonna non trovata o vuota, aggiungi/aggiorna
            if not field_col:
                # Usa nome campo standard se non esiste colonna corrispondente
                standard_field_names = {
                    'winery': 'winery',
                    'region': 'region',
                    'country': 'country',
                    'grape_variety': 'grape_variety',
                    'supplier': 'supplier',
                    'classification': 'classification',
                    'type': 'type',
                    'alcohol_content': 'alcohol_content',
                    'description': 'description',
                    'notes': 'notes'
                }
                field_col = standard_field_names.get(field_name, field_name)
            
            # Applica valore se colonna è vuota o non esiste
            if field_col not in wine_dict or not wine_dict.get(field_col) or wine_dict[field_col].strip() == '':
                wine_dict[field_col] = field_value_str
                
                logger.debug(
                    f"[HEADER_DETECTOR] Applicato campo '{field_name}'='{field_value_str}' "
                    f"al vino riga {line_idx}"
                )
        
        wines_data.append(wine_dict)
    
    if not wines_data:
        return pd.DataFrame()
    
    # Crea DataFrame da lista di dict
    df = pd.DataFrame(wines_data)
    
    logger.info(
        f"[HEADER_DETECTOR] Sezione processata: {len(wines_data)} vini, "
        f"campi applicati: {list(current_field_values.keys())}"
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
            
            # Processa sezione riconoscendo righe valori campi database
            df_section = process_section_with_field_values(section_lines, separator, encoding)
            
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

