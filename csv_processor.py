import pandas as pd
import io
import re
import logging
import chardet
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from ai_processor import ai_processor

logger = logging.getLogger(__name__)

# Dizionario completo di mapping colonne - espanso con più sinonimi
COLUMN_MAPPINGS = {
    'name': ['nome', 'vino', 'wine', 'wine name', 'nome vino', 'denominazione', 'etichetta', 'prodotto', 'articolo', 'descrizione', 'titolo'],
    'vintage': ['annata', 'year', 'vintage', 'anno', 'anno produzione', 'vintage year', 'anno vendemmia', 'vendemmia'],
    'producer': ['produttore', 'producer', 'winery', 'azienda', 'casa vinicola', 'marca', 'brand', 'cantina', 'fattoria', 'azienda vinicola', 'casa produttrice'],
    'grape_variety': ['uvaggio', 'vitigno', 'grape variety', 'varietà', 'grape_variety', 'grape', 'grapes', 'vitigni', 'varietà uva', 'uvaggio principale'],
    'region': ['regione', 'region', 'zona', 'area', 'area geografica', 'zona geografica', 'denominazione', 'regione/denominazione', 'territorio', 'zona di produzione'],
    'country': ['paese', 'country', 'nazione', 'nation', 'paese di origine', 'origine', 'provenienza'],
    'wine_type': ['tipo', 'type', 'wine_type', 'categoria', 'tipo vino', 'categoria vino', 'colore', 'tipologia'],
    'classification': ['classificazione', 'classification', 'doc', 'docg', 'igt', 'dop', 'igp', 'qualità', 'denominazione di origine'],
    'quantity': ['quantità', 'quantity', 'qty', 'q.tà', 'pezzi', 'bottiglie', 'quantità in magazzino', 'scorta', 'qta_magazzino', 'qta magazzino', 'disp', 'disponibilità', 'stock', 'q iniziale', 'q. iniziale', 'quantità iniziale', 'q iniz', 'q. iniz', 'q iniziale magazzino', 'quantità iniz', 'q iniziale stock'],
    'min_quantity': ['scorta minima', 'min quantity', 'quantità minima', 'min qty', 'scorta min', 'qta min', 'min stock'],
    'cost_price': ['costo', 'cost', 'prezzo acquisto', 'prezzo di acquisto', 'prezzo acquisto', 'costo unitario', 'costo per bottiglia', 'prezzo fornitore', 'costo d\'acquisto'],
    'selling_price': ['prezzo', 'price', 'prezzo vendita', 'prezzo di vendita', 'prezzo al pubblico', 'prezzo pubblico', 'prezzo in carta', 'listino', 'prezzo listino'],
    'alcohol_content': ['alcol', 'alcohol', 'gradazione', 'abv', 'alc.', '% vol', '%vol', 'grado alcolico', 'alc %', 'alcohol %', 'grad', 'vol', 'vol.'],
    'description': ['descrizione', 'description', 'note', 'note vino', 'note prodotto', 'dettagli', 'caratteristiche'],
    'notes': ['note', 'notes', 'osservazioni', 'osservazioni vino', 'note aggiuntive', 'commenti', 'annotazioni']
}


