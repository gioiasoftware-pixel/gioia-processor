"""
Post-Processing Normalization - Normalizza inventario salvato in background.

Dopo che l'inventario è stato salvato, esegue un secondo passaggio per:
- Estrarre nome vino da pattern "Categoria (Nome Vino)" (es. "Bolle (Dom Perignon)" → name="Dom Perignon", type="Spumante")
- Estrarre regione da classification (es. "Marche / Verdicchio DOC" → region="Marche")
- Normalizzare valori (country, region, wine_type)
- Estrarre country da region se country è vuoto
- Pulire classification rimuovendo regione se già estratta
- Validazione finale con LLM economico (max 2-3 retry se trova errori)
"""
import logging
import re
import json
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_user_table_name
from ingest.normalization import extract_wine_name_from_category_pattern
from ingest.wine_terms_dict import (
    ALL_PROBLEMATIC_TERMS,
    is_problematic_term,
    infer_wine_type_from_category,
    get_category_description
)

logger = logging.getLogger(__name__)

# Client OpenAI per validazione (singleton)
_openai_client = None


def get_openai_client():
    """Ottiene client OpenAI (singleton) per validazione post-processing."""
    global _openai_client
    if _openai_client is None:
        try:
            from core.config import get_config
            import openai
            config = get_config()
            api_key = config.openai_api_key
            if not api_key:
                logger.warning("[POST_PROCESSING] OPENAI_API_KEY non configurato, validazione LLM disabilitata")
                return None
            _openai_client = openai.OpenAI(api_key=api_key)
        except Exception as e:
            logger.warning(f"[POST_PROCESSING] Errore inizializzazione OpenAI client: {e}")
            return None
    return _openai_client

# Lista regioni italiane comuni per validazione
ITALIAN_REGIONS = [
    'Toscana', 'Piemonte', 'Veneto', 'Sicilia', 'Sardegna', 'Lombardia', 
    'Marche', 'Umbria', 'Lazio', 'Puglia', 'Abruzzo', 'Friuli', 'Trentino', 
    'Alto Adige', 'Campania', 'Liguria', 'Emilia', 'Romagna', 'Calabria',
    'Basilicata', 'Molise', 'Valle d\'Aosta'
]

# Mappa regioni → country (per regioni italiane)
REGION_TO_COUNTRY = {
    region: 'Italia' for region in ITALIAN_REGIONS
}

# Pattern per estrarre regione da classification
REGION_PATTERNS = [
    # Pattern: "Regione / Denominazione" (es. "Marche / Verdicchio DOC")
    r'^([^/]+?)\s*/\s*(.+)$',
    # Pattern: "Regione - Denominazione" (es. "Toscana - Chianti DOCG")
    r'^([^-]+?)\s*-\s*(.+)$',
    # Pattern: "Regione Denominazione" (es. "Toscana Chianti")
    r'^(' + '|'.join([re.escape(r) for r in ITALIAN_REGIONS]) + r')\s+(.+)$',
]


def extract_region_from_classification(classification: Optional[str]) -> Optional[Tuple[str, str]]:
    """
    Estrae regione da classification se presente.
    
    Esempi:
    - "Marche / Verdicchio DOC" → ("Marche", "Verdicchio DOC")
    - "Toscana - Chianti DOCG" → ("Toscana", "Chianti DOCG")
    - "Piemonte Barolo DOCG" → ("Piemonte", "Barolo DOCG")
    
    Returns:
        Tuple (region, cleaned_classification) se regione trovata, altrimenti (None, classification)
    """
    if not classification or not classification.strip():
        return None, classification
    
    classification_clean = classification.strip()
    
    # Prova pattern per estrarre regione
    for pattern in REGION_PATTERNS:
        match = re.match(pattern, classification_clean, re.IGNORECASE)
        if match:
            potential_region = match.group(1).strip()
            remaining = match.group(2).strip()
            
            # Verifica se potential_region è una regione italiana valida
            potential_region_normalized = potential_region.capitalize()
            
            # Match case-insensitive con regioni italiane
            for region in ITALIAN_REGIONS:
                if region.lower() == potential_region_normalized.lower():
                    # Regione trovata!
                    logger.info(
                        f"[POST_PROCESSING] Estratta regione da classification: "
                        f"'{classification_clean}' → region='{region}', classification='{remaining}'"
                    )
                    return region, remaining
            
            # Se non è una regione valida, potrebbe essere parte della denominazione
            # Es. "Chianti / Classico" → non estrarre "Chianti" come regione
            continue
    
    return None, classification


