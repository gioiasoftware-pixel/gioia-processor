"""
Dizionario termini inventario vini - Termini che NON devono essere nomi vino.

Questo dizionario contiene categorie, tipologie, regioni, classificazioni e altri termini
che potrebbero essere erroneamente salvati come nomi vino invece di essere riconosciuti
come metadati (tipo, regione, classificazione, etc.).

Usato da:
- Stage 1 (normalization.py) - Filtro nomi vino
- Stage 3 (llm_extract.py) - Prompt LLM
- Post-processing (post_processing.py) - Validazione e correzione
"""
import re
from typing import Optional

# ============================================================================
# CATEGORIE SPUMANTI / CHAMPAGNE
# ============================================================================
SPARKLING_CATEGORIES = {
    # Italiano
    'bolle', 'bolle\'', 'spumante', 'spumanti', 'prosecco', 'prosecco\'',
    'asti', 'asti spumante', 'moscato d\'asti', 'lambrusco', 'lambruschi',
    'frizzante', 'frizzanti', 'perlante', 'perlanti',
    # Francese
    'champagne', 'champagnes', 'crémant', 'cremant', 'cava', 'cavas',
    # Termini tecnici spumanti
    'brut', 'brut nature', 'extra brut', 'extra dry', 'demi-sec', 'sec', 'doux',
    'metodo classico', 'metodo tradizionale', 'charmat', 'martinotti',
    'dosaggio zero', 'pas dosé', 'pas dose', 'zero dosage',
}

# ============================================================================
# TIPI VINO (colori / stili)
# ============================================================================
WINE_TYPES = {
    # Italiano
    'rosso', 'rossi', 'bianco', 'bianchi', 'rosato', 'rosati', 'rosè', 'rosé',
    'bianco secco', 'bianco dolce', 'rosso secco', 'rosso dolce',
    'passito', 'passiti', 'dolce', 'dolci', 'secco', 'secca', 'amabile',
    # Francese
    'rouge', 'blanc', 'rosé', 'doux', 'sec', 'moelleux',
    # Inglese
    'red', 'white', 'rosé', 'sweet', 'dry',
    # Altri
    'vino da tavola', 'vdt', 'vino da pasto',
}

# ============================================================================
# REGIONI ITALIANE
# ============================================================================
ITALIAN_REGIONS = {
    'abruzzo', 'basilicata', 'calabria', 'campania', 'emilia-romagna',
    'emilia', 'romagna', 'friuli-venezia giulia', 'friuli', 'venezia giulia',
    'lazio', 'liguria', 'lombardia', 'marche', 'molise', 'piemonte',
    'puglia', 'sardegna', 'sicilia', 'toscana', 'trentino-alto adige',
    'trentino', 'alto adige', 'sudtirol', 'umbria', 'valle d\'aosta',
    'valle d aosta', 'valle daosta', 'veneto',
    # Varianti comuni
    'toscata', 'piemonte', 'veneto', 'sicilia', 'sardegna',
}

# ============================================================================
# REGIONI INTERNAZIONALI (principali)
# ============================================================================
INTERNATIONAL_REGIONS = {
    # Francia
    'bordeaux', 'bourgogne', 'burgundy', 'champagne', 'alsace', 'loire',
    'rhône', 'rhone', 'provence', 'languedoc', 'roussillon',
    # Spagna
    'rioja', 'ribera del duero', 'priorat', 'cataluña', 'catalunya',
    # Germania
    'mosel', 'rheingau', 'pfalz', 'baden',
    # Portogallo
    'douro', 'porto', 'alentejo',
    # Altri
    'napa valley', 'sonoma', 'tuscany', 'toscana',
}

# ============================================================================
# CLASSIFICAZIONI / DENOMINAZIONI
# ============================================================================
CLASSIFICATIONS = {
    # Italiane
    'doc', 'docg', 'igt', 'igp', 'vdt', 'vino da tavola',
    'denominazione di origine controllata',
    'denominazione di origine controllata e garantita',
    'indicazione geografica tipica',
    'indicazione geografica protetta',
    # Francesi
    'aoc', 'aop', 'igp', 'vin de pays', 'vin de table',
    # Spagnole
    'do', 'doca', 'vt', 'vcig',
    # Tedesche
    'qualitätswein', 'prädikatswein', 'landwein', 'tafelwein',
    # Generiche
    'protected designation of origin', 'pdo',
    'protected geographical indication', 'pgi',
}

# ============================================================================
# TERMINI TECNICI / DESCRITTORI
# ============================================================================
TECHNICAL_TERMS = {
    # Stili / Metodi
    'riserva', 'riserve', 'superiore', 'classico', 'classica',
    'vendemmia tardiva', 'late harvest', 'ice wine', 'eiswein',
    'noble rot', 'botrytis', 'appassimento',
    # Annate / Millesimi
    'millésimé', 'millesimato', 'vintage', 'non vintage', 'nv',
    # Invecchiamento
    'barrique', 'barriques', 'barrica', 'invecchiato', 'aged',
    'riserva speciale', 'gran riserva',
    # Altri
    'organic', 'biologico', 'biodynamic', 'biodinamico',
    'natural', 'naturale', 'sulfite free',
}