def detect_csv_separator(file_content: bytes, sample_lines: int = 10) -> Tuple[str, Dict[str, Any]]:
    """
    Auto-rileva separatore CSV analizzando i primi sample_lines.
    Returns: (separator, detection_info)
    """
    try:
        # Prova encoding detection
        encoding_result = chardet.detect(file_content[:10000])  # Prime 10KB
        detected_encoding = encoding_result.get('encoding', 'utf-8')
        confidence = encoding_result.get('confidence', 0.0)
        
        # Decodifica con encoding rilevato
        try:
            text = file_content.decode(detected_encoding)
        except (UnicodeDecodeError, LookupError):
            # Fallback: prova UTF-8, poi Latin-1
            for enc in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text = file_content.decode(enc)
                    detected_encoding = enc
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                detected_encoding = 'utf-8'
                text = file_content.decode('utf-8', errors='ignore')
        
        lines = text.split('\n')[:sample_lines]
        non_empty_lines = [l for l in lines if l.strip()]
        
        if not non_empty_lines:
            return ',', {'encoding': detected_encoding, 'confidence': confidence, 'method': 'default'}
        
        # Analizza separatori più comuni
        separators = [',', ';', '\t', '|']
        separator_scores = {}
        
        for sep in separators:
            score = 0
            consistent = True
            
            for line in non_empty_lines:
                parts = line.split(sep)
                if len(parts) >= 2:  # Almeno 2 colonne
                    score += len(parts)
                else:
                    consistent = False
            
            # Bonus se consistente (stesso numero colonne per tutte le righe)
            if consistent:
                column_counts = [len(line.split(sep)) for line in non_empty_lines]
                if len(set(column_counts)) == 1:  # Tutte le righe hanno stesso numero colonne
                    score *= 2
            
            separator_scores[sep] = score
        
        # Trova separatore con score più alto
        best_sep = max(separator_scores.items(), key=lambda x: x[1])[0] if separator_scores else ','
        
        detection_info = {
            'encoding': detected_encoding,
            'confidence': confidence,
            'separator': best_sep,
            'scores': separator_scores,
            'method': 'auto-detected'
        }
        
        logger.info(f"CSV detection: separator='{best_sep}', encoding='{detected_encoding}' (confidence={confidence:.2f})")
        return best_sep, detection_info
        
    except Exception as e:
        logger.warning(f"Error detecting CSV separator/encoding: {e}, using defaults")
        return ',', {'encoding': 'utf-8', 'confidence': 0.0, 'method': 'fallback'}


