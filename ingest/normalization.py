"""
Normalization per Stage 1.

Unifica funzioni di normalizzazione header, valori e classificazione.
"""
import re
import logging
from typing import Dict, List, Optional, Any
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

# Dizionario completo di mapping colonne - conforme a "Update processor.md"
COLUMN_MAPPINGS = {
    'name': ['vino', 'etichetta', 'nome', 'descrizione'],
    'winery': ['cantina', 'produttore', 'azienda'],
    'vintage': ['annata', 'year', 'yr', 'anno'],
    'qty': ['quantità', 'qta', 'pezzi', 'bottiglie', 'pz', 'q.ty'],
    'price': ['prezzo', '€/pz', 'costo', 'valore', 'price'],
    'type': ['tipologia', 'colore', 'categoria'],
}

# Mapping completo (esteso per compatibilità con codice esistente)
# Aggiunti più sinonimi per aumentare matching fuzzy
COLUMN_MAPPINGS_EXTENDED = {
    'name': ['nome', 'vino', 'wine', 'wine name', 'nome vino', 'denominazione', 'etichetta', 'prodotto', 'articolo', 'descrizione', 'titolo', 'label', 'nome prodotto', 'denominazione vino', 'vino nome', 'wine name', 'nome articolo', 'descrizione prodotto', 'prodotto nome', 'articolo nome'],
    'vintage': ['annata', 'year', 'vintage', 'anno', 'anno produzione', 'vintage year', 'anno vendemmia', 'vendemmia', 'yr', 'vintage year', 'anno vinificazione', 'year vintage', 'vintage yr', 'anno prod', 'prod year', 'anno vino'],
    'winery': ['produttore', 'producer', 'winery', 'azienda', 'casa vinicola', 'marca', 'brand', 'cantina', 'fattoria', 'azienda vinicola', 'casa produttrice', 'casa', 'produttore vino', 'azienda produttrice', 'casa vinicola', 'marca vino', 'brand vino', 'cantina produttrice', 'fattoria vinicola'],
    'qty': ['quantità', 'quantity', 'qty', 'q.tà', 'pezzi', 'bottiglie', 'quantità in magazzino', 'scorta', 'qta_magazzino', 'qta magazzino', 'qta', 'disp', 'disponibilità', 'stock', 'q iniziale', 'q. iniziale', 'quantità iniziale', 'q iniz', 'q. iniz', 'q iniziale magazzino', 'quantità iniz', 'q iniziale stock', 'q iniz', 'q cantina', 'quantità disponibile', 'q disponibile', 'q disponibile magazzino', 'scorta disponibile', 'pezzi disponibili', 'bottiglie disponibili', 'quantità stock', 'q stock', 'disponibilità magazzino', 'q.ty', 'qty.', 'qty disponibile', 'quantità iniz', 'q iniz magazzino'],
    'price': ['prezzo', 'price', 'prezzo vendita', 'prezzo di vendita', 'prezzo al pubblico', 'prezzo pubblico', 'prezzo in carta', 'listino', 'prezzo listino', 'prezzo_unit_eur', 'prezzo unit eur', 'prezzo unitario', 'prezzo unit', 'eur', 'euro', 'valore', 'prezzo unitario eur', 'prezzo unitario euro', 'prezzo vendita eur', 'prezzo vendita euro', 'listino prezzo', 'prezzo listino eur', 'valore unitario', 'prezzo pz', 'prezzo pezzo', 'prezzo bottiglia', 'eur pz', 'euro pz', 'eur pezzo', 'euro pezzo', 'selling price', 'prezzo vendita'],
    'type': ['tipo', 'type', 'wine_type', 'categoria', 'tipo vino', 'categoria vino', 'colore', 'tipologia', 'tipo prodotto', 'categoria prodotto', 'colore vino', 'tipologia vino', 'tipo vino prodotto'],
    # Nuovi campi aggiunti
    'grape_variety': ['uvaggio', 'grape variety', 'grape', 'varietà', 'varietà uve', 'uve', 'uvaggi', 'vitigno', 'vitigni', 'grape variety', 'grape_variety', 'varietà uva', 'tipologia uve', 'uvaggio vino'],
    'region': ['regione', 'region', 'area', 'zona', 'territorio', 'terroir', 'regione produzione', 'zona produzione', 'area produzione'],
    'country': ['nazione', 'country', 'paese', 'nazione produzione', 'paese origine', 'origine', 'provenienza', 'nazione origine'],
    'supplier': ['fornitore', 'supplier', 'fornitore vino', 'importatore', 'distributore', 'fornitura', 'supplier name', 'fornitore nome'],
    'classification': ['denominazione', 'classification', 'classificazione', 'docg', 'doc', 'igt', 'vdt', 'igp', 'aoc', 'aop', 'vqa', 'denominazione origine', 'denominazione di origine', 'do', 'dop', 'igp', 'igt', 'vdt', 'vino da tavola'],
    'cost_price': ['costo', 'cost', 'costo unitario', 'costo fornitore', 'prezzo fornitore', 'costo acquisto', 'prezzo acquisto', 'costo pz', 'costo pezzo', 'costo bottiglia', 'cost price', 'prezzo costo', 'costo unit', 'costo unitario eur', 'costo unitario euro'],
    'alcohol_content': ['alcol', 'alcohol', 'gradazione', 'gradazione alcolica', 'alcohol content', 'abv', 'vol', 'volume', 'vol%', 'alcol %', 'gradazione %', 'alcohol %', 'alcool', 'alcool %'],
    'description': ['descrizione', 'description', 'descrizione prodotto', 'descrizione vino', 'note descrittive', 'dettagli', 'caratteristiche'],
    'notes': ['note', 'notes', 'osservazioni', 'annotazioni', 'note aggiuntive', 'note prodotto', 'commenti'],
}