# ============================================================================
# TERMINI COMUNI NON-VINO
# ============================================================================
COMMON_NON_WINE_TERMS = {
    # Numeri / Quantità
    'pezzo', 'pezzi', 'pz', 'bottiglia', 'bottiglie', 'btl', 'btls',
    'cassa', 'casse', 'scatola', 'scatole',
    # Prezzi / Valori
    'prezzo', 'costo', 'valore', 'euro', 'eur', '€',
    # Generici
    'vino', 'vini', 'wine', 'wines', 'produttore', 'cantina',
    'fornitore', 'importatore', 'distributore',
    # Placeholder
    'da definire', 'tbd', 'to be defined', 'n/a', 'na',
}

# ============================================================================
# UNIONE COMPLETA - Tutti i termini problematici
# ============================================================================
ALL_PROBLEMATIC_TERMS = (
    SPARKLING_CATEGORIES |
    WINE_TYPES |
    ITALIAN_REGIONS |
    INTERNATIONAL_REGIONS |
    CLASSIFICATIONS |
    TECHNICAL_TERMS |
    COMMON_NON_WINE_TERMS
)

# ============================================================================
# MAPPING CATEGORIE → TIPO VINO (per inferenza automatica)
# ============================================================================
CATEGORY_TO_WINE_TYPE = {
    # Spumanti
    **{term: 'Spumante' for term in SPARKLING_CATEGORIES},
    # Tipi vino
    **{term: 'Rosso' for term in ['rosso', 'rossi', 'rouge', 'red']},
    **{term: 'Bianco' for term in ['bianco', 'bianchi', 'blanc', 'white']},
    **{term: 'Rosato' for term in ['rosato', 'rosati', 'rosè', 'rosé', 'rose']},
    **{term: 'Altro' for term in ['passito', 'passiti', 'dolce', 'dolci', 'vino da tavola', 'vdt']},
}

# ============================================================================
# FUNZIONI HELPER
# ============================================================================

def is_problematic_term(term: str) -> bool:
    """
    Verifica se un termine è problematico (categoria/tipologia invece di nome vino).
    
    Args:
        term: Termine da verificare
    
    Returns:
        True se è un termine problematico, False altrimenti
    """
    if not term:
        return False
    
    term_lower = term.strip().lower()
    
    # Rimuovi caratteri speciali per confronto
    term_normalized = re.sub(r'[^\w\s]', '', term_lower).strip()
    
    # Verifica esatta
    if term_normalized in ALL_PROBLEMATIC_TERMS:
        return True
    
    # Verifica parziale (es. "Bolle Brut" contiene "bolle" e "brut")
    words = term_normalized.split()
    if len(words) <= 3:  # Massimo 3 parole
        problematic_words = [w for w in words if w in ALL_PROBLEMATIC_TERMS and len(w) > 2]
        if len(problematic_words) == len(words):  # Tutte le parole sono problematiche
            return True
    
    return False


def infer_wine_type_from_category(category: str) -> Optional[str]:
    """
    Infers tipo vino da categoria/tipologia.
    
    Args:
        category: Categoria/tipologia (es. "Bolle", "Rosè", "Brut")
    
    Returns:
        Tipo vino inferito (es. "Spumante", "Rosato") o None
    """
    if not category:
        return None
    
    category_lower = category.lower().strip()
    
    # Cerca match esatto
    if category_lower in CATEGORY_TO_WINE_TYPE:
        return CATEGORY_TO_WINE_TYPE[category_lower]
    
    # Cerca match parziale
    for term, wine_type in CATEGORY_TO_WINE_TYPE.items():
        if term in category_lower:
            return wine_type
    
    return None


def get_category_description(term: str) -> Optional[str]:
    """
    Ritorna descrizione categoria per logging/debug.
    
    Args:
        term: Termine da descrivere
    
    Returns:
        Descrizione categoria o None
    """
    if not term:
        return None
    
    term_lower = term.lower().strip()
    
    if term_lower in SPARKLING_CATEGORIES:
        return "categoria spumante"
    elif term_lower in WINE_TYPES:
        return "tipo vino"
    elif term_lower in ITALIAN_REGIONS:
        return "regione italiana"
    elif term_lower in INTERNATIONAL_REGIONS:
        return "regione internazionale"
    elif term_lower in CLASSIFICATIONS:
        return "classificazione"
    elif term_lower in TECHNICAL_TERMS:
        return "termine tecnico"
    elif term_lower in COMMON_NON_WINE_TERMS:
        return "termine comune non-vino"
    
    return None