def normalize_region_value(region: Optional[str]) -> Optional[str]:
    """
    Normalizza valore regione (capitalizza, corregge typo comuni).
    
    Esempi:
    - "toscana" → "Toscana"
    - "TOSCANA" → "Toscana"
    - "toscata" → "Toscana" (correzione typo)
    """
    if not region or not region.strip():
        return None
    
    region_clean = region.strip()
    
    # Correzione typo comuni
    typo_corrections = {
        'toscata': 'Toscana',
        'piemonte': 'Piemonte',  # Già corretto, ma per sicurezza
    }
    
    if region_clean.lower() in typo_corrections:
        return typo_corrections[region_clean.lower()]
    
    # Match case-insensitive con regioni italiane
    for valid_region in ITALIAN_REGIONS:
        if valid_region.lower() == region_clean.lower():
            return valid_region
    
    # Se non matcha, capitalizza e ritorna
    return region_clean.capitalize()


def normalize_country_value(country: Optional[str]) -> Optional[str]:
    """
    Normalizza valore country (capitalizza, corregge sinonimi).
    
    Esempi:
    - "italia" → "Italia"
    - "ITALIA" → "Italia"
    - "stati uniti" → "USA"
    """
    if not country or not country.strip():
        return None
    
    country_clean = country.strip()
    country_lower = country_clean.lower()
    
    # Mappa sinonimi
    country_synonyms = {
        'stati uniti': 'USA',
        'stati uniti d\'america': 'USA',
        'america': 'USA',
        'united states': 'USA',
        'us': 'USA',
        'italia': 'Italia',
        'italy': 'Italia',
        'francia': 'Francia',
        'france': 'Francia',
        'spagna': 'Spagna',
        'spain': 'Spagna',
        'germania': 'Germania',
        'germany': 'Germania',
        'portogallo': 'Portogallo',
        'portugal': 'Portogallo',
        'australia': 'Australia',
        'cile': 'Cile',
        'chile': 'Cile',
        'argentina': 'Argentina',
    }
    
    if country_lower in country_synonyms:
        return country_synonyms[country_lower]
    
    # Se non è un sinonimo, capitalizza
    return country_clean.capitalize()


def infer_country_from_region(region: Optional[str]) -> Optional[str]:
    """
    Infers country da region se region è una regione italiana.
    
    Esempi:
    - "Toscana" → "Italia"
    - "Piemonte" → "Italia"
    """
    if not region:
        return None
    
    # Verifica se region è una regione italiana
    for italian_region in ITALIAN_REGIONS:
        if italian_region.lower() == region.lower():
            return 'Italia'
    
    return None


def is_invalid_wine_name(name: Optional[str], winery: Optional[str], qty: int, price: Optional[float]) -> bool:
    """
    Verifica se un nome vino è invalido.
    
    Criteri per nome invalido:
    1. Vuoto o None
    2. Placeholder ('nan', 'none', 'null', etc.)
    3. Solo numeri (es. "0", "1", "10", "255")
    4. Troppo corto (< 2 caratteri) E senza altri dati significativi
    
    Args:
        name: Nome vino
        winery: Produttore (opzionale)
        qty: Quantità
        price: Prezzo (opzionale)
    
    Returns:
        True se il nome è invalido, False altrimenti
    """
    if not name or not name.strip():
        return True
    
    name_clean = name.strip()
    
    # Placeholder comuni
    if name_clean.lower() in ['nan', 'none', 'null', 'n/a', 'na', 'undefined', '', ' ']:
        return True
    
    # Solo numeri (es. "0", "1", "10", "255")
    if name_clean.isdigit():
        return True
    
    # Troppo corto (< 2 caratteri) E senza altri dati significativi
    if len(name_clean) < 2:
        has_meaningful_data = (
            (winery and winery.strip()) or
            qty > 0 or
            price is not None
        )
        if not has_meaningful_data:
            return True
    
    return False


