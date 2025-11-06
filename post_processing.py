"""
Post-Processing Normalization - Normalizza inventario salvato in background.

Dopo che l'inventario è stato salvato, esegue un secondo passaggio per:
- Estrarre nome vino da pattern "Categoria (Nome Vino)" (es. "Bolle (Dom Perignon)" → name="Dom Perignon", type="Spumante")
- Estrarre regione da classification (es. "Marche / Verdicchio DOC" → region="Marche")
- Normalizzare valori (country, region, wine_type)
- Estrarre country da region se country è vuoto
- Pulire classification rimuovendo regione se già estratta
"""
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_user_table_name
from ingest.normalization import extract_wine_name_from_category_pattern

logger = logging.getLogger(__name__)

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


async def normalize_saved_inventory(
    session: AsyncSession,
    telegram_id: int,
    business_name: str,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Normalizza inventario salvato in background.
    
    Legge tutti i vini dalla tabella inventario e applica normalizzazioni:
    1. Filtra e rimuove vini con nomi invalidi (solo numeri, troppo corti, placeholder)
    2. Estrae regione da classification se region è vuoto
    3. Normalizza valori region, country, wine_type
    4. Infers country da region se country è vuoto
    5. Aggiorna database con valori normalizzati
    
    Args:
        session: Database session
        telegram_id: ID Telegram utente
        business_name: Nome business
        job_id: ID job (opzionale, per logging)
    
    Returns:
        Dict con statistiche normalizzazione:
        {
            "total_wines": int,
            "invalid_wines_removed": int,
            "normalized_count": int,
            "region_extracted": int,
            "country_inferred": int,
            "values_normalized": int
        }
    """
    stats = {
        "total_wines": 0,
        "invalid_wines_removed": 0,
        "normalized_count": 0,
        "region_extracted": 0,
        "country_inferred": 0,
        "values_normalized": 0
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
        
        # Leggi tutti i vini dalla tabella (include anche winery, qty, price per validazione nome)
        query = sql_text(f"""
            SELECT id, name, winery, qty, price, region, country, classification, wine_type
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
            wine_winery = wine.winery
            wine_qty = wine.qty if hasattr(wine, 'qty') else 0
            wine_price = wine.price if hasattr(wine, 'price') else None
            
            if is_invalid_wine_name(wine_name, wine_winery, wine_qty, wine_price):
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
        
        return stats
        
    except Exception as e:
        logger.error(
            f"[POST_PROCESSING] Job {job_id}: Errore normalizzazione inventario: {e}",
            exc_info=True
        )
        # Non sollevare eccezione - la normalizzazione è opzionale
        return stats

