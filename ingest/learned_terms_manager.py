"""
Manager per termini problematici appresi dall'LLM.

Gestisce il salvataggio e il recupero di termini problematici riconosciuti dall'LLM
durante il post-processing che non sono presenti nel dizionario statico.
"""
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

logger = logging.getLogger(__name__)


async def save_learned_term(
    session: AsyncSession,
    problematic_term: str,
    corrected_term: str,
    wine_type: Optional[str] = None,
    category: Optional[str] = None
) -> bool:
    """
    Salva o aggiorna un termine problematico appreso dall'LLM.
    
    Args:
        session: Sessione database async
        problematic_term: Termine problematico riconosciuto (es. "Bolle", "Rosè")
        corrected_term: Termine corretto o traduzione (es. nome vino reale o winery)
        wine_type: Tipo vino inferito (opzionale, es. "Spumante", "Rosato")
        category: Categoria del termine (opzionale, es. "categoria spumante", "tipo vino")
    
    Returns:
        True se salvato/aggiornato con successo, False altrimenti
    """
    if not problematic_term or not corrected_term:
        return False
    
    try:
        # Upsert: inserisci o aggiorna se esiste già
        upsert_query = sql_text("""
            INSERT INTO learned_problematic_terms 
                (problematic_term, corrected_term, wine_type, category, usage_count, first_seen_at, last_seen_at)
            VALUES 
                (:problematic_term, :corrected_term, :wine_type, :category, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (problematic_term) 
            DO UPDATE SET 
                corrected_term = EXCLUDED.corrected_term,
                wine_type = COALESCE(EXCLUDED.wine_type, learned_problematic_terms.wine_type),
                category = COALESCE(EXCLUDED.category, learned_problematic_terms.category),
                usage_count = learned_problematic_terms.usage_count + 1,
                last_seen_at = CURRENT_TIMESTAMP
        """)
        
        await session.execute(upsert_query, {
            "problematic_term": problematic_term.lower().strip(),
            "corrected_term": corrected_term.strip(),
            "wine_type": wine_type,
            "category": category
        })
        
        await session.commit()
        logger.debug(f"Saved learned term: '{problematic_term}' → '{corrected_term}' (type={wine_type}, category={category})")
        return True
        
    except Exception as e:
        logger.error(f"Error saving learned term '{problematic_term}': {e}", exc_info=True)
        await session.rollback()
        return False


async def get_learned_terms(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Recupera tutti i termini problematici appresi dal database.
    
    Args:
        session: Sessione database async
    
    Returns:
        Lista di dict con chiavi: problematic_term, corrected_term, wine_type, category, usage_count
    """
    try:
        query = sql_text("""
            SELECT problematic_term, corrected_term, wine_type, category, usage_count
            FROM learned_problematic_terms
            ORDER BY usage_count DESC, last_seen_at DESC
        """)
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        terms = []
        for row in rows:
            terms.append({
                "problematic_term": row[0],
                "corrected_term": row[1],
                "wine_type": row[2],
                "category": row[3],
                "usage_count": row[4]
            })
        
        logger.debug(f"Retrieved {len(terms)} learned terms from database")
        return terms
        
    except Exception as e:
        logger.error(f"Error retrieving learned terms: {e}", exc_info=True)
        return []


async def get_learned_term_by_problematic(
    session: AsyncSession,
    problematic_term: str
) -> Optional[Dict[str, Any]]:
    """
    Recupera un termine appreso specifico per termine problematico.
    
    Args:
        session: Sessione database async
        problematic_term: Termine problematico da cercare
    
    Returns:
        Dict con dati del termine o None se non trovato
    """
    if not problematic_term:
        return None
    
    try:
        query = sql_text("""
            SELECT problematic_term, corrected_term, wine_type, category, usage_count
            FROM learned_problematic_terms
            WHERE problematic_term = :problematic_term
        """)
        
        result = await session.execute(query, {"problematic_term": problematic_term.lower().strip()})
        row = result.fetchone()
        
        if row:
            return {
                "problematic_term": row[0],
                "corrected_term": row[1],
                "wine_type": row[2],
                "category": row[3],
                "usage_count": row[4]
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving learned term '{problematic_term}': {e}", exc_info=True)
        return None


async def load_learned_terms_set(session: AsyncSession) -> set:
    """
    Carica tutti i termini problematici appresi come set per lookup veloce.
    
    Args:
        session: Sessione database async
    
    Returns:
        Set di termini problematici (lowercase)
    """
    terms = await get_learned_terms(session)
    return {term["problematic_term"] for term in terms}


async def load_learned_terms_dict(session: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """
    Carica tutti i termini problematici appresi come dict per lookup veloce.
    
    Args:
        session: Sessione database async
    
    Returns:
        Dict con chiave=problematic_term, valore=dict con corrected_term, wine_type, category
    """
    terms = await get_learned_terms(session)
    return {
        term["problematic_term"]: {
            "corrected_term": term["corrected_term"],
            "wine_type": term["wine_type"],
            "category": term["category"],
            "usage_count": term["usage_count"]
        }
        for term in terms
    }