def deduplicate_wines(wines_data: List[Dict[str, Any]], merge_quantities: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Deduplica vini identici (stesso nome+produttore+vintage).
    Se merge_quantities=True, somma le quantità.
    Returns: (deduplicated_wines, dedup_stats)
    """
    seen = {}  # key -> (wine_data, index_in_original)
    duplicates = []
    
    for idx, wine in enumerate(wines_data):
        # Crea chiave univoca: normalize(name+producer+vintage)
        name = str(wine.get('name', '')).lower().strip()
        producer = str(wine.get('producer', '')).lower().strip() if wine.get('producer') else ''
        vintage = wine.get('vintage')
        
        # Normalizza (rimuovi accenti e caratteri speciali per matching robusto)
        def normalize_key(s: str) -> str:
            if not s:
                return ''
            # Rimuovi accenti comuni
            s = s.replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i')
            s = s.replace('ò', 'o').replace('ù', 'u')
            s = re.sub(r'[^\w\s]', '', s.lower())
            return s.strip()
        
        key_parts = [normalize_key(name)]
        if producer:
            key_parts.append(normalize_key(producer))
        if vintage:
            key_parts.append(str(vintage))
        
        key = '|'.join(key_parts)
        
        if key in seen:
            # Duplicato trovato
            existing_wine, existing_idx = seen[key]
            duplicates.append({
                'original_index': existing_idx,
                'duplicate_index': idx,
                'wine_name': name,
                'action': 'merged' if merge_quantities else 'removed'
            })
            
            if merge_quantities:
                # Somma quantità
                existing_qty = existing_wine.get('quantity', 1)
                new_qty = wine.get('quantity', 1)
                existing_wine['quantity'] = existing_qty + new_qty
                
                # Mantieni dati più completi (preferisci valori non null)
                for field in ['producer', 'vintage', 'selling_price', 'cost_price', 'alcohol_content', 'description']:
                    if not existing_wine.get(field) and wine.get(field):
                        existing_wine[field] = wine[field]
        else:
            seen[key] = (wine, idx)
    
    deduplicated = [wine for wine, _ in seen.values()]
    
    stats = {
        'original_count': len(wines_data),
        'deduplicated_count': len(deduplicated),
        'duplicates_found': len(duplicates),
        'duplicates_detail': duplicates
    }
    
    logger.info(f"Deduplication: {stats['original_count']} -> {stats['deduplicated_count']} wines ({stats['duplicates_found']} duplicates)")
    return deduplicated, stats

def normalize_column_name(col_name: str) -> str:
    """
    Normalizza nome colonna per matching: lowercase, strip, rimuove spazi multipli
    """
    if not col_name:
        return ""
    normalized = str(col_name).lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)  # Rimuove spazi multipli
    return normalized

def find_column_mapping(col_name: str, column_mappings: Dict[str, List[str]]) -> Optional[str]:
    """
    Trova il mapping per una colonna data.
    Cerca prima corrispondenza esatta, poi parziale (contains).
    Da priorità a match più specifici, più lunghi e più rilevanti.
    
    Returns:
        Nome colonna standardizzato o None se non trovato
    """
    normalized_col = normalize_column_name(col_name)
    
    # Cerca corrispondenza esatta prima (priorità massima)
    for standard_name, variants in column_mappings.items():
        for variant in variants:
            normalized_variant = normalize_column_name(variant)
            if normalized_col == normalized_variant:
                return standard_name
    
    # Cerca corrispondenza parziale (priorità a match più specifici)
    # Ordine priorità:
    # 1. Match che contiene variante esatta completa (es. "regione/denominazione" contiene "regione")
    # 2. Match più lunghi (variante più lunga = più specifica)
    # 3. Match che inizia con la variante (più rilevante)
    
    best_match = None
    best_match_length = 0
    best_match_score = 0  # Score: 0=none, 1=generic, 2=specific, 3=specific+starts_with
    
    for standard_name, variants in column_mappings.items():
        for variant in variants:
            normalized_variant = normalize_column_name(variant)
            score = 0
            variant_len = len(normalized_variant)
            
            # Match specifico: la variante è contenuta nel nome colonna
            if normalized_variant in normalized_col:
                score = 2  # Match specifico base
                
                # Bonus: se la variante è all'inizio del nome colonna (più rilevante)
                if normalized_col.startswith(normalized_variant):
                    score = 3  # Match specifico + inizio
                
                # Se questo match è migliore del precedente
                if score > best_match_score or (score == best_match_score and variant_len > best_match_length):
                    best_match = standard_name
                    best_match_length = variant_len
                    best_match_score = score
            # Match generico: il nome colonna è contenuto nella variante (priorità minore)
            elif normalized_col in normalized_variant:
                col_len = len(normalized_col)
                score = 1  # Match generico
                
                # Accetta solo se non c'è già un match specifico migliore
                if best_match_score < 2 or (best_match_score == 1 and col_len > best_match_length):
                    best_match = standard_name
                    best_match_length = col_len
                    best_match_score = score
    
    return best_match

def create_smart_column_mapping(original_columns: List[str]) -> Dict[str, str]:
    """
    Crea mapping intelligente tra colonne originali e nomi standardizzati.
    Usa il dizionario COLUMN_MAPPINGS per trovare corrispondenze.
    Evita conflitti: se una colonna standard è già mappata, non la rimappa.
    
    Returns:
        Dict con mapping {'nome colonna originale': 'nome standardizzato'}
    """
    rename_mapping = {}
    mapped_standard_names = set()  # Traccia colonne standard già mappate
    
    # Prima passata: cerca match esatti e specifici
    for orig_col in original_columns:
        standard_name = find_column_mapping(orig_col, COLUMN_MAPPINGS)
        if standard_name and standard_name not in mapped_standard_names:
            rename_mapping[orig_col] = standard_name
            mapped_standard_names.add(standard_name)
            logger.debug(f"Mapped '{orig_col}' -> '{standard_name}'")
    
    logger.info(f"Smart mapping created: {len(rename_mapping)}/{len(original_columns)} columns mapped")
    return rename_mapping

async def process_csv_file(file_content: bytes, separator: Optional[str] = None, encoding: Optional[str] = None, deduplicate: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Processa file CSV e estrae dati sui vini usando mapping intelligente + AI opzionale.
    Auto-rileva separatore/encoding se non specificati.
    
    Returns: (wines_data, processing_info)
    processing_info contiene: detection_info, dedup_stats, etc.
    """
    processing_info = {}
    
    try:
        # Auto-rileva separatore/encoding se non specificati
        if separator is None or encoding is None:
            detected_sep, detection_info = detect_csv_separator(file_content)
            processing_info['detection'] = detection_info
            separator = separator or detected_sep
            encoding = encoding or detection_info.get('encoding', 'utf-8')
        else:
            processing_info['detection'] = {'separator': separator, 'encoding': encoding, 'method': 'manual'}
        
        # Leggi CSV con separatore/encoding rilevati
        df = pd.read_csv(io.BytesIO(file_content), sep=separator, encoding=encoding, engine='python', on_bad_lines='skip')
        logger.info(f"CSV loaded with {len(df)} rows and {len(df.columns)} columns (sep='{separator}', enc='{encoding}')")
        
        # Salva colonne originali
        original_columns = list(df.columns)
        logger.info(f"Original columns: {original_columns}")
        
        # PRIMA: Prova mapping intelligente automatico (senza AI)
        smart_mapping = create_smart_column_mapping(original_columns)
        
        # SECONDA: Usa AI solo se mapping intelligente non copre tutte le colonne importanti
        ai_analysis = None
        ai_mapping = {}
        
        # Verifica se mapping intelligente ha trovato le colonne chiave
        key_columns = ['name', 'producer', 'vintage']
        mapped_key_columns = [col for col in key_columns if col in smart_mapping.values()]
        
        # IMPORTANTE: quantity è obbligatoria nell'inventario, verifica se è stata mappata
        quantity_mapped = 'quantity' in smart_mapping.values()
        
        if len(mapped_key_columns) < 2:  # Se mancano troppe colonne chiave, usa AI
            logger.info("Smart mapping insufficiente, usando AI per completare")
            csv_text = df.to_string()
            ai_analysis = await ai_processor.analyze_csv_structure(csv_text)
            ai_mapping = ai_analysis.get('column_mapping', {})
        elif not quantity_mapped:  # Se quantity non è stata mappata, usa AI per trovarla
            logger.warning("Colonna 'quantity' non riconosciuta dal mapping intelligente, usando AI per identificarla")
            csv_text = df.to_string()
            ai_analysis = await ai_processor.analyze_csv_structure(csv_text)
            ai_mapping = ai_analysis.get('column_mapping', {})
            # Verifica che l'AI abbia trovato quantity
            if 'quantity' in ai_mapping:
                logger.info(f"AI ha identificato colonna quantità: '{ai_mapping['quantity']}'")
            else:
                logger.warning("AI non ha identificato la colonna quantità nel CSV")
        else:
            logger.info(f"Smart mapping sufficiente ({len(mapped_key_columns)}/{len(key_columns)} key columns), quantity mappata, skipping AI")
        
        # Combina mapping intelligente e AI (AI ha priorità se c'è conflitto)
        rename_mapping = smart_mapping.copy()
        
        if ai_mapping:
            # Inverti mapping AI: da {'name': 'Wine Name'} a {'Wine Name': 'name'}
            for standard_name, original_col_name in ai_mapping.items():
                # Cerca colonna originale (case-sensitive prima)
                if original_col_name in original_columns:
                    rename_mapping[original_col_name] = standard_name
                else:
                    # Fallback case-insensitive
                    for orig_col in original_columns:
                        if normalize_column_name(orig_col) == normalize_column_name(original_col_name):
                            rename_mapping[orig_col] = standard_name
                            break
        
        logger.info(f"Final rename mapping: {rename_mapping}")
        
        # Rinomina colonne usando il mapping
        if rename_mapping:
            df = df.rename(columns=rename_mapping)
        
        # Normalizza le colonne rimanenti (lowercase, strip)
        df.columns = [normalize_column_name(col) for col in df.columns]
        
        logger.info(f"Final columns after mapping: {list(df.columns)}")
        
        # Controlla colonne duplicate dopo mapping
        if len(df.columns) != len(set(df.columns)):
            duplicates = [col for col in df.columns if list(df.columns).count(col) > 1]
            logger.warning(f"ATTENZIONE: Colonne duplicate dopo mapping: {set(duplicates)}")
            # Rimuovi duplicati mantenendo la prima occorrenza
            df = df.loc[:, ~df.columns.duplicated()]
            logger.info(f"Colonne dopo rimozione duplicati: {list(df.columns)}")
        
        wines_data = []
        
        for index, row in df.iterrows():
            try:
                wine_data = extract_wine_data_from_row(row)
                if wine_data and wine_data.get('name'):
                    wines_data.append(wine_data)
                else:
                    logger.debug(f"Row {index} skipped: wine_data={wine_data}, has_name={wine_data.get('name') if wine_data else False}")
            except Exception as e:
                logger.warning(f"Error processing row {index}: {e}", exc_info=True)
                continue
        
        # Deduplica se richiesto
        if deduplicate and wines_data:
            wines_data, dedup_stats = deduplicate_wines(wines_data, merge_quantities=True)
            processing_info['deduplication'] = dedup_stats
        
        # Usa AI per validare e filtrare vini (batch, costo ridotto)
        validated_wines = await ai_processor.validate_wine_data(wines_data)
        
        # Filtra vini (ora accetta tutti i vini)
        filtered_wines = filter_italian_wines(validated_wines)
        
        confidence = ai_analysis.get('confidence', 0.9) if ai_analysis else 0.9  # 0.9 se usato solo smart mapping
        processing_info['confidence'] = confidence
        processing_info['total_extracted'] = len(filtered_wines)
        
        logger.info(f"Processed {len(filtered_wines)} wines from CSV (confidence: {confidence})")
        return filtered_wines, processing_info
        
    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        raise

async def process_excel_file(file_content: bytes, deduplicate: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Processa file Excel e estrae dati sui vini usando mapping intelligente + AI opzionale.
    
    Returns: (wines_data, processing_info)
    """
    processing_info = {}
    
    try:
        # Leggi Excel da bytes
        df = pd.read_excel(io.BytesIO(file_content))
        logger.info(f"Excel loaded with {len(df)} rows and {len(df.columns)} columns")
        
        # Salva colonne originali
        original_columns = list(df.columns)
        logger.info(f"Original columns: {original_columns}")
        
        # PRIMA: Prova mapping intelligente automatico (senza AI)
        smart_mapping = create_smart_column_mapping(original_columns)
        
        # SECONDA: Usa AI solo se mapping intelligente non copre tutte le colonne importanti
        ai_analysis = None
        ai_mapping = {}
        
        # Verifica se mapping intelligente ha trovato le colonne chiave
        key_columns = ['name', 'producer', 'vintage']
        mapped_key_columns = [col for col in key_columns if col in smart_mapping.values()]
        
        # IMPORTANTE: quantity è obbligatoria nell'inventario, verifica se è stata mappata
        quantity_mapped = 'quantity' in smart_mapping.values()
        
        if len(mapped_key_columns) < 2:  # Se mancano troppe colonne chiave, usa AI
            logger.info("Smart mapping insufficiente, usando AI per completare")
            excel_text = df.to_string()
            ai_analysis = await ai_processor.analyze_csv_structure(excel_text)
            ai_mapping = ai_analysis.get('column_mapping', {})
        elif not quantity_mapped:  # Se quantity non è stata mappata, usa AI per trovarla
            logger.warning("Colonna 'quantity' non riconosciuta dal mapping intelligente, usando AI per identificarla")
            excel_text = df.to_string()
            ai_analysis = await ai_processor.analyze_csv_structure(excel_text)
            ai_mapping = ai_analysis.get('column_mapping', {})
            # Verifica che l'AI abbia trovato quantity
            if 'quantity' in ai_mapping:
                logger.info(f"AI ha identificato colonna quantità: '{ai_mapping['quantity']}'")
            else:
                logger.warning("AI non ha identificato la colonna quantità nell'Excel")
        else:
            logger.info(f"Smart mapping sufficiente ({len(mapped_key_columns)}/{len(key_columns)} key columns), quantity mappata, skipping AI")
        
        # Combina mapping intelligente e AI (AI ha priorità se c'è conflitto)
        rename_mapping = smart_mapping.copy()
        
        if ai_mapping:
            # Inverti mapping AI: da {'name': 'Wine Name'} a {'Wine Name': 'name'}
            for standard_name, original_col_name in ai_mapping.items():
                # Cerca colonna originale (case-sensitive prima)
                if original_col_name in original_columns:
                    rename_mapping[original_col_name] = standard_name
                else:
                    # Fallback case-insensitive
                    for orig_col in original_columns:
                        if normalize_column_name(orig_col) == normalize_column_name(original_col_name):
                            rename_mapping[orig_col] = standard_name
                            break
        
        logger.info(f"Final rename mapping: {rename_mapping}")
        
        # Rinomina colonne usando il mapping
        if rename_mapping:
            df = df.rename(columns=rename_mapping)
        
        # Normalizza le colonne rimanenti (lowercase, strip)
        df.columns = [normalize_column_name(col) for col in df.columns]
        
        logger.info(f"Final columns after mapping: {list(df.columns)}")
        
        # Controlla colonne duplicate dopo mapping
        if len(df.columns) != len(set(df.columns)):
            duplicates = [col for col in df.columns if list(df.columns).count(col) > 1]
            logger.warning(f"ATTENZIONE: Colonne duplicate dopo mapping: {set(duplicates)}")
            # Rimuovi duplicati mantenendo la prima occorrenza
            df = df.loc[:, ~df.columns.duplicated()]
            logger.info(f"Colonne dopo rimozione duplicati: {list(df.columns)}")
        
        wines_data = []
        
        for index, row in df.iterrows():
            try:
                wine_data = extract_wine_data_from_row(row)
                if wine_data and wine_data.get('name'):
                    wines_data.append(wine_data)
                else:
                    logger.debug(f"Row {index} skipped: wine_data={wine_data}, has_name={wine_data.get('name') if wine_data else False}")
            except Exception as e:
                logger.warning(f"Error processing row {index}: {e}", exc_info=True)
                continue
        
        # Deduplica se richiesto
        if deduplicate and wines_data:
            wines_data, dedup_stats = deduplicate_wines(wines_data, merge_quantities=True)
            processing_info['deduplication'] = dedup_stats
        
        # Usa AI per validare e filtrare vini (batch, costo ridotto)
        validated_wines = await ai_processor.validate_wine_data(wines_data)
        
        # Filtra vini (ora accetta tutti i vini)
        filtered_wines = filter_italian_wines(validated_wines)
        
        confidence = ai_analysis.get('confidence', 0.9) if ai_analysis else 0.9  # 0.9 se usato solo smart mapping
        processing_info['confidence'] = confidence
        processing_info['total_extracted'] = len(filtered_wines)
        
        logger.info(f"Processed {len(filtered_wines)} wines from Excel (confidence: {confidence})")
        return filtered_wines, processing_info
        
    except Exception as e:
        logger.error(f"Error processing Excel file: {e}")
        raise

def extract_wine_data_from_row(row: pd.Series) -> Dict[str, Any]:
    """
    Estrae dati vino da una riga del DataFrame.
    Estrae TUTTI i campi dello schema database per garantire scalabilità.
    """
    wine_data = {}
    
    # Nome vino (obbligatorio)
    if 'name' in row and pd.notna(row['name']):
        wine_data['name'] = str(row['name']).strip()
    
    # Annata (vintage)
    if 'vintage' in row and pd.notna(row['vintage']):
        vintage = str(row['vintage']).strip()
        vintage_match = re.search(r'\b(19|20)\d{2}\b', vintage)
        if vintage_match:
            wine_data['vintage'] = int(vintage_match.group())
    
    # Produttore
    if 'producer' in row and pd.notna(row['producer']):
        wine_data['producer'] = str(row['producer']).strip()
    
    # Uvaggio/Vitigno (grape_variety)
    if 'grape_variety' in row and pd.notna(row['grape_variety']):
        wine_data['grape_variety'] = str(row['grape_variety']).strip()
    
    # Regione
    if 'region' in row and pd.notna(row['region']):
        wine_data['region'] = str(row['region']).strip()
    
    # Paese (country)
    if 'country' in row and pd.notna(row['country']):
        wine_data['country'] = str(row['country']).strip()
    
    # Tipo vino (wine_type)
    if 'wine_type' in row and pd.notna(row['wine_type']):
        wine_type = str(row['wine_type']).lower().strip()
        wine_data['wine_type'] = classify_wine_type(wine_type)
    else:
        # Prova a classificare dal nome
        if 'name' in wine_data:
            wine_data['wine_type'] = classify_wine_type(wine_data['name'])
        else:
            wine_data['wine_type'] = 'sconosciuto'
    
    # Classificazione (DOC, DOCG, IGT, etc.)
    if 'classification' in row and pd.notna(row['classification']):
        wine_data['classification'] = str(row['classification']).strip().upper()
    
    # Quantità
    if 'quantity' in row and pd.notna(row['quantity']):
        try:
            qty_str = str(row['quantity']).strip()
            qty_match = re.search(r'\d+', qty_str)
            if qty_match:
                wine_data['quantity'] = int(qty_match.group())
            else:
                wine_data['quantity'] = 1
        except (ValueError, TypeError):
            wine_data['quantity'] = 1
    else:
        wine_data['quantity'] = 1
    
    # Scorta minima (min_quantity)
    if 'min_quantity' in row and pd.notna(row['min_quantity']):
        try:
            min_qty_str = str(row['min_quantity']).strip()
            min_qty_match = re.search(r'\d+', min_qty_str)
            if min_qty_match:
                wine_data['min_quantity'] = int(min_qty_match.group())
            else:
                wine_data['min_quantity'] = 0
        except (ValueError, TypeError):
            wine_data['min_quantity'] = 0
    else:
        wine_data['min_quantity'] = 0
    
    # Prezzo di acquisto (cost_price)
    if 'cost_price' in row and pd.notna(row['cost_price']):
        try:
            cost_str = str(row['cost_price']).replace(',', '.').replace('€', '').strip()
            cost_clean = re.sub(r'[^\d.,]', '', cost_str)
            if cost_clean:
                wine_data['cost_price'] = float(cost_clean.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Prezzo di vendita (selling_price)
    # Controlla prima selling_price, poi price (compatibilità)
    if 'selling_price' in row and pd.notna(row['selling_price']):
        try:
            price_str = str(row['selling_price']).replace(',', '.').replace('€', '').strip()
            price_clean = re.sub(r'[^\d.,]', '', price_str)
            if price_clean:
                wine_data['selling_price'] = float(price_clean.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    elif 'price' in row and pd.notna(row['price']):
        # Fallback: se c'è solo 'price', usa come selling_price
        try:
            price_str = str(row['price']).replace(',', '.').replace('€', '').strip()
            price_clean = re.sub(r'[^\d.,]', '', price_str)
            if price_clean:
                wine_data['selling_price'] = float(price_clean.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Gradazione alcolica (alcohol_content)
    if 'alcohol_content' in row and pd.notna(row['alcohol_content']):
        try:
            alc_str = str(row['alcohol_content']).replace('%', '').replace('vol', '').strip()
            alc_clean = re.sub(r'[^\d.,]', '', alc_str)
            if alc_clean:
                wine_data['alcohol_content'] = float(alc_clean.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Descrizione
    if 'description' in row and pd.notna(row['description']):
        wine_data['description'] = str(row['description']).strip()
    
    # Note
    if 'notes' in row and pd.notna(row['notes']):
        wine_data['notes'] = str(row['notes']).strip()
    
    return wine_data

def classify_wine_type(text: str) -> str:
    """
    Classifica il tipo di vino dal testo
    """
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['rosso', 'red', 'nero', 'black', 'sangiovese', 'barbera', 'nebbiolo', 'cabernet', 'merlot', 'pinot noir', 'syrah', 'shiraz']):
        return 'rosso'
    elif any(word in text_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon', 'riesling', 'gewürztraminer', 'moscato']):
        return 'bianco'
    elif any(word in text_lower for word in ['rosato', 'rosé', 'rose', 'pink']):
        return 'rosato'
    elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco', 'moscato', 'frizzante', 'sparkling', 'cava', 'crémant']):
        return 'spumante'
    else:
        return 'sconosciuto'

def clean_wine_name(name: str) -> str:
    """
    Pulisce il nome del vino
    """
    if not name:
        return ""
    
    # Rimuovi caratteri speciali eccessivi
    cleaned = re.sub(r'[^\w\s\-\.]', ' ', name)
    # Rimuovi spazi multipli
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def filter_italian_wines(wines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filtra vini per mantenere solo quelli italiani (funzione rimossa - ora accetta tutti i vini)
    """
    # Ora accetta tutti i vini, non solo quelli italiani
    return wines
