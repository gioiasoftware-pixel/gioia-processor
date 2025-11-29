"""
Router per elaborazione inventario (ingest pipeline).

Endpoint:
- POST /process-inventory: Elabora file inventario usando la nuova pipeline.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, batch_insert_wines, ensure_user_tables, User
from core.job_manager import create_job, get_job_by_client_msg_id, update_job_status
from core.logger import log_with_context
from ingest.pipeline import process_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


async def process_inventory_background(
    job_id: str,
    telegram_id: int,
    business_name: str,
    file_type: str,
    file_content: bytes,
    file_name: str,
    correlation_id: Optional[str] = None,
    mode: str = "add",  # "add" o "replace"
    dry_run: bool = False  # Se True, solo anteprima senza salvare
):
    """
    Elabora inventario in background usando la nuova pipeline.
    
    Conforme a "Update processor.md" - Background processing con nuova pipeline.
    
    Args:
        job_id: ID job elaborazione
        telegram_id: ID Telegram utente
        business_name: Nome business
        file_type: Tipo file (csv, excel, xlsx, xls, image, jpg, jpeg, png, pdf)
        file_content: Contenuto file (bytes)
        file_name: Nome file
        correlation_id: ID correlazione per logging
        mode: Modalità salvataggio ("add" o "replace")
        dry_run: Se True, solo anteprima senza salvare
    """
    start_time = datetime.utcnow()
    
    try:
        async for db in get_db():
            # Aggiorna job status a processing (started_at gestito automaticamente)
            await update_job_status(
                db, job_id, 
                status='processing'
            )
            
            log_with_context(
                "info",
                f"Job {job_id}: Started processing for telegram_id: {telegram_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            # Determina estensione file
            ext = file_type.lower()
            if ext in ["excel", "xlsx", "xls"]:
                ext = "xlsx"
            elif ext in ["image", "jpg", "jpeg", "png"]:
                ext = "jpg" if ext in ["image", "jpg", "jpeg"] else "png"
            
            # Processa file con nuova pipeline
            wines_data = []
            processing_method = "unknown"
            metrics = {}
            stage_used = "unknown"
            
            try:
                wines_data, metrics, decision, stage_used = await process_file(
                    file_content=file_content,
                    file_name=file_name,
                    ext=ext,
                    telegram_id=telegram_id,
                    business_name=business_name,
                    correlation_id=correlation_id
                )
                
                # Determina processing_method da stage_used
                if stage_used == 'csv_excel_parse':
                    processing_method = "csv_excel_parse"
                elif stage_used == 'ia_targeted':
                    processing_method = "ia_targeted"
                elif stage_used == 'llm_mode':
                    processing_method = "llm_mode"
                elif stage_used == 'ocr':
                    processing_method = "ocr_llm"
                else:
                    processing_method = stage_used
                
                logger.info(
                    f"Job {job_id}: Extracted {len(wines_data)} wines from {file_type} file "
                    f"(stage: {stage_used}, decision: {decision})"
                )
                
                # Aggiorna progress (mantieni status='processing')
                await update_job_status(
                    db, job_id,
                    status='processing',  # Mantieni status processing
                    total_wines=len(wines_data),
                    processed_wines=len(wines_data),
                    processing_method=processing_method
                )
                
                # Se decision='error' o wines_data vuoto, gestisci errore
                if decision == 'error' or len(wines_data) == 0:
                    error_msg = f"Pipeline failed: decision={decision}, wines_count={len(wines_data)}"
                    logger.error(f"Job {job_id}: {error_msg}")
                    await update_job_status(
                        db, job_id,
                        status='error',
                        error_message=error_msg
                    )
                    
                    # Notifica admin per errore processing
                    try:
                        from admin_notifications import enqueue_admin_notification
                        
                        await enqueue_admin_notification(
                            event_type="error",
                            telegram_id=telegram_id,
                            payload={
                                "business_name": business_name,
                                "error_type": "processing_error",
                                "error_message": error_msg,
                                "error_code": "PIPELINE_ERROR",
                                "component": "gioia-processor",
                                "file_type": file_type,
                                "file_size_bytes": len(file_content) if file_content else 0,
                                "stage_used": stage_used
                            },
                            correlation_id=correlation_id
                        )
                    except Exception as notif_error:
                        logger.warning(f"Errore invio notifica admin: {notif_error}")
                    
                    return
                
                # Se dry-run, non salvare nel database
                if dry_run:
                    logger.info(f"Job {job_id}: Dry-run mode - skipping database save")
                    processing_time = (datetime.utcnow() - start_time).total_seconds()
                    
                    result_data = {
                        "status": "preview",
                        "wines_count": len(wines_data),
                        "metrics": metrics,
                        "stage_used": stage_used,
                        "processing_method": processing_method,
                        "mode": mode,
                        "dry_run": True,
                        "message": f"Anteprima: {len(wines_data)} vini estratti (non salvati)",
                        "processing_time_seconds": round(processing_time, 2)
                    }
                    
                    await update_job_status(
                        db, job_id,
                        status='completed',
                        result_data=result_data
                    )
                    return
                
                # Salva nel database usando batch_insert_wines
                saved_count = 0
                error_count = 0
                warnings_log = []
                errors_log = []
                
                try:
                    # Assicura che tabelle esistano
                    user_tables = await ensure_user_tables(db, telegram_id, business_name)
                    table_inventario = user_tables["inventario"]
                    
                    # Trova utente per user_id
                    stmt = select(User).where(User.telegram_id == telegram_id)
                    result = await db.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        # Crea nuovo utente se non esiste
                        user = User(
                            telegram_id=telegram_id,
                            business_name=business_name,
                            onboarding_completed=True
                        )
                        db.add(user)
                        await db.flush()
                    
                    # Se mode='replace', elimina tutti i vini esistenti
                    if mode == "replace":
                        from sqlalchemy import text as sql_text
                        delete_stmt = sql_text(f"""
                            DELETE FROM {table_inventario}
                            WHERE user_id = :user_id
                        """)
                        await db.execute(delete_stmt, {"user_id": user.id})
                        await db.commit()
                        logger.info(f"Job {job_id}: Replaced mode - cleared existing inventory")
                    
                    # Batch insert vini
                    saved_count, error_count = await batch_insert_wines(
                        db, table_inventario, wines_data, user_id=user.id
                    )
                    
                    if error_count > 0:
                        errors_log.append(f"{error_count} vini non salvati per errori")
                    
                    logger.info(
                        f"Job {job_id}: Saved {saved_count}/{len(wines_data)} wines "
                        f"(errors: {error_count})"
                    )
                    
                except Exception as db_error:
                    logger.error(f"Job {job_id}: Database error: {db_error}", exc_info=True)
                    await update_job_status(
                        db, job_id,
                        status='error',
                        error_message=f"Database error: {str(db_error)}"
                    )
                    
                    # Notifica admin per errore database
                    try:
                        from admin_notifications import enqueue_admin_notification
                        
                        await enqueue_admin_notification(
                            event_type="error",
                            telegram_id=telegram_id,
                            payload={
                                "business_name": business_name,
                                "error_type": "database_error",
                                "error_message": str(db_error),
                                "error_code": "DATABASE_ERROR",
                                "component": "gioia-processor",
                                "file_type": file_type
                            },
                            correlation_id=correlation_id
                        )
                    except Exception as notif_error:
                        logger.warning(f"Errore invio notifica admin: {notif_error}")
                    
                    return
                
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Prepara risultato
                ai_enabled = "yes" if os.getenv("OPENAI_API_KEY") else "no"
                
                result_data = {
                    "status": "success",
                    "total_wines": len(wines_data),
                    "saved_wines": saved_count,
                    "error_count": error_count,
                    "business_name": business_name,
                    "telegram_id": telegram_id,
                    "ai_enhanced": ai_enabled,
                    "processing_method": processing_method,
                    "stage_used": stage_used,
                    "metrics": metrics,
                    "processing_time_seconds": round(processing_time, 2),
                    "file_type": file_type,
                    "file_size_bytes": len(file_content)
                }
                
                # Messaggi condizionali
                if error_count > 0:
                    result_data["errors"] = errors_log[:10] if errors_log else []
                    result_data["message"] = (
                        f"⚠️ Salvati {saved_count} vini su {len(wines_data)}. "
                        f"{error_count} errori."
                    )
                else:
                    result_data["message"] = (
                        f"✅ Salvati {saved_count} vini su {len(wines_data)} senza errori."
                    )
                
                # Aggiorna job come completato (completed_at gestito automaticamente)
                await update_job_status(
                    db, job_id,
                    status='completed',
                    saved_wines=saved_count,
                    error_count=error_count,
                    result_data=result_data
                )
                
                logger.info(f"Job {job_id}: Completed successfully")
                
                # Notifica admin per inventario caricato
                try:
                    from admin_notifications import enqueue_admin_notification
                    
                    await enqueue_admin_notification(
                        event_type="inventory_uploaded",
                        telegram_id=telegram_id,
                        payload={
                            "business_name": business_name,
                            "file_type": file_type,
                            "file_size_bytes": len(file_content),
                            "wines_processed": len(wines_data),
                            "wines_saved": saved_count,
                            "errors_count": error_count,
                            "processing_duration_seconds": round(processing_time, 2),
                            "processing_method": processing_method,
                            "stage_used": stage_used
                        },
                        correlation_id=correlation_id
                    )
                except Exception as notif_error:
                    logger.warning(f"Errore invio notifica admin: {notif_error}")
                
                # ✅ POST-PROCESSING: Normalizza inventario salvato in background
                # Esegue dopo che il job è marcato come completed, non blocca il flusso
                async def run_post_processing():
                    """Task background per normalizzazione post-processing"""
                    db_session = None
                    try:
                        logger.info(
                            f"[POST_PROCESSING] Job {job_id}: Avvio normalizzazione "
                            f"in background per {telegram_id}/{business_name}"
                        )
                        
                        # Usa una nuova sessione per il post-processing
                        # IMPORTANTE: Non usare async for, usa direttamente AsyncSessionLocal per mantenere la sessione aperta
                        from core.database import AsyncSessionLocal
                        from post_processing import normalize_saved_inventory
                        
                        async with AsyncSessionLocal() as db_session:
                            stats = await normalize_saved_inventory(
                                session=db_session,
                                telegram_id=telegram_id,
                                business_name=business_name,
                                job_id=job_id
                            )
                            
                            # Commit finale esplicito per assicurarsi che tutte le modifiche siano salvate
                            await db_session.commit()
                            
                            logger.info(
                                f"[POST_PROCESSING] Job {job_id}: Normalizzazione completata - "
                                f"{stats['normalized_count']}/{stats['total_wines']} vini normalizzati, "
                                f"{stats.get('llm_corrections_applied', 0)} correzioni LLM applicate, "
                                f"{stats.get('duplicates_removed', 0)} duplicati rimossi"
                            )
                            
                            # Notifica utente direttamente su Telegram se ci sono duplicati rimossi
                            if stats.get('duplicates_removed', 0) > 0:
                                try:
                                    from telegram_notifier import send_telegram_message
                                    
                                    duplicates_count = stats['duplicates_removed']
                                    total_before = stats['total_wines']
                                    total_after = total_before - duplicates_count
                                    
                                    message = (
                                        f"🔍 **Pulizia inventario completata**\n\n"
                                        f"✅ **{duplicates_count} vini duplicati** rimossi\n"
                                        f"📊 **Inventario aggiornato:**\n"
                                        f"• Prima: {total_before} vini\n"
                                        f"• Dopo: {total_after} vini\n\n"
                                        f"💡 I duplicati erano vini con **tutti i campi identici** (nome, produttore, annata, quantità, prezzo, regione, paese, tipo, classificazione).\n\n"
                                        f"🏢 **{business_name}** inventario ottimizzato!"
                                    )
                                    
                                    success = await send_telegram_message(
                                        telegram_id=telegram_id,
                                        message=message,
                                        parse_mode="Markdown"
                                    )
                                    
                                    if success:
                                        logger.info(
                                            f"[POST_PROCESSING] Job {job_id}: Messaggio Telegram inviato a {telegram_id} "
                                            f"per {duplicates_count} duplicati rimossi"
                                        )
                                    else:
                                        logger.warning(
                                            f"[POST_PROCESSING] Job {job_id}: Errore invio messaggio Telegram "
                                            f"per duplicati rimossi"
                                        )
                                except Exception as notif_error:
                                    logger.warning(
                                        f"[POST_PROCESSING] Errore invio messaggio Telegram per duplicati: {notif_error}",
                                        exc_info=True
                                    )
                    except Exception as post_error:
                        # Non bloccare il flusso principale se post-processing fallisce
                        logger.warning(
                            f"[POST_PROCESSING] Job {job_id}: Errore post-processing "
                            f"(non critico): {post_error}",
                            exc_info=True
                        )
                        # Rollback in caso di errore
                        if db_session:
                            try:
                                await db_session.rollback()
                            except:
                                pass
                
                # ============================================================
                # POST-PROCESSING DISABILITATO per inventari puliti
                # ============================================================
                # Il post-processing (normalizzazione, deduplicazione, validazione LLM)
                # è stato disabilitato perché troppo aggressivo per inventari già puliti.
                # Rimuove vini che non sono realmente duplicati.
                #
                # Per riattivare il post-processing, decommentare le righe seguenti:
                #
                # async def run_post_processing():
                #     """Esegue post-processing in background (non blocca risposta)"""
                #     try:
                #         logger.info(
                #             f"[POST_PROCESSING] Job {job_id}: Avvio normalizzazione "
                #             f"in background per {telegram_id}/{business_name}"
                #         )
                #         from post_processing import normalize_saved_inventory
                #         
                #         stats = await normalize_saved_inventory(
                #             job_id=job_id,
                #             telegram_id=telegram_id,
                #             business_name=business_name
                #         )
                #         
                #         logger.info(
                #             f"[POST_PROCESSING] Job {job_id}: Normalizzazione completata - "
                #             f"{stats.get('normalized_count', 0)}/{stats.get('total_rows', 0)} vini normalizzati, "
                #             f"{stats.get('llm_corrections_applied', 0)} correzioni LLM applicate, "
                #             f"{stats.get('duplicates_removed', 0)} duplicati rimossi"
                #         )
                #         
                #         # Notifica utente se ci sono duplicati rimossi
                #         duplicates_count = stats.get('duplicates_removed', 0)
                #         if duplicates_count > 0:
                #             try:
                #                 from admin_notifications import enqueue_admin_notification
                #                 
                #                 await enqueue_admin_notification(
                #                     event_type="duplicates_removed",
                #                     telegram_id=telegram_id,
                #                     payload={
                #                         "business_name": business_name,
                #                         "duplicates_count": duplicates_count,
                #                         "job_id": job_id
                #                     }
                #                 )
                #                 
                #                 # Notifica anche direttamente su Telegram se configurato
                #                 try:
                #                     config = get_config()
                #                     if config.telegram_bot_token:
                #                         import httpx
                #                         message = (
                #                             f"ℹ️ **Post-processing completato**\n\n"
                #                             f"📊 **Risultati:**\n"
                #                             f"• {stats.get('normalized_count', 0)} vini normalizzati\n"
                #                             f"• {stats.get('llm_corrections_applied', 0)} correzioni LLM applicate\n"
                #                             f"• {duplicates_count} duplicati rimossi"
                #                         )
                #                         async with httpx.AsyncClient() as client:
                #                             await client.post(
                #                                 f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
                #                                 json={
                #                                     "chat_id": telegram_id,
                #                                     "text": message,
                #                                     "parse_mode": "Markdown"
                #                                 },
                #                                 timeout=10.0
                #                             )
                #                 except Exception as notif_error:
                #                     logger.warning(
                #                         f"[POST_PROCESSING] Errore invio messaggio Telegram per duplicati: {notif_error}",
                #                         exc_info=True
                #                     )
                #             except Exception as notif_error:
                #                 logger.warning(
                #                     f"[POST_PROCESSING] Errore invio messaggio Telegram per duplicati: {notif_error}",
                #                     exc_info=True
                #                 )
                #     except Exception as post_error:
                #         # Non bloccare il flusso principale se post-processing fallisce
                #         logger.warning(
                #             f"[POST_PROCESSING] Job {job_id}: Errore post-processing "
                #             f"(non critico): {post_error}",
                #             exc_info=True
                #         )
                # 
                # # Avvia post-processing in background (non blocca)
                # asyncio.create_task(run_post_processing())
                
                break
                
            except Exception as processing_error:
                logger.error(
                    f"Job {job_id}: Error processing {file_type} file: {processing_error}",
                    exc_info=True
                )
                await update_job_status(
                    db, job_id,
                    status='error',
                    error_message=f"Error processing file: {str(processing_error)}"
                )
                
                # Notifica admin per errore processing
                try:
                    from admin_notifications import enqueue_admin_notification
                    
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "business_name": business_name,
                            "error_type": "processing_error",
                            "error_message": str(processing_error),
                            "error_code": "PROCESSING_ERROR",
                            "component": "gioia-processor",
                            "file_type": file_type,
                            "file_size_bytes": len(file_content) if file_content else 0
                        },
                        correlation_id=correlation_id
                    )
                except Exception as notif_error:
                    logger.warning(f"Errore invio notifica admin: {notif_error}")
                
                return
            
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error: {e}", exc_info=True)
        try:
            async for db in get_db():
                await update_job_status(
                    db, job_id,
                    status='error',
                    error_message=f"Unexpected error: {str(e)}"
                )
                
                # Notifica admin per errore inaspettato
                try:
                    from admin_notifications import enqueue_admin_notification
                    
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "business_name": business_name,
                            "error_type": "unexpected_error",
                            "error_message": str(e),
                            "error_code": "UNEXPECTED_ERROR",
                            "component": "gioia-processor",
                            "job_id": job_id
                        },
                        correlation_id=correlation_id
                    )
                except Exception as notif_error:
                    logger.warning(f"Errore invio notifica admin: {notif_error}")
                
                break
        except:
            pass


@router.post("/process-inventory")
async def process_inventory_endpoint(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file_type: str = Form(...),
    file: UploadFile = File(...),
    client_msg_id: Optional[str] = Form(None),  # Opzionale: per idempotenza
    correlation_id: Optional[str] = Form(None),  # Opzionale: per logging
    mode: str = Form("add"),  # "add" o "replace" - modalità import
    dry_run: bool = Form(False)  # Se True, solo anteprima senza salvare
):
    """
    Crea job di elaborazione inventario e ritorna job_id immediatamente.
    L'elaborazione avviene in background usando la nuova pipeline.
    Supporta idempotenza tramite client_msg_id.
    
    Conforme a "Update processor.md" - Endpoint /process-inventory.
    """
    try:
        log_with_context(
            "info",
            f"Creating job for telegram_id: {telegram_id}, business: {business_name}, type: {file_type}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Validazione input
        if not telegram_id or telegram_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid telegram_id")
        
        if not business_name or len(business_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Business name is required")
        
        supported_types = ["csv", "excel", "xlsx", "xls", "image", "jpg", "jpeg", "png", "pdf"]
        if not file_type or file_type.lower() not in supported_types:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Leggi contenuto file
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        if len(file_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
        
        # IDEMPOTENZA: Controlla se job esiste già con stesso client_msg_id
        if client_msg_id:
            async for db in get_db():
                existing_job = await get_job_by_client_msg_id(db, telegram_id, client_msg_id)
                if existing_job:
                    # Job già esistente: ritorna risultato precedente
                    if existing_job.status == 'completed':
                        log_with_context(
                            "info",
                            f"Job already completed (idempotency): {existing_job.job_id}",
                            telegram_id=telegram_id,
                            correlation_id=correlation_id
                        )
                        return {
                            "status": "completed",
                            "job_id": existing_job.job_id,
                            "message": "Job già elaborato (idempotenza)",
                            "from_cache": True
                        }
                    elif existing_job.status == 'processing':
                        log_with_context(
                            "info",
                            f"Job already processing (idempotency): {existing_job.job_id}",
                            telegram_id=telegram_id,
                            correlation_id=correlation_id
                        )
                        return {
                            "status": "processing",
                            "job_id": existing_job.job_id,
                            "message": "Job già in elaborazione",
                            "from_cache": True
                        }
                    # Se error, permette retry creando nuovo job
                break
        
        # Crea nuovo job
        async for db in get_db():
            job_id = await create_job(
                db,
                telegram_id=telegram_id,
                business_name=business_name,
                file_type=file_type.lower(),
                file_name=file.filename or "inventario",
                file_size_bytes=len(file_content),
                client_msg_id=client_msg_id
            )
            break
        
        log_with_context(
            "info",
            f"Job {job_id} created, starting background processing",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Avvia elaborazione in background
        asyncio.create_task(
            process_inventory_background(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                file_type=file_type,
                file_content=file_content,
                file_name=file.filename or "inventario",
                correlation_id=correlation_id,
                mode=mode,
                dry_run=dry_run
            )
        )
        
        # Ritorna job_id immediatamente
        return {
            "status": "processing",
            "job_id": job_id,
            "message": "Elaborazione avviata. Usa /status/{job_id} per verificare lo stato.",
            "telegram_id": telegram_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