def normalize_column_name(col_name: str) -> str:
    """
    Normalizza nome colonna per matching: lowercase, strip, rimuove spazi multipli e simboli.
    
    Args:
        col_name: Nome colonna originale
    
    Returns:
        Nome colonna normalizzato
    """
    if not col_name:
        return ""
    normalized = str(col_name).lower().strip()
    # Rimuovi simboli (mantieni lettere, numeri, spazi, underscore, trattino)
    normalized = re.sub(r'[^\w\s\-_]', '', normalized)
    # Rimuovi spazi multipli
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def map_headers(
    original_columns: List[str],
    confidence_threshold: float = 0.75,
    use_extended: bool = True
) -> Dict[str, str]:
    """
    Mappa header colonne usando rapidfuzz per fuzzy matching.
    
    Conforme a "Update processor.md" - Sezione "Sinonimi riconosciuti".
    
    Args:
        original_columns: Lista nomi colonne originali
        confidence_threshold: Soglia confidence (default 0.75)
        use_extended: Se True usa COLUMN_MAPPINGS_EXTENDED, altrimenti COLUMN_MAPPINGS
    
    Returns:
        Dict mapping {'nome colonna originale': 'nome standardizzato'}
    """
    column_mappings = COLUMN_MAPPINGS_EXTENDED if use_extended else COLUMN_MAPPINGS
    
    rename_mapping = {}
    mapped_standard_names = set()  # Traccia colonne standard già mappate
    
    # Prepara lista target per rapidfuzz (tutti i sinonimi)
    target_list = []
    target_to_standard = {}
    
    for standard_name, variants in column_mappings.items():
        for variant in variants:
            normalized_variant = normalize_column_name(variant)
            target_list.append(normalized_variant)
            target_to_standard[normalized_variant] = standard_name
    
    # Mappa ogni colonna originale
    for orig_col in original_columns:
        normalized_col = normalize_column_name(orig_col)
        
        # Usa rapidfuzz per trovare match migliore
        if target_list:
            result = process.extractOne(
                normalized_col,
                target_list,
                scorer=fuzz.ratio,
                score_cutoff=int(confidence_threshold * 100)
            )
            
            if result:
                matched_variant, score, _ = result
                standard_name = target_to_standard[matched_variant]
                
                # Evita conflitti: se standard già mappato, salta
                if standard_name not in mapped_standard_names:
                    rename_mapping[orig_col] = standard_name
                    mapped_standard_names.add(standard_name)
                    logger.debug(
                        f"[NORMALIZATION] Mapped '{orig_col}' -> '{standard_name}' "
                        f"(confidence={score/100:.2f})"
                    )
    
    logger.info(
        f"[NORMALIZATION] Header mapping: {len(rename_mapping)}/{len(original_columns)} columns mapped "
        f"(threshold={confidence_threshold})"
    )
    return rename_mapping


def is_na(value: Any) -> bool:
    """
    Verifica se valore è null/NaN (compatibile con pandas.isna ma senza dipendenza).
    
    Args:
        value: Valore da verificare
    
    Returns:
        True se valore è None, NaN, o stringa vuota
    """
    if value is None:
        return True
    if isinstance(value, float):
        import math
        return math.isnan(value)
    if isinstance(value, str):
        return value.strip() == '' or value.strip().lower() in ['nan', 'none', 'null', 'n/a', 'na']
    return False


