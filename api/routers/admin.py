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

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Body
from pydantic import BaseModel
import base64
from sqlalchemy import select, text as sql_text

from core.database import get_db, User, ensure_user_tables, find_or_create_user_by_business_name, batch_insert_wines
from core.logger import log_with_context
from core.scheduler import generate_daily_movements_report, send_daily_reports_to_all_users
from telegram_notifier import send_telegram_message
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ITALY_TZ = pytz.timezone('Europe/Rome')


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
            logger.error(f"Errore parsing riga {row_num}: {e}", exc_info=True)
            continue
    
    return wines


@router.post("/insert-inventory")
async def admin_insert_inventory(
    user_id: int = Form(...),
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
        user_id: ID utente
        business_name: Nome business
        file: File CSV inventario pulito
        mode: "add" (aggiunge) o "replace" (sostituisce)
    
    Returns:
        Dict con risultato inserimento
    """
    correlation_id = f"admin_insert_{user_id}_{business_name}"
    
    try:
        log_with_context(
            "info",
            f"[ADMIN_INSERT] Inizio inserimento inventario per user_id={user_id}/{business_name}",
            telegram_id=user_id,  # Mantenuto per retrocompatibilità log
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
            telegram_id=user_id,  # Mantenuto per retrocompatibilità log
            correlation_id=correlation_id
        )
        
        async for db in get_db():
            # Trova utente per user_id
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(
                    status_code=404,
                    detail=f"Utente user_id={user_id} non trovato"
                )
            
            # Crea/verifica tabelle usando user_id
            user_tables = await ensure_user_tables(db, user_id, business_name)
            table_inventario = user_tables["inventario"]
            
            log_with_context(
                "info",
                f"[ADMIN_INSERT] Tabelle utente verificate/create: {list(user_tables.keys())}",
                telegram_id=user_id,  # Mantenuto per retrocompatibilità log
                correlation_id=correlation_id
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


@router.post("/trigger-daily-report")
async def admin_trigger_daily_report(
    telegram_id: Optional[int] = None,
    report_date: Optional[str] = None,  # Formato: YYYY-MM-DD, default: oggi
):
    """
    Endpoint admin per triggerare manualmente il report giornaliero.
    
    Args:
        telegram_id: ID Telegram utente specifico (opzionale). Se None, invia a tutti.
        report_date: Data del report in formato YYYY-MM-DD (opzionale). Default: oggi.
    
    Returns:
        Dict con risultato invio report
    """
    try:
        # Parse data report (default: oggi)
        if report_date:
            try:
                report_datetime = datetime.strptime(report_date, "%Y-%m-%d")
                report_datetime = ITALY_TZ.localize(report_datetime.replace(hour=0, minute=0, second=0, microsecond=0))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato data non valido: {report_date}. Usa formato YYYY-MM-DD"
                )
        else:
            # Default: oggi (non ieri, perché l'utente vuole il report per la data corrente)
            now_italy = datetime.now(ITALY_TZ)
            # Mantieni timezone awareness quando imposti a mezzanotte
            report_datetime = ITALY_TZ.localize(
                now_italy.replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
            )
        
        report_date_str = report_datetime.strftime("%Y-%m-%d")
        
        logger.info(
            f"[ADMIN_REPORT] Trigger manuale report per data: {report_date_str}, "
            f"telegram_id: {telegram_id if telegram_id else 'TUTTI'}"
        )
        
        sent_count = 0
        skipped_count = 0
        error_count = 0
        errors = []
        
        if telegram_id:
            # Invia a un utente specifico
            async for db in get_db():
                stmt = select(User).where(User.telegram_id == telegram_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Utente {telegram_id} non trovato"
                    )
                
                if not user.business_name:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Utente {telegram_id} senza business_name"
                    )
                
                # Genera report
                report = await generate_daily_movements_report(
                    telegram_id=user.telegram_id,
                    business_name=user.business_name,
                    report_date=report_datetime
                )
                
                if not report:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Errore generazione report per utente {telegram_id}"
                    )
                
                # Invia report via Telegram
                success = await send_telegram_message(
                    telegram_id=user.telegram_id,
                    message=report,
                    parse_mode="Markdown"
                )
                
                if success:
                    sent_count = 1
                    logger.info(
                        f"[ADMIN_REPORT] Report inviato a {telegram_id}/{user.business_name}"
                    )
                else:
                    error_count = 1
                    errors.append(f"Errore invio a {telegram_id}")
                    logger.warning(f"[ADMIN_REPORT] Errore invio report a {telegram_id}", exc_info=True)
        else:
            # Invia a tutti gli utenti
            async for db in get_db():
                stmt = select(User).where(User.onboarding_completed == True)
                result = await db.execute(stmt)
                users = result.scalars().all()
                
                logger.info(f"[ADMIN_REPORT] Trovati {len(users)} utenti attivi")
                
                for user in users:
                    try:
                        if not user.business_name:
                            logger.warning(
                                f"[ADMIN_REPORT] Utente {user.telegram_id} senza business_name, skip"
                            )
                            skipped_count += 1
                            continue
                        
                        # Genera report
                        report = await generate_daily_movements_report(
                            telegram_id=user.telegram_id,
                            business_name=user.business_name,
                            report_date=report_datetime
                        )
                        
                        if not report:
                            logger.warning(
                                f"[ADMIN_REPORT] Errore generazione report per {user.telegram_id}, skip"
                            )
                            skipped_count += 1
                            continue
                        
                        # Invia report via Telegram
                        success = await send_telegram_message(
                            telegram_id=user.telegram_id,
                            message=report,
                            parse_mode="Markdown"
                        )
                        
                        if success:
                            sent_count += 1
                            logger.info(
                                f"[ADMIN_REPORT] Report inviato a {user.telegram_id}/{user.business_name}"
                            )
                        else:
                            error_count += 1
                            errors.append(f"Errore invio a {user.telegram_id}")
                            logger.warning(
                                f"[ADMIN_REPORT] Errore invio report a {user.telegram_id}"
                            )
                        
                        # Piccola pausa tra invii per evitare rate limiting
                        import asyncio
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        error_count += 1
                        errors.append(f"Errore processamento {user.telegram_id}: {str(e)[:100]}")
                        logger.error(
                            f"[ADMIN_REPORT] Errore processamento utente {user.telegram_id}: {e}",
                            exc_info=True
                        )
                        continue
        
        return {
            "status": "success",
            "report_date": report_date_str,
            "telegram_id": telegram_id,
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "errors": errors[:10]  # Max 10 errori nel response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[ADMIN_REPORT] Errore trigger report: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Errore trigger report: {str(e)}"
        )


class InsertInventoryJSONRequest(BaseModel):
    """Request model per inserimento inventario via JSON (bypass multipart)"""
    user_id: Optional[int] = None  # Opzionale: se None, crea nuovo utente con solo business_name
    business_name: str
    file_content_base64: str  # CSV content in base64
    mode: str = "add"  # "add" o "replace"
    source: str = "admin_bot"  # Fonte: "admin_bot", "admin_script", etc.


@router.post("/insert-inventory-json")
async def admin_insert_inventory_json(request: InsertInventoryJSONRequest):
    """
    Endpoint alternativo per inserire inventario via JSON (bypass problemi multipart).
    
    Questo endpoint accetta il contenuto CSV come stringa base64 invece di multipart form.
    Utile quando ci sono problemi con l'ordine dei campi multipart.
    """
    correlation_id = f"admin_insert_{request.user_id or 'new_user'}_{request.business_name}"
    
    try:
        log_with_context(
            "info",
            f"[ADMIN_INSERT_JSON] Inizio inserimento inventario per user_id={request.user_id or 'N/A'}/{request.business_name}",
            telegram_id=request.user_id,  # Mantenuto per retrocompatibilità log
            correlation_id=correlation_id
        )
        
        # Decodifica file CSV da base64
        try:
            file_content = base64.b64decode(request.file_content_base64)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Errore decodifica base64: {str(e)}"
            )
        
        # Parse CSV
        wines = parse_csv_content(file_content)
        
        if not wines:
            raise HTTPException(
                status_code=400,
                detail="Nessun vino trovato nel CSV. Verifica formato file."
            )
        
        log_with_context(
            "info",
            f"[ADMIN_INSERT_JSON] Trovati {len(wines)} vini nel CSV",
            telegram_id=request.user_id,  # Mantenuto per retrocompatibilità log
            correlation_id=correlation_id
        )
        
        # Usa la stessa logica dell'endpoint multipart
        async for db in get_db():
            # Crea/verifica utente e tabelle (crea automaticamente se non esistono)
            log_with_context(
                "info",
                f"[ADMIN_INSERT_JSON] Creazione/verifica tabelle per utente user_id={request.user_id or 'N/A'}/{request.business_name}",
                telegram_id=request.user_id,  # Mantenuto per retrocompatibilità log
                correlation_id=correlation_id
            )
            
            # Se user_id è presente, usa quello
            # Altrimenti, crea/ottieni utente solo con business_name
            if request.user_id is not None:
                # Trova utente per user_id
                stmt = select(User).where(User.id == request.user_id)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Utente user_id={request.user_id} non trovato"
                    )
                
                # Crea tabelle usando user_id
                user_tables = await ensure_user_tables(db, request.user_id, request.business_name)
            else:
                # Crea/ottieni utente solo con business_name
                user = await find_or_create_user_by_business_name(db, request.business_name)
                # Crea tabelle usando user_id
                user_tables = await ensure_user_tables(db, user.id, request.business_name)
            
            table_inventario = user_tables["inventario"]
            
            log_with_context(
                "info",
                f"[ADMIN_INSERT_JSON] Tabelle utente verificate/create: {list(user_tables.keys())}",
                telegram_id=request.telegram_id,
                correlation_id=correlation_id
            )
            
            # Se mode='replace', elimina tutti i vini esistenti
            if request.mode == "replace":
                delete_stmt = sql_text(f"""
                    DELETE FROM {table_inventario}
                    WHERE user_id = :user_id
                """)
                await db.execute(delete_stmt, {"user_id": user.id})
                await db.commit()
                log_with_context(
                    "info",
                    f"[ADMIN_INSERT_JSON] Inventario esistente eliminato (mode=replace)",
                    telegram_id=request.telegram_id,
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
                f"[ADMIN_INSERT_JSON] Inserimento completato: {saved_count} salvati, {error_count} errori",
                telegram_id=user.id,  # Mantenuto per retrocompatibilità log
                correlation_id=correlation_id
            )
            
            return {
                "status": "success",
                "user_id": user.id,
                "business_name": request.business_name,
                "mode": request.mode,
                "source": request.source,
                "total_wines": len(wines),
                "saved_wines": saved_count,  # Compatibile con endpoint multipart
                "error_count": error_count,
                "tables_created": list(user_tables.keys())
            }
            
    except HTTPException:
        raise
    except Exception as e:
        log_with_context(
            "error",
            f"[ADMIN_INSERT_JSON] Errore inserimento: {e}",
            telegram_id=request.telegram_id,
            correlation_id=correlation_id,
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Errore inserimento inventario: {str(e)}"
        )


@router.post("/update-wine-field")
async def update_wine_field(
    user_id: int = Form(...),
    business_name: str = Form(...),
    wine_id: int = Form(...),
    field: str = Form(...),
    value: str = Form(...)
):
    """
    Aggiorna un singolo campo per un vino dell'inventario utente.
    Campi supportati: producer, supplier, vintage, grape_variety, classification, 
    selling_price, cost_price, alcohol_content, description, notes, region, country, wine_type
    """
    try:
        allowed_fields = {
            'producer': 'producer',
            'supplier': 'supplier',
            'vintage': 'vintage',
            'grape_variety': 'grape_variety',
            'classification': 'classification',
            'selling_price': 'selling_price',
            'cost_price': 'cost_price',
            'alcohol_content': 'alcohol_content',
            'description': 'description',
            'notes': 'notes',
            'region': 'region',
            'country': 'country',
            'wine_type': 'wine_type',
        }
        
        if field not in allowed_fields:
            raise HTTPException(
                status_code=400, 
                detail=f"Campo non consentito: {field}. Campi supportati: {', '.join(allowed_fields.keys())}"
            )
        
        # Normalizza tipi per alcuni campi
        def cast_value(f: str, v: str):
            if f == 'vintage':
                try:
                    parsed = int(v)
                    if parsed < 1800 or parsed > 2100:
                        raise HTTPException(status_code=400, detail=f"Anno non valido: {parsed}")
                    return parsed
                except (ValueError, TypeError):
                    raise HTTPException(status_code=400, detail=f"Anno non valido per {f}: '{v}'")
            if f in ('selling_price', 'cost_price', 'alcohol_content'):
                try:
                    parsed = float(str(v).replace(',', '.'))
                    if f == 'alcohol_content' and (parsed < 0 or parsed > 100):
                        raise HTTPException(status_code=400, detail=f"Gradazione alcolica non valida: {parsed}%")
                    if f in ('selling_price', 'cost_price') and parsed < 0:
                        raise HTTPException(status_code=400, detail=f"Prezzo non può essere negativo: {parsed}")
                    return parsed
                except (ValueError, TypeError):
                    raise HTTPException(status_code=400, detail=f"Numero non valido per {f}: '{v}'")
            if f == 'wine_type':
                # Validazione enum per tipo vino
                valid_types = ['Rosso', 'Bianco', 'Rosato', 'Spumante', 'Altro']
                v_normalized = str(v).strip()
                if v_normalized and v_normalized not in valid_types:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Tipo vino non valido: '{v_normalized}'. Tipi validi: {', '.join(valid_types)}"
                    )
                return v_normalized if v_normalized else None
            # Per stringhe (region, country, etc.), rimuovi spazi eccessivi
            return str(v).strip() if v else None
        
        column = allowed_fields[field]
        new_value = cast_value(field, value)
        
        async for db in get_db():
            # Verifica utente
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail=f"Utente user_id={user_id} non trovato")
            
            # Assicura esistenza tabelle
            user_tables = await ensure_user_tables(db, user_id, business_name)
            table_inventario = user_tables["inventario"]
            
            # Verifica che il vino esista
            check_wine = sql_text(f"""
                SELECT id FROM {table_inventario}
                WHERE id = :wine_id AND user_id = :user_id
            """)
            wine_check = await db.execute(check_wine, {"wine_id": wine_id, "user_id": user_id})
            if not wine_check.fetchone():
                raise HTTPException(status_code=404, detail=f"Vino con id {wine_id} non trovato")
            
            # Aggiorna campo
            update_stmt = sql_text(f"""
                UPDATE {table_inventario}
                SET {column} = :val, updated_at = CURRENT_TIMESTAMP
                WHERE id = :wine_id AND user_id = :user_id
                RETURNING id
            """)
            result = await db.execute(update_stmt, {"val": new_value, "wine_id": wine_id, "user_id": user_id})
            updated = result.scalar_one_or_none()
            
            if not updated:
                await db.rollback()
                raise HTTPException(status_code=404, detail="Vino non trovato dopo aggiornamento")
            
            await db.commit()
            
            log_with_context(
                "info",
                f"[UPDATE_WINE_FIELD] Campo aggiornato: {field} = {new_value} per wine_id={wine_id}",
                telegram_id=user_id  # Mantenuto per retrocompatibilità log
            )
            
            return {
                "status": "success",
                "wine_id": wine_id,
                "field": field,
                "value": new_value,
                "message": f"Campo {field} aggiornato con successo"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPDATE_WINE_FIELD] Errore aggiornamento campo vino: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno durante aggiornamento: {str(e)}"
        )


@router.post("/update-wine-field-with-movement")
async def update_wine_field_with_movement(
    user_id: int = Form(...),
    business_name: str = Form(...),
    wine_id: int = Form(...),
    field: str = Form(...),
    new_value: int = Form(...)
):
    """
    Aggiorna campo quantity creando automaticamente un movimento nel log.
    Mantiene il flusso di tracciabilità come se fosse fatto in chat.
    
    Args:
        user_id: ID utente
        business_name: Nome business
        wine_id: ID vino da aggiornare
        field: Deve essere 'quantity'
        new_value: Nuova quantità (intero >= 0)
    
    Returns:
        Dict con status, wine_id, movement_type, quantity_change, etc.
    """
    try:
        # Validazione campo
        if field != 'quantity':
            raise HTTPException(
                status_code=400,
                detail=f"Questo endpoint supporta solo field='quantity'. Ricevuto: '{field}'"
            )
        
        # Validazione valore
        if not isinstance(new_value, int) or new_value < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Quantità deve essere un intero >= 0. Ricevuto: {new_value}"
            )
        
        async for db in get_db():
            # Verifica utente
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail=f"Utente user_id={user_id} non trovato")
            
            # Assicura esistenza tabelle
            user_tables = await ensure_user_tables(db, user_id, business_name)
            table_inventario = user_tables["inventario"]
            table_consumi = user_tables["consumi"]
            
            # Recupera vino con quantity_before
            get_wine = sql_text(f"""
                SELECT id, name, producer, quantity
                FROM {table_inventario}
                WHERE id = :wine_id AND user_id = :user_id
            """)
            wine_result = await db.execute(get_wine, {"wine_id": wine_id, "user_id": user_id})
            wine_row = wine_result.fetchone()
            
            if not wine_row:
                raise HTTPException(status_code=404, detail=f"Vino con id {wine_id} non trovato")
            
            wine_id_db = wine_row[0]
            wine_name_db = wine_row[1]  # name
            wine_producer = wine_row[2] if len(wine_row) > 2 else None  # producer
            quantity_before = wine_row[3] if len(wine_row) > 3 else 0  # quantity
            
            logger.info(
                f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Vino trovato: wine_id={wine_id}, "
                f"wine_name='{wine_name_db}', quantity_before={quantity_before}, new_value={new_value}"
            )
            
            # Calcola differenza
            quantity_change = new_value - quantity_before
            
            # Se non c'è cambiamento, aggiorna solo quantity senza movimento
            if quantity_change == 0:
                update_stmt = sql_text(f"""
                    UPDATE {table_inventario}
                    SET quantity = :val, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :wine_id AND user_id = :user_id
                    RETURNING id
                """)
                result = await db.execute(update_stmt, {"val": new_value, "wine_id": wine_id, "user_id": user.id})
                updated = result.scalar_one_or_none()
                
                if not updated:
                    await db.rollback()
                    raise HTTPException(status_code=404, detail="Vino non trovato dopo aggiornamento")
                
                await db.commit()
                
                log_with_context(
                    "info",
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Quantità aggiornata senza movimento: {quantity_before} → {new_value} per wine_id={wine_id}",
                    telegram_id=user_id  # Mantenuto per retrocompatibilità log
                )
                
                return {
                    "status": "success",
                    "wine_id": wine_id,
                    "field": field,
                    "value": new_value,
                    "quantity_before": quantity_before,
                    "quantity_after": new_value,
                    "movement_created": False,
                    "message": f"Quantità aggiornata (nessun movimento necessario: quantità invariata)"
                }
            
            # Determina movement_type
            if quantity_change > 0:
                movement_type = 'rifornimento'
                logger.info(
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Movimento tipo: {movement_type}, "
                    f"quantity_change={quantity_change}"
                )
            else:
                movement_type = 'consumo'
                logger.info(
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Movimento tipo: {movement_type}, "
                    f"quantity_change={quantity_change} (valore assoluto: {abs(quantity_change)})"
                )
                # Validazione quantità sufficiente per consumo
                if quantity_before < abs(quantity_change):
                    logger.warning(
                        f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Quantità insufficiente per consumo: "
                        f"disponibili={quantity_before}, richieste={new_value}, differenza={abs(quantity_change)}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Quantità insufficiente: disponibili {quantity_before}, richieste {new_value}"
                    )
            
            quantity_after = new_value
            
            # Calcola quantity_change per il log (positivo per rifornimento, negativo per consumo)
            movement_quantity_change = abs(quantity_change) if movement_type == 'rifornimento' else -abs(quantity_change)
            
            try:
                # UPDATE quantity nella tabella inventario
                update_stmt = sql_text(f"""
                    UPDATE {table_inventario}
                    SET quantity = :val, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :wine_id AND user_id = :user_id
                    RETURNING id
                """)
                result = await db.execute(update_stmt, {"val": new_value, "wine_id": wine_id, "user_id": user_id})
                updated = result.scalar_one_or_none()
                
                if not updated:
                    await db.rollback()
                    raise HTTPException(status_code=404, detail="Vino non trovato dopo aggiornamento")
                
                logger.info(
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] UPDATE inventario eseguito - "
                    f"quantity: {quantity_before} → {quantity_after} per wine_id={wine_id}"
                )
                
                # INSERT movimento nella tabella Consumi e rifornimenti
                insert_mov = sql_text(f"""
                    INSERT INTO {table_consumi}
                        (user_id, wine_name, wine_producer, movement_type, quantity_change, quantity_before, quantity_after, movement_date)
                    VALUES (:user_id, :wine_name, :wine_producer, :movement_type, :quantity_change, :quantity_before, :quantity_after, CURRENT_TIMESTAMP)
                """)
                await db.execute(insert_mov, {
                    "user_id": user_id,
                    "wine_name": wine_name_db,
                    "wine_producer": wine_producer,
                    "movement_type": movement_type,
                    "quantity_change": movement_quantity_change,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after
                })
                
                logger.info(
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] INSERT log movimento eseguito - "
                    f"movement_type={movement_type}, quantity_change={movement_quantity_change}"
                )
                
                await db.commit()
                
                log_with_context(
                    "info",
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Campo quantity aggiornato con movimento: {quantity_before} → {quantity_after} "
                    f"({movement_type} {abs(quantity_change)}) per wine_id={wine_id}",
                    telegram_id=user_id  # Mantenuto per retrocompatibilità log
                )
                
                return {
                    "status": "success",
                    "wine_id": wine_id,
                    "field": field,
                    "value": new_value,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after,
                    "movement_type": movement_type,
                    "quantity_change": movement_quantity_change,
                    "movement_created": True,
                    "message": f"Quantità aggiornata e movimento {movement_type} registrato"
                }
                
            except HTTPException:
                await db.rollback()
                raise
            except Exception as te:
                await db.rollback()
                logger.error(
                    f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Errore transazione: {te}",
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Errore durante aggiornamento quantità: {str(te)}"
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPDATE_WINE_FIELD_WITH_MOVEMENT] Errore aggiornamento quantità con movimento: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno durante aggiornamento: {str(e)}"
        )


@router.post("/add-wine")
async def add_wine(
    user_id: int = Form(...),
    business_name: str = Form(...),
    name: str = Form(...),
    producer: Optional[str] = Form(None),
    quantity: Optional[int] = Form(None),
    selling_price: Optional[float] = Form(None),
    cost_price: Optional[float] = Form(None),
    vintage: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    wine_type: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    grape_variety: Optional[str] = Form(None),
    classification: Optional[str] = Form(None),
    alcohol_content: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
):
    """
    Aggiunge un nuovo vino all'inventario.
    
    Args:
        user_id: ID utente
        business_name: Nome business
        name: Nome vino (obbligatorio)
        Altri campi: opzionali
    
    Returns:
        Dict con status, wine_id, etc.
    """
    try:
        # Validazione nome
        if not name or not name.strip():
            raise HTTPException(
                status_code=400,
                detail="Il nome del vino è obbligatorio"
            )
        
        async for db in get_db():
            # Verifica utente
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail=f"Utente user_id={user_id} non trovato")
            
            # Assicura esistenza tabelle
            user_tables = await ensure_user_tables(db, user_id, business_name)
            table_inventario = user_tables["inventario"]
            
            # Prepara dati vino
            wine_data = {
                "user_id": user.id,
                "name": name.strip(),
                "producer": producer.strip() if producer else None,
                "supplier": supplier.strip() if supplier else None,
                "vintage": _parse_int(vintage) if vintage else None,
                "grape_variety": grape_variety.strip() if grape_variety else None,
                "region": region.strip() if region else None,
                "country": country.strip() if country else None,
                "wine_type": wine_type.strip() if wine_type else None,
                "classification": classification.strip() if classification else None,
                "quantity": quantity if quantity is not None else 0,
                "min_quantity": 0,
                "cost_price": _parse_float(cost_price) if cost_price else None,
                "selling_price": _parse_float(selling_price) if selling_price else None,
                "alcohol_content": _parse_float(alcohol_content) if alcohol_content else None,
                "description": description.strip() if description else None,
                "notes": notes.strip() if notes else None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Validazione wine_type se fornito
            if wine_data["wine_type"]:
                allowed_types = ['Rosso', 'Bianco', 'Rosato', 'Spumante', 'Altro']
                if wine_data["wine_type"] not in allowed_types:
                    logger.warning(
                        f"[ADD_WINE] wine_type '{wine_data['wine_type']}' non valido, "
                        f"usando 'Altro'"
                    )
                    wine_data["wine_type"] = "Altro"
            
            # Inserisci vino
            insert_stmt = sql_text(f"""
                INSERT INTO {table_inventario}
                    (user_id, name, producer, supplier, vintage, grape_variety, region, 
                     country, wine_type, classification, quantity, min_quantity, 
                     cost_price, selling_price, alcohol_content, description, notes, 
                     created_at, updated_at)
                VALUES 
                    (:user_id, :name, :producer, :supplier, :vintage, :grape_variety, :region,
                     :country, :wine_type, :classification, :quantity, :min_quantity,
                     :cost_price, :selling_price, :alcohol_content, :description, :notes,
                     :created_at, :updated_at)
                RETURNING id
            """)
            
            result = await db.execute(insert_stmt, wine_data)
            wine_id = result.scalar_one()
            
            # Assicura che wine_id sia un intero
            if wine_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="Errore: wine_id non restituito dopo inserimento"
                )
            
            wine_id = int(wine_id)  # Assicura che sia un intero
            
            await db.commit()
            
            log_with_context(
                "info",
                f"[ADD_WINE] Vino aggiunto: wine_id={wine_id}, name='{name}', "
                f"user_id={user_id}, business_name={business_name}",
                telegram_id=user_id  # Mantenuto per retrocompatibilità log
            )
            
            return {
                "status": "success",
                "wine_id": wine_id,
                "message": f"Vino '{name}' aggiunto con successo"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADD_WINE] Errore aggiunta vino: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno durante aggiunta vino: {str(e)}"
        )

