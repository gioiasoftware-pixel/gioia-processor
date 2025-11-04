from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select
import uvicorn
import os
import asyncio
import json
import uuid
from datetime import datetime
from database import get_db, create_tables, save_inventory_to_db, get_inventory_status, ProcessingJob, ensure_user_tables, get_user_table_name, User
from config import validate_config
from csv_processor import process_csv_file, process_excel_file
from ocr_processor import process_image_ocr
try:
    from pdf_processor import process_pdf_file
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    import logging
    logging.getLogger(__name__).warning("PDF processor not available")
from ai_processor import ai_processor
import logging
from typing import Optional
from logging_config import setup_colored_logging

# Configurazione logging colorato
setup_colored_logging("processor")
logger = logging.getLogger(__name__)

app = FastAPI(title="Gioia Processor", version="1.0.0")

# CORS per comunicazione con bot
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Inizializza database e AI al startup"""
    try:
        # Valida configurazione
        validate_config()
        
        # Crea tabelle database
        await create_tables()
        logger.info("Database tables created successfully")
        
        # Verifica configurazione AI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("OpenAI API key configured - AI features enabled")
        else:
            logger.warning("OpenAI API key not found - AI features disabled")
            
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@app.get("/health")
async def health_check():
    """Health check del servizio con informazioni dettagliate"""
    try:
        # Verifica stato AI
        ai_status = "enabled" if os.getenv("OPENAI_API_KEY") else "disabled"
        
        # Verifica database
        db_status = "connected"
        try:
            async for db in get_db():
                # Test connessione database
                await db.execute(text("SELECT 1"))
                break
        except Exception as e:
            db_status = f"error: {str(e)[:100]}"
            logger.error(f"Database health check failed: {e}")
        
        # Verifica variabili ambiente critiche
        env_status = {
            "DATABASE_URL": "configured" if os.getenv("DATABASE_URL") else "missing",
            "PORT": os.getenv("PORT", "8001"),
            "OPENAI_API_KEY": "configured" if os.getenv("OPENAI_API_KEY") else "missing"
        }
        
        return {
            "status": "healthy", 
            "service": "gioia-processor",
            "version": "1.0.0",
            "ai_enabled": ai_status,
            "database_status": db_status,
            "environment": env_status,
            "features": ["csv_processing", "excel_processing", "ocr", "pdf_processing", "ai_enhancement", "batch_insert", "deduplication", "dry_run"],
            "endpoints": {
                "health": "/health",
                "process": "/process-inventory", 
                "status": "/status/{telegram_id}",
                "ai_status": "/ai/status",
                "ai_test": "/ai/test"
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "gioia-processor", 
            "error": str(e),
            "timestamp": str(datetime.utcnow())
        }

async def process_inventory_background(
    job_id: str,
    telegram_id: int,
    business_name: str,
    file_type: str,
    file_content: bytes,
    file_name: str,
    correlation_id: str = None,
    mode: str = "add",  # "add" o "replace"
    dry_run: bool = False  # Se True, solo anteprima senza salvare
):
    """
    Elabora inventario in background (chiamata asincrona)
    """
    start_time = datetime.utcnow()
    
    try:
        async for db in get_db():
            # Aggiorna job status a processing
            stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()
            
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            await db.commit()
            
            from structured_logging import log_with_context
            
            log_with_context(
                "info",
                f"Job {job_id}: Started processing for telegram_id: {telegram_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            # Processa file in base al tipo
            wines_data = []
            processing_method = ""
            processing_info = {}
            
            try:
                if file_type.lower() == "csv":
                    wines_data, processing_info = await process_csv_file(file_content)
                    processing_method = "csv_ai_enhanced"
                elif file_type.lower() in ["excel", "xlsx", "xls"]:
                    wines_data, processing_info = await process_excel_file(file_content)
                    processing_method = "excel_ai_enhanced"
                elif file_type.lower() in ["image", "jpg", "jpeg", "png"]:
                    wines_data = await process_image_ocr(file_content)
                    processing_method = "ocr_ai_enhanced"
                    processing_info = {"method": "ocr"}
                elif file_type.lower() == "pdf" and PDF_SUPPORT:
                    wines_data = await process_pdf_file(file_content, file_name)
                    processing_method = "pdf_enhanced"
                    processing_info = {"method": "pdf"}
                else:
                    raise ValueError(f"Tipo file non supportato: {file_type}")
                
                logger.info(f"Job {job_id}: Extracted {len(wines_data)} wines from {file_type} file")
                
                # Aggiorna progress
                job.total_wines = len(wines_data)
                job.processed_wines = len(wines_data)
                job.processing_method = processing_method
                # Salva processing_info come JSON nel result_data per dry-run o report
                if processing_info:
                    job.result_data = json.dumps({
                        "preview": True,
                        "wines_count": len(wines_data),
                        "processing_info": processing_info,
                        "mode": mode,
                        "dry_run": dry_run
                    })
                await db.commit()
                
            except Exception as processing_error:
                logger.error(f"Job {job_id}: Error processing {file_type} file: {processing_error}")
                job.status = 'error'
                job.error_message = f"Error processing file: {str(processing_error)}"
                job.completed_at = datetime.utcnow()
                await db.commit()
                
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
            
            # Se dry-run, non salvare nel database
            if dry_run:
                logger.info(f"Job {job_id}: Dry-run mode - skipping database save")
                job.status = 'completed'
                job.result_data = json.dumps({
                    "status": "preview",
                    "wines_count": len(wines_data),
                    "processing_info": processing_info,
                    "mode": mode,
                    "dry_run": True,
                    "message": f"Anteprima: {len(wines_data)} vini estratti (non salvati)"
                })
                job.completed_at = datetime.utcnow()
                await db.commit()
                return
            
            # Salva nel database
            save_result = None
            try:
                save_result = await save_inventory_to_db(db, telegram_id, business_name, wines_data, mode=mode)
            except Exception as db_error:
                logger.error(f"Job {job_id}: Database error: {db_error}")
                job.status = 'error'
                job.error_message = f"Database error: {str(db_error)}"
                job.completed_at = datetime.utcnow()
                await db.commit()
                
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
            
            # Estrai informazioni dal risultato
            if isinstance(save_result, dict):
                inventory_id = save_result.get("user_id")
                saved_count = save_result.get("saved_count", len(wines_data))
                warning_count = save_result.get("warning_count", 0)  # Separato: solo warnings
                error_count = save_result.get("error_count", 0)     # Solo errori critici
                warnings_log = save_result.get("warnings", [])       # Lista warnings
                errors_log = save_result.get("errors", [])           # Lista errori
            else:
                inventory_id = save_result
                saved_count = len(wines_data)
                warning_count = 0
                error_count = 0
                warnings_log = []
                errors_log = []
            
            logger.info(f"Job {job_id}: Successfully processed {saved_count}/{len(wines_data)} wines in {processing_time:.2f}s")
            if warning_count > 0:
                logger.info(f"Job {job_id}: {warning_count} warnings (annate mancanti, dati opzionali)")
            if error_count > 0:
                logger.error(f"Job {job_id}: {error_count} errori critici")
            
            # Prepara risultato
            ai_enabled = "yes" if os.getenv("OPENAI_API_KEY") else "no"
            
            result_data = {
                "status": "success",
                "total_wines": len(wines_data),
                "saved_wines": saved_count,
                "warning_count": warning_count,  # Separato: solo warnings
                "error_count": error_count,      # Solo errori critici
                "business_name": business_name,
                "telegram_id": telegram_id,
                "inventory_id": inventory_id,
                "ai_enhanced": ai_enabled,
                "processing_method": processing_method,
                "processing_time_seconds": round(processing_time, 2),
                "file_type": file_type,
                "file_size_bytes": len(file_content)
            }
            
            # Messaggi condizionali in base a warnings/errori
            if error_count > 0:
                result_data["warnings"] = warnings_log[:10] if warnings_log else []
                result_data["errors"] = errors_log[:10]
                result_data["message"] = f"⚠️ Salvati {saved_count} vini su {len(wines_data)}. {error_count} errori critici, {warning_count} warnings."
            elif warning_count > 0:
                result_data["warnings"] = warnings_log[:10]
                result_data["message"] = f"✅ Salvati {saved_count} vini su {len(wines_data)}. {warning_count} warnings (annate mancanti, dati opzionali - verificare note)."
            else:
                result_data["message"] = f"✅ Salvati {saved_count} vini su {len(wines_data)} senza errori o warnings."
            
            # Aggiorna job come completato
            job.status = 'completed'
            job.saved_wines = saved_count
            job.error_count = error_count  # Solo errori critici (warnings non sono errori)
            job.result_data = json.dumps(result_data)
            job.completed_at = datetime.utcnow()
            await db.commit()
            
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
                        "warnings_count": warning_count,
                        "errors_count": error_count,
                        "processing_duration_seconds": round(processing_time, 2),
                        "processing_method": processing_method
                    },
                    correlation_id=correlation_id
                )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
            break
            
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error: {e}")
        try:
            async for db in get_db():
                stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()
                job.status = 'error'
                job.error_message = f"Unexpected error: {str(e)}"
                job.completed_at = datetime.utcnow()
                await db.commit()
                
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

@app.post("/process-inventory")
async def process_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file_type: str = Form(...),
    file: UploadFile = File(...),
    client_msg_id: str = Form(None),  # Opzionale: per idempotenza
    correlation_id: str = Form(None),  # Opzionale: per logging
    mode: str = Form("add"),  # "add" o "replace" - modalità import
    dry_run: bool = Form(False)  # Se True, solo anteprima senza salvare
):
    """
    Crea job di elaborazione inventario e ritorna job_id immediatamente.
    L'elaborazione avviene in background.
    Supporta idempotenza tramite client_msg_id.
    """
    try:
        from structured_logging import log_with_context
        
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
        
        if not file_type or file_type.lower() not in ["csv", "excel", "xlsx", "xls", "image", "jpg", "jpeg", "png"]:
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
                existing = await db.execute(
                    select(ProcessingJob).where(
                        ProcessingJob.telegram_id == telegram_id,
                        ProcessingJob.client_msg_id == client_msg_id
                    )
                )
                existing_job = existing.scalar_one_or_none()
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
        
        # Genera job_id univoco
        job_id = str(uuid.uuid4())
        
        # Crea job nel database
        async for db in get_db():
            job = ProcessingJob(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                status='pending',
                file_type=file_type.lower(),
                file_name=file.filename or "inventario",
                file_size_bytes=len(file_content),
                client_msg_id=client_msg_id  # Nuovo campo per idempotenza
            )
            db.add(job)
            await db.commit()
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
                correlation_id=correlation_id,  # Passa correlation_id
                mode=mode,  # Modalità import
                dry_run=dry_run  # Dry-run flag
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
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Ottieni stato elaborazione per job_id
    """
    try:
        async for db in get_db():
            stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one_or_none()
            
            if not job:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            
            response = {
                "job_id": job.job_id,
                "status": job.status or "unknown",
                "telegram_id": job.telegram_id or 0,
                "business_name": job.business_name or "",
                "file_type": job.file_type or "",
                "file_name": job.file_name or "",
                "total_wines": job.total_wines or 0,
                "processed_wines": job.processed_wines or 0,
                "saved_wines": job.saved_wines or 0,
                "error_count": job.error_count or 0,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            
            # Se completato, aggiungi risultato
            if job.status == 'completed' and job.result_data:
                try:
                    result_dict = json.loads(job.result_data)
                    if isinstance(result_dict, dict):
                        response["result"] = result_dict
                    else:
                        logger.warning(f"Invalid result_data format for job {job_id}: not a dict")
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing result_data JSON for job {job_id}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error parsing result_data for job {job_id}: {e}")
            
            # Se errore, aggiungi messaggio errore
            if job.status == 'error' and job.error_message:
                response["error"] = job.error_message
            
            # Calcola progress percentuale
            if job.total_wines and job.total_wines > 0:
                response["progress_percent"] = int((job.processed_wines or 0) / job.total_wines * 100)
            else:
                response["progress_percent"] = 0
            
            logger.debug(f"Job status response for {job_id}: status={response['status']}, progress={response['progress_percent']}%")
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/create-tables")
async def create_user_tables(telegram_id: int = Form(...), business_name: str = Form(...)):
    """
    Crea le 4 tabelle per un utente quando viene dato il nome del locale.
    
    Tabelle create:
    1. "{telegram_id}/{business_name} INVENTARIO"
    2. "{telegram_id}/{business_name} INVENTARIO backup"
    3. "{telegram_id}/{business_name} LOG interazione"
    4. "{telegram_id}/{business_name} Consumi e rifornimenti"
    
    Chiamato dal bot quando l'utente completa l'onboarding.
    """
    try:
        logger.info(f"Creating tables for telegram_id {telegram_id}, business_name: {business_name}")
        
        async for db in get_db():
            try:
                # Crea le tabelle
                tables = await ensure_user_tables(db, telegram_id, business_name)
                
                # Commit esplicito per assicurare che le modifiche siano salvate
                await db.commit()
                
                logger.info(f"Tables created successfully for {telegram_id}/{business_name}")
                return {
                    "status": "success",
                    "message": f"Tabelle create per {telegram_id}/{business_name}",
                    "tables": tables
                }
            except Exception as db_error:
                # Rollback in caso di errore
                await db.rollback()
                logger.error(f"Database error creating tables for telegram_id {telegram_id}: {db_error}")
                raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tables for telegram_id {telegram_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating tables: {str(e)}")

@app.delete("/tables/{telegram_id}")
async def delete_user_tables(telegram_id: int, business_name: str = Query(...)):
    """
    Cancella tutte le tabelle utente.
    SOLO PER telegram_id = 927230913 (admin)
    
    Uso: DELETE /tables/{telegram_id}?business_name=NomeLocale
    """
    ADMIN_TELEGRAM_ID = 927230913
    if telegram_id != ADMIN_TELEGRAM_ID:
        raise HTTPException(status_code=403, detail="Non autorizzato. Solo l'amministratore può cancellare tabelle.")
    
    try:
        async for db in get_db():
            # Ottieni nomi tabelle
            table_inventario = get_user_table_name(telegram_id, business_name, "INVENTARIO")
            table_backup = get_user_table_name(telegram_id, business_name, "INVENTARIO backup")
            table_log = get_user_table_name(telegram_id, business_name, "LOG interazione")
            table_consumi = get_user_table_name(telegram_id, business_name, "Consumi e rifornimenti")
            
            # Cancella tabelle
            from sqlalchemy import text as sql_text
            
            drop_queries = [
                sql_text(f'DROP TABLE IF EXISTS {table_inventario} CASCADE'),
                sql_text(f'DROP TABLE IF EXISTS {table_backup} CASCADE'),
                sql_text(f'DROP TABLE IF EXISTS {table_log} CASCADE'),
                sql_text(f'DROP TABLE IF EXISTS {table_consumi} CASCADE')
            ]
            
            for query in drop_queries:
                await db.execute(query)
            
            await db.commit()
            
            logger.info(f"ADMIN {telegram_id} deleted tables for {business_name}")
            return {
                "success": True,
                "message": f"Tabelle cancellate per {telegram_id}/{business_name}",
                "telegram_id": telegram_id
            }
    except Exception as e:
        logger.error(f"Error deleting tables for telegram_id {telegram_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting tables: {str(e)}")

@app.get("/status/{telegram_id}")
async def get_status(telegram_id: int):
    """
    Restituisce stato elaborazione per utente
    """
    try:
        async for db in get_db():
            status_data = await get_inventory_status(db, telegram_id)
            return status_data
    except Exception as e:
        logger.error(f"Error getting status for telegram_id {telegram_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")

async def process_movement_background(
    job_id: str,
    telegram_id: int,
    business_name: str,
    wine_name: str,
    movement_type: str,  # 'consumo' o 'rifornimento'
    quantity: int
):
    """
    Elabora movimento inventario in background (chiamata asincrona).
    Usa il nome corretto del prodotto dal database.
    """
    start_time = datetime.utcnow()
    
    try:
        async for db in get_db():
            from sqlalchemy import text as sql_text
            from structured_logging import log_with_context
            
            # Aggiorna job status a processing
            stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()
            
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            await db.commit()
            
            log_with_context(
                "info",
                f"Job {job_id}: Started processing movement for telegram_id: {telegram_id}, {movement_type} {quantity} {wine_name}",
                telegram_id=telegram_id
            )
            
            # Trova utente
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                job.status = 'error'
                job.error_message = f"Utente {telegram_id} non trovato"
                job.completed_at = datetime.utcnow()
                await db.commit()
                return
            
            # Ottieni nome tabelle e assicura che esistano (inclusa migrazione se necessario)
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = user_tables["inventario"]
            table_consumi = user_tables["consumi"]
            
            # ✅ TRANSACTIONE ATOMICA con FOR UPDATE per evitare race condition
            wine_row = None
            quantity_before = 0
            quantity_after = 0
            prodotto_rifornito = None
            prodotto_consumato = None
            
            try:
                # Cerca vino nell'inventario con FOR UPDATE (lock riga) - inizia transazione
                search_wine = sql_text(f"""
                    SELECT * FROM {table_inventario} 
                    WHERE user_id = :user_id 
                    AND (
                        LOWER(name) LIKE LOWER(:wine_name_pattern)
                        OR LOWER(producer) LIKE LOWER(:wine_name_pattern)
                    )
                    FOR UPDATE  -- ✅ LOCK row per serializzare accessi
                    LIMIT 1
                """)
                
                wine_name_pattern = f"%{wine_name}%"
                result = await db.execute(search_wine, {
                    "user_id": user.id,
                    "wine_name_pattern": wine_name_pattern
                })
                wine_row = result.fetchone()
                
                if not wine_row:
                    raise ValueError(f"Vino '{wine_name}' non trovato nell'inventario")
                
                # Ottieni quantità corrente
                quantity_before = wine_row.quantity if wine_row.quantity else 0
                
                # Calcola nuova quantità
                if movement_type == 'consumo':
                    if quantity_before < quantity:
                        raise ValueError(f"Quantità insufficiente: disponibili {quantity_before}, richieste {quantity}")
                    quantity_after = quantity_before - quantity
                    prodotto_rifornito = None
                    prodotto_consumato = quantity
                else:  # rifornimento
                    quantity_after = quantity_before + quantity
                    prodotto_rifornito = quantity
                    prodotto_consumato = None
                
                # ✅ UPDATE in stessa transazione
                update_wine = sql_text(f"""
                    UPDATE {table_inventario}
                    SET quantity = :quantity_after,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :wine_id
                """)
                await db.execute(update_wine, {
                    "quantity_after": quantity_after,
                    "wine_id": wine_row.id
                })
                
                # ✅ INSERT movimento in stessa transazione
                # Calcola quantity_change (positivo per rifornimento, negativo per consumo)
                quantity_change = quantity if movement_type == 'rifornimento' else -quantity
                
                insert_movement = sql_text(f"""
                    INSERT INTO {table_consumi}
                    (user_id, wine_name, wine_producer, movement_type, quantity_change, quantity_before, quantity_after, movement_date)
                    VALUES
                    (:user_id, :wine_name, :wine_producer, :movement_type, :quantity_change, :quantity_before, :quantity_after, CURRENT_TIMESTAMP)
                    RETURNING id
                """)
                await db.execute(insert_movement, {
                    "user_id": user.id,
                    "wine_name": wine_row.name,  # Nome corretto dal database
                    "wine_producer": getattr(wine_row, 'producer', None),
                    "movement_type": movement_type,
                    "quantity_change": quantity_change,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after
                })
                
                # ✅ COMMIT esplicito per garantire atomicità
                await db.commit()
            except ValueError as ve:
                # Errore validazione: rollback e aggiorna job
                await db.rollback()
                job.status = 'error'
                job.error_message = str(ve)
                job.completed_at = datetime.utcnow()
                await db.commit()
                return
            except Exception as te:
                # Errore transazione: rollback
                await db.rollback()
                raise  # Rilancia per essere gestito dal catch esterno
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Prepara risultato
            result_data = {
                "status": "success",
                "movement_type": movement_type,
                "wine_name": wine_row.name,  # Nome corretto dal database
                "quantity": quantity,
                "quantity_before": quantity_before,
                "quantity_after": quantity_after,
                "telegram_id": telegram_id,
                "business_name": business_name,
                "processing_time_seconds": round(processing_time, 2)
            }
            
            # Aggiorna job come completato
            job.status = 'completed'
            job.result_data = json.dumps(result_data)
            job.completed_at = datetime.utcnow()
            await db.commit()
            
            log_with_context(
                "info",
                f"Job {job_id}: Movement processed successfully - {movement_type} {quantity} {wine_row.name}",
                telegram_id=telegram_id
            )
            break
            
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error: {e}")
        try:
            async for db in get_db():
                stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()
                job.status = 'error'
                job.error_message = f"Unexpected error: {str(e)}"
                job.completed_at = datetime.utcnow()
                await db.commit()
                break
        except:
            pass

@app.post("/process-movement")
async def process_movement(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    wine_name: str = Form(...),
    movement_type: str = Form(...),  # 'consumo' o 'rifornimento'
    quantity: int = Form(...)
):
    """
    Crea job di elaborazione movimento inventario e ritorna job_id immediatamente.
    L'elaborazione avviene in background.
    """
    try:
        logger.info(f"Creating movement job for telegram_id: {telegram_id}, business: {business_name}, {movement_type} {quantity} {wine_name}")
        
        # Validazione input
        if movement_type not in ['consumo', 'rifornimento']:
            raise HTTPException(status_code=400, detail="movement_type deve essere 'consumo' o 'rifornimento'")
        
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity deve essere > 0")
        
        # Genera job_id univoco
        job_id = str(uuid.uuid4())
        
        # Crea job nel database
        async for db in get_db():
            job = ProcessingJob(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                status='pending',
                file_type='movement',  # Tipo speciale per movimenti
                file_name=f"{movement_type}_{wine_name}_{quantity}"
            )
            db.add(job)
            await db.commit()
            break
        
        logger.info(f"Movement job {job_id} created, starting background processing")
        
        # Avvia elaborazione in background
        asyncio.create_task(
            process_movement_background(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                wine_name=wine_name,
                movement_type=movement_type,
                quantity=quantity
            )
        )
        
        # Ritorna job_id immediatamente
        return {
            "status": "processing",
            "job_id": job_id,
            "message": f"Movimento {movement_type} avviato. Usa /status/{job_id} per verificare lo stato.",
            "telegram_id": telegram_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating movement job: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/update-wine-field")
async def update_wine_field(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    wine_id: int = Form(...),
    field: str = Form(...),
    value: str = Form(...)
):
    """
    Aggiorna un singolo campo per un vino dell'inventario utente.
    Campi supportati: producer, supplier, vintage, grape_variety, classification, selling_price, cost_price, alcohol_content, description, notes
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
        }
        if field not in allowed_fields:
            raise HTTPException(status_code=400, detail=f"Field not allowed: {field}")

        # Normalizza tipi per alcuni campi
        def cast_value(f: str, v: str):
            if f in ('vintage',):
                try:
                    return int(v)
                except:
                    raise HTTPException(status_code=400, detail=f"Invalid integer for {f}")
            if f in ('selling_price', 'cost_price', 'alcohol_content'):
                try:
                    return float(str(v).replace(',', '.'))
                except:
                    raise HTTPException(status_code=400, detail=f"Invalid number for {f}")
            return v

        column = allowed_fields[field]
        new_value = cast_value(field, value)

        async for db in get_db():
            # Assicura esistenza tabelle
            user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = tables["inventario"]

            from sqlalchemy import text as sql_text
            update_stmt = sql_text(f"""
                UPDATE {table_inventario}
                SET {column} = :val, updated_at = CURRENT_TIMESTAMP
                WHERE id = :wine_id AND user_id = :user_id
                RETURNING id
            """)
            result = await db.execute(update_stmt, {"val": new_value, "wine_id": wine_id, "user_id": user.id})
            updated = result.scalar_one_or_none()
            if not updated:
                await db.rollback()
                raise HTTPException(status_code=404, detail="Wine not found")
            await db.commit()
            return {"status": "success", "wine_id": wine_id, "field": field}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wine field: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/ai/status")
async def ai_status():
    """Stato dell'AI processor"""
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return {
                "ai_enabled": False,
                "message": "OpenAI API key not configured"
            }
        
        # Test connessione OpenAI
        try:
            # Test semplice con AI
            test_result = await ai_processor.classify_wine_type("Chianti Classico")
            return {
                "ai_enabled": True,
                "openai_connected": True,
                "test_classification": test_result,
                "message": "AI processor ready"
            }
        except Exception as e:
            return {
                "ai_enabled": True,
                "openai_connected": False,
                "error": str(e),
                "message": "AI processor configured but not responding"
            }
            
    except Exception as e:
        return {
            "ai_enabled": False,
            "error": str(e),
            "message": "Error checking AI status"
        }

@app.post("/ai/test")
async def test_ai_processing(
    text: str = Form(...)
):
    """Test AI processing con testo"""
    try:
        # Estrai vini dal testo usando AI
        wines = await ai_processor.extract_wines_from_text(text)
        
        return {
            "status": "success",
            "wines_found": len(wines),
            "wines": wines,
            "ai_processing": True
        }
        
    except Exception as e:
        logger.error(f"Error in AI test: {e}")
        raise HTTPException(status_code=500, detail=f"AI test failed: {str(e)}")

@app.get("/debug/info")
async def debug_info():
    """Informazioni di debug per troubleshooting"""
    try:
        import sys
        import platform
        
        return {
            "service": "gioia-processor",
            "version": "1.0.0",
            "python_version": sys.version,
            "platform": platform.platform(),
            "environment_variables": {
                "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else None,
                "PORT": os.getenv("PORT"),
                "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else None,
                "ENVIRONMENT": os.getenv("ENVIRONMENT", "production")
            },
            "database_test": await test_database_connection(),
            "ai_test": await test_ai_connection(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

async def test_database_connection():
    """Test connessione database"""
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            return {"status": "connected", "error": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def test_ai_connection():
    """Test connessione AI"""
    try:
        if not os.getenv("OPENAI_API_KEY"):
            return {"status": "not_configured", "error": "OPENAI_API_KEY not set"}
        
        # Test semplice
        result = await ai_processor.classify_wine_type("Chianti")
        return {"status": "connected", "test_result": result, "error": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/debug/logs")
async def debug_logs():
    """Logs recenti per debugging"""
    try:
        # Simula logs (in produzione usare un sistema di logging reale)
        return {
            "service": "gioia-processor",
            "logs": [
                {"level": "INFO", "message": "Service started", "timestamp": datetime.utcnow().isoformat()},
                {"level": "INFO", "message": "Database connected", "timestamp": datetime.utcnow().isoformat()},
                {"level": "INFO", "message": "AI processor ready", "timestamp": datetime.utcnow().isoformat()}
            ],
            "note": "This is a simplified log view. Check Railway dashboard for full logs."
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/process-inventory-graphql")
async def process_inventory_graphql(request: Request):
    """
    Elabora file inventario usando formato GraphQL multipart
    """
    try:
        # Leggi il contenuto della richiesta
        form = await request.form()
        
        # Estrai operations e map
        operations_str = form.get("operations")
        map_str = form.get("map")
        
        if not operations_str or not map_str:
            raise HTTPException(status_code=400, detail="Missing operations or map")
        
        # Parse JSON
        operations = json.loads(operations_str)
        file_map = json.loads(map_str)
        
        # Estrai variabili
        variables = operations.get("variables", {})
        telegram_id = variables.get("telegram_id")
        business_name = variables.get("business_name")
        file_type = variables.get("file_type")
        
        # Estrai file usando la mappa
        file_key = list(file_map.keys())[0]  # Prende la prima chiave (es. "0")
        file = form.get(file_key)
        
        if not file:
            raise HTTPException(status_code=400, detail="File not found in request")
        
        logger.info(f"GraphQL Processing inventory for telegram_id: {telegram_id}, business: {business_name}, type: {file_type}")
        
        # Usa la stessa logica dell'endpoint standard
        return await process_inventory_logic(telegram_id, business_name, file_type, file)
        
    except Exception as e:
        logger.error(f"Error in GraphQL endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_inventory_logic(telegram_id: int, business_name: str, file_type: str, file):
    """
    Logica comune per elaborazione inventario
    """
    start_time = datetime.utcnow()
    
    try:
        # Validazione input
        if not telegram_id or telegram_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid telegram_id")
        
        if not business_name or len(business_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Business name is required")
        
        if not file_type or file_type.lower() not in ["csv", "excel", "xlsx", "xls", "image", "jpg", "jpeg", "png", "photo"]:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Leggi contenuto file
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Processa file in base al tipo
        if file_type.lower() in ["csv"]:
            wines_data, _ = await process_csv_file(file_content)
        elif file_type.lower() in ["excel", "xlsx", "xls"]:
            wines_data, _ = await process_excel_file(file_content)
        elif file_type.lower() in ["image", "jpg", "jpeg", "png", "photo"]:
            wines_data = await process_image_ocr(file_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        if not wines_data:
            return {
                "status": "error",
                "error": "No wines found in file",
                "telegram_id": telegram_id
            }
        
        # Salva nel database
        async for db in get_db():
            save_result = await save_inventory_to_db(db, telegram_id, business_name, wines_data)
            break
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Inventory processed successfully: {len(wines_data)} wines in {processing_time:.2f}s")
        
        return {
            "status": "success",
            "total_wines": len(wines_data),
            "business_name": business_name,
            "telegram_id": telegram_id,
            "processing_time": processing_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing inventory: {e}")
        return {
            "status": "error",
            "error": str(e),
            "telegram_id": telegram_id
        }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