def normalize_vintage(value: Any) -> Optional[int]:
    """
    Normalizza valore vintage (annata).
    
    Regole:
    - Estrae anno 4 cifre (1900-2099) con regex
    - Fuori range = null
    
    Args:
        value: Valore originale (string, int, etc.)
    
    Returns:
        Anno (1900-2099) o None
    """
    # Controlla NaN prima di qualsiasi altra operazione
    if is_na(value):
        return None
    
    if value is None:
        return None
    
    # Se è float NaN, ritorna None
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return None
    
    # Converti a string
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ['nan', 'none', 'null', 'n/a', 'na']:
        return None
    
    # Cerca anno 4 cifre (1900-2099)
    match = re.search(r'\b(19\d{2}|20\d{2})\b', value_str)
    if match:
        year = int(match.group())
        if 1900 <= year <= 2099:
            return year
    
    return None


def normalize_qty(value: Any) -> int:
    """
    Normalizza quantità (qty).
    
    Regole:
    - Estrae intero (es. "12 bottiglie" → 12)
    - Default 0 se vuoto o non trovato
    
    Args:
        value: Valore originale (string, int, etc.)
    
    Returns:
        Quantità (>= 0, default 0)
    """
    # Controlla NaN prima di qualsiasi altra operazione
    if is_na(value):
        return 0
    
    if value is None:
        return 0
    
    # Se è già int/float, verifica NaN prima di convertire
    if isinstance(value, (int, float)):
        import math
        if math.isnan(value):
            return 0
        return max(0, int(value))
    
    # Converti a string
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ['nan', 'none', 'null', 'n/a', 'na']:
        return 0
    
    # Estrai primo numero intero
    match = re.search(r'\d+', value_str)
    if match:
        return int(match.group())
    
    return 0


def normalize_price(value: Any) -> Optional[float]:
    """
    Normalizza prezzo.
    
    Regole:
    - Estrae float (gestisci virgola europea: "8,50" → 8.5)
    - Default None se vuoto
    
    Args:
        value: Valore originale (string, float, etc.)
    
    Returns:
        Prezzo (>= 0.0) o None
    """
    # Controlla NaN prima di qualsiasi altra operazione
    if is_na(value):
        return None
    
    if value is None:
        return None
    
    # Se è già float/int, verifica NaN prima di convertire
    if isinstance(value, (int, float)):
        import math
        if math.isnan(value):
            return None
        return max(0.0, float(value))
    
    # Converti a string
    value_str = str(value).strip()
    if not value_str:
        return None
    
    # Rimuovi simboli valuta
    value_str = re.sub(r'[€$£]', '', value_str)
    
    # Sostituisci virgola con punto (formato europeo)
    value_str = value_str.replace(',', '.')
    
    # Estrai numero (float)
    match = re.search(r'\d+\.?\d*', value_str)
    if match:
        try:
            price = float(match.group())
            return max(0.0, price) if price >= 0 else None
        except ValueError:
            pass
    
    return None


def classify_wine_type(text: str) -> str:
    """
    Classifica tipo vino dal testo.
    
    Versione più completa da csv_processor.py (conforme a AUDIT_DUPLICAZIONI.md).
    
    Args:
        text: Testo da analizzare (nome vino, descrizione, etc.)
    
    Returns:
        Tipo vino: 'rosso', 'bianco', 'rosato', 'spumante', 'sconosciuto'
    """
    if not text:
        return 'sconosciuto'
    
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


def normalize_wine_type(value: Any) -> Optional[str]:
    """
    Normalizza tipo vino a enum.
    
    Args:
        value: Valore originale (string, etc.)
    
    Returns:
        Tipo vino: 'Rosso', 'Bianco', 'Rosato', 'Spumante', 'Altro' o None
    """
    if value is None:
        return None
    
    value_str = str(value).strip().lower()
    if not value_str:
        return None
    
    # Classifica con funzione esistente
    classified = classify_wine_type(value_str)
    
    # Mappa a enum (capitalizza prima lettera)
    if classified == 'rosso':
        return 'Rosso'
    elif classified == 'bianco':
        return 'Bianco'
    elif classified == 'rosato':
        return 'Rosato'
    elif classified == 'spumante':
        return 'Spumante'
    elif classified == 'sconosciuto':
        return 'Altro'
    
    return None


def normalize_string_field(value: Any) -> Optional[str]:
    """
    Normalizza campo stringa opzionale.
    
    Args:
        value: Valore originale
    
    Returns:
        Stringa normalizzata o None
    """
    if is_na(value):
        return None
    if value is None:
        return None
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ['nan', 'none', 'null', 'n/a', 'na', '', 'undefined']:
        return None
    return value_str


