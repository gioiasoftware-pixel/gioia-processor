"""
Router admin per inserimento diretto inventari puliti.

Endpoint:
- POST /admin/insert-inventory: Inserisce inventario pulito direttamente nel database
  senza passare attraverso la pipeline di pulizia/normalizzazione.
"""
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select, text as sql_text

from core.database import get_db, User, ensure_user_tables, batch_insert_wines
from core.logger import log_with_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_int(value: Any) -> Optional[int]:
    """Converte valore a int, ritorna None se invalido."""
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (ValueError, TypeError):
        return None


def _parse_float(value: Any) -> Optional[float]:
    """Converte valore a float, ritorna None se invalido."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def parse_csv_content(csv_content: bytes) -> List[Dict[str, Any]]:
    """
    Legge CSV inventario pulito e restituisce lista di vini.
    
    Supporta header del template:
    Nome,Produttore,Fornitore,Annata,Quantità,Prezzo,Costo,Tipologia,Uvaggio,Regione,Paese,Classificazione
    """
    wines = []
    
    # Decodifica CSV
    try:
        csv_text = csv_content.decode('utf-8')
    except UnicodeDecodeError:
        # Prova altri encoding comuni
        try:
            csv_text = csv_content.decode('latin-1')
        except:
            csv_text = csv_content.decode('utf-8', errors='ignore')
    
    # Leggi CSV
    reader = csv.DictReader(csv_text.splitlines())
    
    for row_num, row in enumerate(reader, start=2):  # Start da 2 (dopo header)
        try:
            # Normalizza chiavi (rimuovi spazi, lowercase)
            normalized_row = {k.strip().lower(): v.strip() if isinstance(v, str) else v 
                             for k, v in row.items()}
            
            # Mappa header CSV a campi database
            wine = {
                "name": normalized_row.get("nome", "").strip(),
                "winery": normalized_row.get("produttore", "").strip() or None,
                "supplier": normalized_row.get("fornitore", "").strip() or None,
                "vintage": _parse_int(normalized_row.get("annata")),
                "qty": _parse_float(normalized_row.get("quantità", "0")) or 0,
                "price": _parse_float(normalized_row.get("prezzo")),
                "cost_price": _parse_float(normalized_row.get("costo")),
                "type": normalized_row.get("tipologia", "").strip() or None,
                "grape_variety": normalized_row.get("uvaggio", "").strip() or None,
                "region": normalized_row.get("regione", "").strip() or None,
                "country": normalized_row.get("paese", "").strip() or None,
                "classification": normalized_row.get("classificazione", "").strip() or None,
            }
            
            # Validazione minima: name e qty obbligatori
            if not wine["name"]:
                logger.warning(f"Riga {row_num}: Nome vuoto, saltata")
                continue
            
            if wine["qty"] is None or wine["qty"] < 0:
                logger.warning(f"Riga {row_num}: Quantità invalida ({wine['qty']}), impostata a 0")
                wine["qty"] = 0
            
            wines.append(wine)
            
        except Exception as e:
            logger.error(f"Errore parsing riga {row_num}: {e}")
            continue
    
    return wines


@router.post("/insert-inventory")
async def admin_insert_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file: UploadFile = File(...),
    mode: str = Form("add"),  # "add" o "replace"
):
    """
    Endpoint admin per inserire inventario pulito direttamente nel database.
    
    Questo endpoint:
    1. Crea le tabelle utente se non esistono (INVENTARIO, BACKUP, LOG, CONSUMI)
    2. Inserisce i vini direttamente senza passare attraverso la pipeline
    3. NON esegue pulizie/normalizzazioni (CSV deve essere già pulito)
    
    Args:
        telegram_id: ID Telegram utente
        business_name: Nome business
        file: File CSV inventario pulito
        mode: "add" (aggiunge) o "replace" (sostituisce)
    
    Returns:
        Dict con risultato inserimento
    """
    correlation_id = f"admin_insert_{telegram_id}_{business_name}"
    
    try:
        log_with_context(
            "info",
            f"[ADMIN_INSERT] Inizio inserimento inventario per {telegram_id}/{business_name}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Leggi file CSV
        file_content = await file.read()
        
        # Parse CSV
        wines = parse_csv_content(file_content)
        
        if not wines:
            raise HTTPException(
                status_code=400,
                detail="Nessun vino trovato nel CSV. Verifica formato file."
            )
        
        log_with_context(
            "info",
            f"[ADMIN_INSERT] Trovati {len(wines)} vini nel CSV",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        async for db in get_db():
            # Crea/verifica utente e tabelle
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = user_tables["inventario"]
            
            log_with_context(
                "info",
                f"[ADMIN_INSERT] Tabelle utente verificate/create: {list(user_tables.keys())}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            # Trova utente per user_id
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(
                    status_code=404,
                    detail=f"Utente {telegram_id} non trovato dopo creazione tabelle"
                )
            
            # Se mode='replace', elimina tutti i vini esistenti
            if mode == "replace":
                delete_stmt = sql_text(f"""
                    DELETE FROM {table_inventario}
                    WHERE user_id = :user_id
                """)
                await db.execute(delete_stmt, {"user_id": user.id})
                await db.commit()
                log_with_context(
                    "info",
                    f"[ADMIN_INSERT] Inventario esistente eliminato (mode=replace)",
                    telegram_id=telegram_id,
                    correlation_id=correlation_id
                )
            
            # Batch insert vini (SENZA normalizzazioni/pulizie)
            saved_count, error_count = await batch_insert_wines(
                db,
                table_inventario,
                wines,
                user_id=user.id
            )
            
            await db.commit()
            
            log_with_context(
                "info",
                f"[ADMIN_INSERT] Inserimento completato: {saved_count} salvati, {error_count} errori",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            return {
                "status": "success",
                "telegram_id": telegram_id,
                "business_name": business_name,
                "total_wines": len(wines),
                "saved_wines": saved_count,
                "error_count": error_count,
                "tables_created": list(user_tables.keys()),
                "mode": mode
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ADMIN_INSERT] Errore inserimento inventario: {e}",
            exc_info=True,
            extra={
                "telegram_id": telegram_id,
                "correlation_id": correlation_id
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Errore inserimento inventario: {str(e)}"
        )