async def validate_wines_with_llm(
    wines_sample: List[Dict[str, Any]],
    max_wines: int = 20
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Valida campione di vini con LLM economico (gpt-4o-mini o gpt-3.5-turbo).
    
    Controlla:
    - Nomi vini corretti (non categorie come "Bolle", "Rosè")
    - Tipi vino corretti
    - Dati coerenti (es. vintage ragionevole, prezzo positivo)
    
    Args:
        wines_sample: Lista di vini da validare (max max_wines)
        max_wines: Numero massimo di vini da validare (default 20)
    
    Returns:
        Tuple (has_errors, corrections, common_patterns) dove:
        - has_errors: True se ci sono errori trovati
        - corrections: Lista di correzioni specifiche per vini nel campione
        - common_patterns: Lista di pattern comuni da applicare a tutti i vini
    """
    client = get_openai_client()
    if not client:
        # Se OpenAI non disponibile, salta validazione
        return False, [], []
    
    if not wines_sample or len(wines_sample) == 0:
        return False, [], []
    
    # Limita campione per contenere costi
    sample = wines_sample[:max_wines]
    
    try:
        # Prepara prompt per validazione
        wines_json = json.dumps(sample, ensure_ascii=False, indent=2)
        
        prompt = f"""Analizza questo campione di vini da un inventario e identifica errori comuni e PATTERN RICORRENTI.

CAMPIONE VINI:
{wines_json}

ERRORI DA CERCARE:
1. Nomi vini che sono categorie/tipi invece di nomi reali (es. "Bolle", "Rosè", "Brut" senza nome vino tra parentesi)
2. Pattern "Categoria (Nome Vino)" non estratti (es. "Bolle (Dom Perignon)" dovrebbe essere "Dom Perignon")
3. Tipi vino mancanti o errati (inferisci da nome se possibile)
4. Dati incoerenti (vintage fuori range 1900-2099, prezzi negativi, etc.)

TERMINI PROBLEMATICI (usa dizionario wine_terms_dict):
- Categorie spumanti: Bolle, Spumante, Champagne, Prosecco, Brut, Cava, Crémant, Frizzante
- Tipi vino: Rosso, Bianco, Rosato, Rosè, Passito, Dolce, Secco
- Regioni: Toscana, Piemonte, Veneto, Sicilia, Bordeaux, Bourgogne, etc.
- Classificazioni: DOC, DOCG, IGT, AOC, AOP, IGP
- Termini tecnici: Riserva, Classico, Superiore, Vintage, Barrique
Se il nome è SOLO uno di questi termini, usa "producer" come nome e imposta "wine_type" appropriato.

IMPORTANTE - IDENTIFICA PATTERN COMUNI:
Se vedi lo stesso errore ripetuto in molti vini (es. molti vini con "Bolle" come nome), identifica il PATTERN e suggerisci una correzione batch.

Rispondi con JSON object con due campi:
{{
  "corrections": [
    {{
      "wine_index": 0,
      "field": "name",
      "old_value": "Bolle",
      "new_value": "Dom Perignon",
      "reason": "Nome è categoria, estrai da pattern se presente"
    }}
  ],
  "common_patterns": [
    {{
      "field": "name",
      "old_value_pattern": "Bolle",
      "correction_rule": "extract_from_parentheses",
      "inferred_type": "Spumante",
      "description": "Molti vini hanno 'Bolle' come nome invece di tipo. Se il nome contiene parentesi, estrai il contenuto. Altrimenti usa il producer come nome."
    }}
  ]
}}

Se non ci sono errori, rispondi con: {{"corrections": [], "common_patterns": []}}
"""
        
        # Usa modello economico (gpt-4o-mini o gpt-3.5-turbo)
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Modello economico
            messages=[
                {
                    "role": "system",
                    "content": "Sei un validatore di dati inventario vini. Identifica errori comuni e PATTERN RICORRENTI. Rispondi SOLO con JSON object con 'corrections' e 'common_patterns'."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1500  # Aumentato per gestire pattern comuni
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Estrai JSON dalla risposta
        try:
            # Rimuovi markdown code blocks se presenti
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            
            # Gestisci sia formato vecchio (array) che nuovo (object con corrections e common_patterns)
            if isinstance(result, list):
                # Formato vecchio (backward compatibility)
                corrections = result
                common_patterns = []
            elif isinstance(result, dict):
                corrections = result.get("corrections", [])
                common_patterns = result.get("common_patterns", [])
            else:
                corrections = []
                common_patterns = []
            
            if not isinstance(corrections, list):
                corrections = []
            if not isinstance(common_patterns, list):
                common_patterns = []
            
            has_errors = len(corrections) > 0 or len(common_patterns) > 0
            
            logger.info(
                f"[POST_PROCESSING] Validazione LLM: {len(corrections)} correzioni specifiche, "
                f"{len(common_patterns)} pattern comuni identificati su {len(sample)} vini validati"
            )
            
            return has_errors, corrections, common_patterns
            
        except json.JSONDecodeError as e:
            logger.warning(f"[POST_PROCESSING] Errore parsing JSON validazione LLM: {e}, risposta: {response_text[:200]}")
            return False, [], []
            
    except Exception as e:
        logger.warning(f"[POST_PROCESSING] Errore validazione LLM: {e}")
        return False, [], []


async def normalize_saved_inventory(
    session: AsyncSession,
    telegram_id: int,
    business_name: str,
    job_id: Optional[str] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Normalizza inventario salvato in background con validazione LLM finale.
    
    Legge tutti i vini dalla tabella inventario e applica normalizzazioni:
    1. Filtra e rimuove vini con nomi invalidi (solo numeri, troppo corti, placeholder)
    2. Estrae nome vino da pattern "Categoria (Nome Vino)"
    3. Estrae regione da classification se region è vuoto
    4. Normalizza valori region, country, wine_type
    5. Infers country da region se country è vuoto
    6. Validazione finale con LLM economico (max max_retries retry se trova errori)
    
    Args:
        session: Database session
        telegram_id: ID Telegram utente
        business_name: Nome business
        job_id: ID job (opzionale, per logging)
        max_retries: Numero massimo di retry con validazione LLM (default 3)
    
    Returns:
        Dict con statistiche normalizzazione:
        {
            "total_wines": int,
            "invalid_wines_removed": int,
            "normalized_count": int,
            "region_extracted": int,
            "country_inferred": int,
            "values_normalized": int,
            "llm_validation_retries": int,
            "llm_corrections_applied": int
        }
    """
    stats = {
        "total_wines": 0,
        "invalid_wines_removed": 0,
        "normalized_count": 0,
        "region_extracted": 0,
        "country_inferred": 0,
        "values_normalized": 0,
        "llm_validation_retries": 0,
        "llm_corrections_applied": 0
    }
    
    try:
        table_name = get_user_table_name(telegram_id, business_name, "INVENTARIO")
        
        # Recupera user_id
        from core.database import User
        result = await session.execute(
            sql_text("SELECT id FROM users WHERE telegram_id = :telegram_id"),
            {"telegram_id": telegram_id}
        )
        user_row = result.fetchone()
        if not user_row:
            logger.warning(f"[POST_PROCESSING] User {telegram_id} non trovato")
            return stats
        
        user_id = user_row[0]
        
        # Leggi tutti i vini dalla tabella (include anche producer, qty, price per validazione nome)
        query = sql_text(f"""
            SELECT id, name, producer, quantity, selling_price, region, country, classification, wine_type
            FROM {table_name}
            WHERE user_id = :user_id
        """)
        result = await session.execute(query, {"user_id": user_id})
        wines = result.fetchall()
        
        stats["total_wines"] = len(wines)
        logger.info(
            f"[POST_PROCESSING] Job {job_id}: Trovati {len(wines)} vini da normalizzare "
            f"per {telegram_id}/{business_name}"
        )
        
        if not wines:
            return stats
        
        # 1. Filtra e rimuove vini con nomi invalidi
        invalid_wine_ids = []
        valid_wines = []
        
        for wine in wines:
            wine_id = wine.id
            wine_name = wine.name
            wine_producer = wine.producer if hasattr(wine, 'producer') else None
            wine_qty = wine.quantity if hasattr(wine, 'quantity') else 0
            wine_price = wine.selling_price if hasattr(wine, 'selling_price') else None
            
            if is_invalid_wine_name(wine_name, wine_producer, wine_qty, wine_price):
                invalid_wine_ids.append(wine_id)
                logger.debug(
                    f"[POST_PROCESSING] Vino {wine_id} marcato per rimozione: "
                    f"nome invalido '{wine_name}'"
                )
            else:
                valid_wines.append(wine)
        
        # Rimuovi vini invalidi dal database
        if invalid_wine_ids:
            # Usa IN con lista per compatibilità asyncpg
            # Costruisci query con placeholder per ogni ID
            placeholders = ','.join([f':id_{i}' for i in range(len(invalid_wine_ids))])
            delete_query = sql_text(f"""
                DELETE FROM {table_name}
                WHERE id IN ({placeholders}) AND user_id = :user_id
            """)
            params = {f'id_{i}': wine_id for i, wine_id in enumerate(invalid_wine_ids)}
            params['user_id'] = user_id
            await session.execute(delete_query, params)
            await session.commit()
            stats["invalid_wines_removed"] = len(invalid_wine_ids)
            
            # Log nomi vini rimossi (primi 10)
            removed_names = [w.name for w in wines if w.id in invalid_wine_ids][:10]
            logger.info(
                f"[POST_PROCESSING] Job {job_id}: Rimossi {len(invalid_wine_ids)} vini con nomi invalidi "
                f"(esempi: {removed_names}{'...' if len(invalid_wine_ids) > 10 else ''})"
            )
        
        # Processa ogni vino valido per normalizzazione
        updates = []
        for wine in valid_wines:
            wine_id = wine.id
            current_name = wine.name
            current_region = wine.region
            current_country = wine.country
            current_classification = wine.classification
            current_wine_type = wine.wine_type
            
            needs_update = False
            new_name = current_name
            new_region = current_region
            new_country = current_country
            new_classification = current_classification
            new_wine_type = current_wine_type
            
            # 0. Estrai nome vino da pattern "Categoria (Nome Vino)" se presente
            if current_name:
                extracted_name, inferred_type = extract_wine_name_from_category_pattern(current_name)
                if extracted_name != current_name:
                    # Nome è stato estratto da pattern
                    new_name = extracted_name
                    needs_update = True
                    # Se tipo è stato inferito e non c'è già un tipo, usalo
                    if inferred_type and not current_wine_type:
                        new_wine_type = inferred_type
                    logger.debug(
                        f"[POST_PROCESSING] Job {job_id}: Estratto nome da pattern categoria "
                        f"per vino '{current_name}' → name='{new_name}', type={new_wine_type} "
                        f"(telegram_id={telegram_id}, wine_id={wine_id})"
                    )
            
            # 1. Estrai regione da classification se region è vuoto
            if not current_region and current_classification:
                extracted_region, cleaned_classification = extract_region_from_classification(
                    current_classification
                )
                if extracted_region:
                    new_region = extracted_region
                    new_classification = cleaned_classification
                    needs_update = True
                    stats["region_extracted"] += 1
                    logger.debug(
                        f"[POST_PROCESSING] Vino {wine_id}: Estratta regione '{extracted_region}' "
                        f"da classification '{current_classification}'"
                    )
            
            # 2. Normalizza regione
            if new_region:
                normalized_region = normalize_region_value(new_region)
                if normalized_region != new_region:
                    new_region = normalized_region
                    needs_update = True
                    stats["values_normalized"] += 1
            
            # 3. Normalizza country
            if new_country:
                normalized_country = normalize_country_value(new_country)
                if normalized_country != new_country:
                    new_country = normalized_country
                    needs_update = True
                    stats["values_normalized"] += 1
            
            # 4. Infers country da region se country è vuoto
            if not new_country and new_region:
                inferred_country = infer_country_from_region(new_region)
                if inferred_country:
                    new_country = inferred_country
                    needs_update = True
                    stats["country_inferred"] += 1
                    logger.debug(
                        f"[POST_PROCESSING] Vino {wine_id}: Inferito country '{inferred_country}' "
                        f"da region '{new_region}'"
                    )
            
            # Se ci sono modifiche, aggiungi a updates
            if needs_update:
                update_data = {
                    "id": wine_id,
                    "region": new_region,
                    "country": new_country,
                    "classification": new_classification
                }
                # Aggiungi name e wine_type solo se modificati
                if new_name != current_name:
                    update_data["name"] = new_name
                if new_wine_type != current_wine_type:
                    update_data["wine_type"] = new_wine_type
                updates.append(update_data)
        
        # Esegui UPDATE batch se ci sono modifiche
        if updates:
            logger.info(
                f"[POST_PROCESSING] Job {job_id}: Normalizzando {len(updates)} vini "
                f"su {len(wines)} totali"
            )
            
            for update_data in updates:
                # Costruisci query UPDATE dinamica in base ai campi modificati
                set_clauses = []
                params = {"id": update_data["id"], "user_id": user_id}
                
                if "name" in update_data:
                    set_clauses.append("name = :name")
                    params["name"] = update_data["name"]
                if "wine_type" in update_data:
                    set_clauses.append("wine_type = :wine_type")
                    params["wine_type"] = update_data["wine_type"]
                if "region" in update_data:
                    set_clauses.append("region = :region")
                    params["region"] = update_data["region"]
                if "country" in update_data:
                    set_clauses.append("country = :country")
                    params["country"] = update_data["country"]
                if "classification" in update_data:
                    set_clauses.append("classification = :classification")
                    params["classification"] = update_data["classification"]
                
                if set_clauses:
                    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                    update_query = sql_text(f"""
                        UPDATE {table_name}
                        SET {', '.join(set_clauses)}
                        WHERE id = :id AND user_id = :user_id
                    """)
                    await session.execute(update_query, params)
            
            await session.commit()
            stats["normalized_count"] = len(updates)
            
            logger.info(
                f"[POST_PROCESSING] Job {job_id}: Normalizzazione completata - "
                f"{stats['invalid_wines_removed']} vini invalidi rimossi, "
                f"{stats['normalized_count']} vini aggiornati "
                f"({stats['region_extracted']} regioni estratte, "
                f"{stats['country_inferred']} country inferiti, "
                f"{stats['values_normalized']} valori normalizzati)"
            )
        else:
            logger.info(
                f"[POST_PROCESSING] Job {job_id}: Nessuna normalizzazione necessaria "
                f"per {len(wines)} vini"
            )
        
        # ✅ VALIDAZIONE LLM FINALE con retry (max max_retries volte)
        llm_retry_count = 0
        while llm_retry_count < max_retries:
            # Leggi vini aggiornati per validazione
            result = await session.execute(query, {"user_id": user_id})
            wines_after_normalization = result.fetchall()
            
            if not wines_after_normalization:
                break
            
            # Prepara campione per validazione LLM (max 20 vini)
            wines_sample = []
            for wine in wines_after_normalization[:20]:
                wines_sample.append({
                    "id": wine.id,
                    "name": wine.name,
                    "producer": wine.producer if hasattr(wine, 'producer') else None,
                    "vintage": wine.vintage if hasattr(wine, 'vintage') else None,
                    "qty": wine.quantity if hasattr(wine, 'quantity') else 0,
                    "price": wine.selling_price if hasattr(wine, 'selling_price') else None,
                    "wine_type": wine.wine_type,
                    "region": wine.region,
                    "country": wine.country,
                    "classification": wine.classification
                })
            
            # Valida con LLM
            has_errors, corrections, common_patterns = await validate_wines_with_llm(wines_sample, max_wines=20)
            
            if not has_errors or (len(corrections) == 0 and len(common_patterns) == 0):
                # Nessun errore trovato, esci dal loop
                logger.info(
                    f"[POST_PROCESSING] Job {job_id}: Validazione LLM completata - "
                    f"nessun errore trovato (retry {llm_retry_count + 1}/{max_retries})"
                )
                break
            
            corrections_applied = 0
            
            # ✅ PRIORITÀ 1: Applica pattern comuni a TUTTI i vini (batch update)
            if common_patterns:
                logger.info(
                    f"[POST_PROCESSING] Job {job_id}: Identificati {len(common_patterns)} pattern comuni, "
                    f"applicazione batch a tutti i vini..."
                )
                
                for pattern in common_patterns:
                    field = pattern.get("field")
                    old_value_pattern = pattern.get("old_value_pattern")
                    correction_rule = pattern.get("correction_rule")
                    inferred_type = pattern.get("inferred_type")
                    
                    if not field or not old_value_pattern:
                        continue
                    
                    # Trova tutti i vini con questo pattern
                    pattern_matches = []
                    for wine in wines_after_normalization:
                        wine_value = getattr(wine, field, None) if hasattr(wine, field) else None
                        if wine_value and old_value_pattern.lower() in str(wine_value).lower():
                            pattern_matches.append(wine)
                    
                    if not pattern_matches:
                        continue
                    
                    logger.info(
                        f"[POST_PROCESSING] Job {job_id}: Pattern '{old_value_pattern}' trovato in "
                        f"{len(pattern_matches)} vini, applicazione correzione batch..."
                    )
                    
                    # Applica correzione batch in base alla regola
                    for wine in pattern_matches:
                        try:
                            new_value = None
                            
                            if correction_rule == "extract_from_parentheses":
                                # Estrai nome da pattern "Categoria (Nome Vino)"
                                wine_name = getattr(wine, "name", None) if field == "name" else None
                                if wine_name:
                                    extracted_name, inferred_type_from_pattern = extract_wine_name_from_category_pattern(wine_name)
                                    if extracted_name != wine_name:
                                        new_value = extracted_name
                                        # Se tipo è stato inferito e field è name, aggiorna anche wine_type
                                        if inferred_type_from_pattern and field == "name":
                                            # Aggiorna anche wine_type se mancante
                                            if not getattr(wine, "wine_type", None):
                                                type_update_query = sql_text(f"""
                                                    UPDATE {table_name}
                                                    SET wine_type = :wine_type, updated_at = CURRENT_TIMESTAMP
                                                    WHERE id = :wine_id AND user_id = :user_id
                                                """)
                                                await session.execute(type_update_query, {
                                                    "wine_type": inferred_type_from_pattern,
                                                    "wine_id": wine.id,
                                                    "user_id": user_id
                                                })
                            elif correction_rule == "use_producer_as_name" and field == "name":
                                # Usa producer come nome se disponibile
                                producer = getattr(wine, "producer", None)
                                if producer:
                                    new_value = producer
                            elif inferred_type and field == "wine_type":
                                # Imposta tipo inferito
                                new_value = inferred_type
                            
                            if new_value:
                                update_query = sql_text(f"""
                                    UPDATE {table_name}
                                    SET {field} = :new_value, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = :wine_id AND user_id = :user_id
                                """)
                                await session.execute(update_query, {
                                    "new_value": new_value,
                                    "wine_id": wine.id,
                                    "user_id": user_id
                                })
                                corrections_applied += 1
                                
                        except Exception as pattern_error:
                            logger.warning(
                                f"[POST_PROCESSING] Job {job_id}: Errore applicazione pattern batch: {pattern_error}"
                            )
                            # Rollback esplicito se la transazione è in stato aborted
                            try:
                                await session.rollback()
                            except:
                                pass
                            continue
                    
                    # Commit dopo ogni pattern per evitare transazioni troppo lunghe
                    if corrections_applied > 0:
                        try:
                            await session.commit()
                        except Exception as commit_error:
                            logger.warning(
                                f"[POST_PROCESSING] Job {job_id}: Errore commit pattern '{old_value_pattern}': {commit_error}"
                            )
                            try:
                                await session.rollback()
                            except:
                                pass
                    
                    logger.info(
                        f"[POST_PROCESSING] Job {job_id}: Pattern '{old_value_pattern}' - "
                        f"applicate {len(pattern_matches)} correzioni batch"
                    )
            
            # ✅ PRIORITÀ 2: Applica correzioni specifiche per vini nel campione
            for correction in corrections:
                try:
                    wine_index = correction.get("wine_index")
                    field = correction.get("field")
                    new_value = correction.get("new_value")
                    
                    if wine_index is None or field is None or new_value is None:
                        continue
                    
                    # Trova il vino corrispondente
                    if wine_index < len(wines_sample):
                        wine_id_to_update = wines_sample[wine_index]["id"]
                        
                        # Costruisci UPDATE dinamico
                        update_query = sql_text(f"""
                            UPDATE {table_name}
                            SET {field} = :new_value, updated_at = CURRENT_TIMESTAMP
                            WHERE id = :wine_id AND user_id = :user_id
                        """)
                        await session.execute(update_query, {
                            "new_value": new_value,
                            "wine_id": wine_id_to_update,
                            "user_id": user_id
                        })
                        corrections_applied += 1
                        logger.debug(
                            f"[POST_PROCESSING] Job {job_id}: Applicata correzione LLM - "
                            f"vino {wine_id_to_update}, campo {field} = '{new_value}'"
                        )
                except Exception as corr_error:
                    logger.warning(
                        f"[POST_PROCESSING] Job {job_id}: Errore applicazione correzione LLM: {corr_error}"
                    )
                    # Rollback esplicito se la transazione è in stato aborted
                    try:
                        await session.rollback()
                    except:
                        pass
                    continue
            
            if corrections_applied > 0:
                await session.commit()
                stats["llm_corrections_applied"] += corrections_applied
                llm_retry_count += 1
                stats["llm_validation_retries"] = llm_retry_count
                
                logger.info(
                    f"[POST_PROCESSING] Job {job_id}: Applicate {corrections_applied} correzioni LLM "
                    f"(retry {llm_retry_count}/{max_retries})"
                )
                
                # Se ci sono ancora correzioni, continua il loop per rifare post-processing
                # (le normalizzazioni precedenti verranno riapplicate)
            else:
                # Nessuna correzione applicabile, esci
                break
        
        if llm_retry_count > 0:
            logger.info(
                f"[POST_PROCESSING] Job {job_id}: Validazione LLM completata - "
                f"{stats['llm_corrections_applied']} correzioni applicate in {llm_retry_count} retry"
            )
        
        return stats
        
    except Exception as e:
        logger.error(
            f"[POST_PROCESSING] Job {job_id}: Errore normalizzazione inventario: {e}",
            exc_info=True
        )
        # Non sollevare eccezione - la normalizzazione è opzionale
        return stats