def normalize_alcohol_content(value: Any) -> Optional[float]:
    """
    Normalizza gradazione alcolica.
    
    Estrae percentuale (es. "14.5%", "14.5", "14,5" → 14.5)
    
    Args:
        value: Valore originale
    
    Returns:
        Gradazione (0-100) o None
    """
    if is_na(value):
        return None
    if value is None:
        return None
    
    if isinstance(value, (int, float)):
        import math
        if math.isnan(value):
            return None
        alc = float(value)
        return alc if 0 <= alc <= 100 else None
    
    value_str = str(value).strip()
    if not value_str:
        return None
    
    # Rimuovi simboli % e spazi
    value_str = re.sub(r'[%\s]', '', value_str)
    # Sostituisci virgola con punto
    value_str = value_str.replace(',', '.')
    
    # Estrai numero
    match = re.search(r'\d+\.?\d*', value_str)
    if match:
        try:
            alc = float(match.group())
            return alc if 0 <= alc <= 100 else None
        except ValueError:
            pass
    
    return None


def normalize_values(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizza valori riga secondo schema WineItemModel esteso.
    
    Applica normalizzazione a tutti i campi: vintage, qty, price, type, grape_variety, region, country, etc.
    
    Args:
        row: Dict con dati riga (chiavi possono essere mappate a vari campi)
    
    Returns:
        Dict con valori normalizzati (tutti i campi WineItemModel)
    """
    normalized = {}
    
    # Name (trim e pulizia)
    if 'name' in row:
        name_raw = row['name']
        # Controlla NaN prima
        if is_na(name_raw):
            normalized['name'] = ""
        else:
            name_str = str(name_raw).strip()
            # Filtra valori placeholder comuni
            if name_str.lower() in ['nan', 'none', 'null', 'n/a', 'na', '', 'undefined']:
                normalized['name'] = ""
            else:
                normalized['name'] = name_str
    else:
        normalized['name'] = ""
    
    # Winery (trim, opzionale)
    if 'winery' in row:
        winery = row['winery']
        normalized['winery'] = normalize_string_field(winery)
    
    # Vintage (regex 19xx|20xx → int, fuori range = null)
    if 'vintage' in row:
        normalized['vintage'] = normalize_vintage(row['vintage'])
    else:
        normalized['vintage'] = None
    
    # Qty (estrai intero, default 0)
    if 'qty' in row:
        normalized['qty'] = normalize_qty(row['qty'])
    else:
        normalized['qty'] = 0
    
    # Price (estrai float, gestisci virgola europea) - prezzo vendita
    if 'price' in row:
        normalized['price'] = normalize_price(row['price'])
    else:
        normalized['price'] = None
    
    # Type (mappa fuzzy a enum)
    if 'type' in row:
        normalized['type'] = normalize_wine_type(row['type'])
    else:
        normalized['type'] = None
    
    # Nuovi campi aggiuntivi
    # Grape variety (uvaggio)
    if 'grape_variety' in row:
        normalized['grape_variety'] = normalize_string_field(row['grape_variety'])
    
    # Region (regione)
    if 'region' in row:
        normalized['region'] = normalize_string_field(row['region'])
    
    # Country (nazione)
    if 'country' in row:
        normalized['country'] = normalize_string_field(row['country'])
    
    # Supplier (fornitore)
    if 'supplier' in row:
        normalized['supplier'] = normalize_string_field(row['supplier'])
    
    # Classification (denominazione)
    if 'classification' in row:
        normalized['classification'] = normalize_string_field(row['classification'])
    
    # Cost price (costo)
    if 'cost_price' in row:
        normalized['cost_price'] = normalize_price(row['cost_price'])
    
    # Alcohol content (gradazione alcolica)
    if 'alcohol_content' in row:
        normalized['alcohol_content'] = normalize_alcohol_content(row['alcohol_content'])
    
    # Description (descrizione)
    if 'description' in row:
        normalized['description'] = normalize_string_field(row['description'])
    
    # Notes (note)
    if 'notes' in row:
        normalized['notes'] = normalize_string_field(row['notes'])
    
    return normalized


def clean_wine_name(name: str) -> str:
    """
    Pulisce nome vino (rimuove caratteri speciali eccessivi, normalizza spazi).
    
    Args:
        name: Nome vino originale
    
    Returns:
        Nome vino pulito
    """
    if not name:
        return ""
    
    # Rimuovi caratteri speciali eccessivi (mantieni lettere, numeri, spazi, trattini, punti)
    cleaned = re.sub(r'[^\w\s\-\.]', ' ', name)
    # Rimuovi spazi multipli
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def clean_text(text: str) -> str:
    """
    Pulisce testo generico (per OCR, etc.).
    
    Args:
        text: Testo originale
    
    Returns:
        Testo pulito
    """
    if not text:
        return ""
    
    # Rimuovi caratteri strani, normalizza spazi
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if line:
            # Rimuovi caratteri non stampabili
            line = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', line)
            if line:
                lines.append(line)
    
    return '\n'.join(lines)

