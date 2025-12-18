"""
Main FastAPI application per gioia-processor.

Refactor di main.py con nuova architettura modulare.
Mantiene compatibilità endpoint esistenti.
"""
import logging
import os
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from core.config import get_config, validate_config
from core.database import create_tables, get_db, ProcessingJob, ensure_user_tables_from_telegram_id, AsyncSessionLocal
from sqlalchemy import text as sql_text
from core.logger import setup_colored_logging
from core.scheduler import start_scheduler, shutdown_scheduler
from api.routers import ingest, snapshot
from api.routers import movements, diagnostics, admin
from ingest.learned_terms_manager import load_learned_terms_set, load_learned_terms_dict
from ingest.wine_terms_dict import set_learned_terms

# Configurazione logging colorato
setup_colored_logging("processor")
logger = logging.getLogger(__name__)

app = FastAPI(title="Gioia Processor", version="2.0.0")

# CORS per comunicazione con bot
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# Nota: ingest router usa prefix="/api" ma endpoint /process-inventory deve essere senza prefix
# Quindi aggiungiamo router senza prefix
app.include_router(ingest.router, prefix="")  # /process-inventory senza /api prefix
app.include_router(snapshot.router)  # /api/inventory/snapshot, /api/viewer/*, etc.
app.include_router(movements.router, prefix="")  # /process-movement
app.include_router(diagnostics.router)
app.include_router(admin.router)  # /admin/* endpoints


async def run_auto_migrations():
    """
    Esegue migrazioni automatiche se non già completate.
    Controlla se le migrazioni sono necessarie prima di eseguirle.
    """
    import importlib
    import sys
    import os
    
    logger.info("[AUTO-MIGRATION] Verifica migrazioni necessarie...")
    
    # Debug: log percorso corrente e struttura directory
    current_file = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(current_file))
    logger.info(f"[AUTO-MIGRATION] File corrente: {current_file}")
    logger.info(f"[AUTO-MIGRATION] Directory base: {base_dir}")
    logger.info(f"[AUTO-MIGRATION] Working directory: {os.getcwd()}")
    
    # Prova diversi percorsi possibili per migrations
    possible_paths = [
        os.path.join(base_dir, "migrations"),
        os.path.join(os.getcwd(), "migrations"),
        os.path.join("/app", "migrations"),
        "migrations"  # Percorso relativo
    ]
    
    migrations_dir = None
    for path in possible_paths:
        if os.path.exists(path) and os.path.isdir(path):
            migrations_dir = path
            logger.info(f"[AUTO-MIGRATION] Trovata directory migrations: {migrations_dir}")
            break
    
    if not migrations_dir:
        logger.error(f"[AUTO-MIGRATION] Directory migrations non trovata. Percorsi provati: {possible_paths}")
        return  # Esci senza errori, le migrazioni verranno eseguite manualmente
    
    async for db in get_db():
        try:
            # Migrazione 005: Rinomina tabelle da telegram_id a user_id
            # Controlla se ci sono ancora tabelle con formato telegram_id
            # NOTA: in information_schema.tables i nomi sono SENZA virgolette
            check_005 = sql_text("""
                SELECT COUNT(*) 
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name ~ '^[0-9]+/'
            """)
            result = await db.execute(check_005)
            count_old_tables = result.scalar() or 0
            
            if count_old_tables > 0:
                logger.info(f"[AUTO-MIGRATION] Esecuzione migrazione 005: {count_old_tables} tabelle da migrare")
                # Importa ed esegue migrazione 005 usando importlib
                migrations_path = os.path.join(migrations_dir, "005_migrate_telegram_to_user_id.py")
                if not os.path.exists(migrations_path):
                    logger.error(f"[AUTO-MIGRATION] File migrazione non trovato: {migrations_path}")
                    logger.error(f"[AUTO-MIGRATION] Contenuto directory {migrations_dir}: {os.listdir(migrations_dir) if os.path.exists(migrations_dir) else 'NON ESISTE'}")
                    return  # Esci senza errori
                spec_005 = importlib.util.spec_from_file_location("migrate_005", migrations_path)
                module_005 = importlib.util.module_from_spec(spec_005)
                sys.modules["migrate_005"] = module_005
                spec_005.loader.exec_module(module_005)
                await module_005.migrate_tables_telegram_to_user_id()
                logger.info("[AUTO-MIGRATION] Migrazione 005 completata")
            else:
                logger.info("[AUTO-MIGRATION] Migrazione 005 non necessaria (nessuna tabella con formato telegram_id)")
            
            # Migrazione 004: Popola Storico vino
            # Controlla se ci sono utenti con movimenti ma senza storico
            check_004 = sql_text("""
                SELECT COUNT(DISTINCT u.id)
                FROM users u
                WHERE EXISTS (
                    SELECT 1 
                    FROM information_schema.tables t
                    WHERE t.table_schema = 'public'
                    AND t.table_name LIKE '"' || u.id || '/% Consumi e rifornimenti"'
                )
                AND NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables t2
                    WHERE t2.table_schema = 'public'
                    AND t2.table_name LIKE '"' || u.id || '/% Storico vino"'
                )
            """)
            result = await db.execute(check_004)
            count_users_needing_migration = result.scalar() or 0
            
            if count_users_needing_migration > 0:
                logger.info(f"[AUTO-MIGRATION] Esecuzione migrazione 004: {count_users_needing_migration} utenti da migrare")
                # Importa ed esegue migrazione 004 usando importlib
                migrations_path = os.path.join(migrations_dir, "004_migrate_wine_history.py")
                if not os.path.exists(migrations_path):
                    logger.error(f"[AUTO-MIGRATION] File migrazione non trovato: {migrations_path}")
                    return  # Esci senza errori
                spec_004 = importlib.util.spec_from_file_location("migrate_004", migrations_path)
                module_004 = importlib.util.module_from_spec(spec_004)
                sys.modules["migrate_004"] = module_004
                spec_004.loader.exec_module(module_004)
                await module_004.migrate_wine_history()
                logger.info("[AUTO-MIGRATION] Migrazione 004 completata")
            else:
                logger.info("[AUTO-MIGRATION] Migrazione 004 non necessaria (tutti gli utenti hanno già Storico vino)")
            
            break
        except Exception as e:
            logger.error(f"[AUTO-MIGRATION] Errore durante migrazione: {e}", exc_info=True)
            raise


@app.on_event("startup")
async def startup_event():
    """Inizializza database e configurazione al startup"""
    try:
        # Valida configurazione
        config = get_config()
        validate_config()
        
        # Crea tabelle database
        await create_tables()
        logger.info("Database tables created successfully")
        
        # Esegui migrazioni automatiche (se non già eseguite)
        try:
            await run_auto_migrations()
        except Exception as migrate_error:
            logger.warning(f"Auto-migration failed (continuing anyway): {migrate_error}", exc_info=True)
        
        # Carica termini problematici appresi dal database
        try:
            async with AsyncSessionLocal() as session:
                learned_terms_set = await load_learned_terms_set(session)
                learned_terms_dict = await load_learned_terms_dict(session)
                set_learned_terms(learned_terms_set, learned_terms_dict)
                logger.info(
                    f"Loaded {len(learned_terms_set)} learned problematic terms from database "
                    f"for wine name filtering"
                )
        except Exception as learned_error:
            logger.warning(f"Error loading learned terms (continuing anyway): {learned_error}")
        
        # Verifica configurazione AI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("OpenAI API key configured - AI features enabled")
        else:
            logger.warning("OpenAI API key not found - AI features disabled")
        
        # Avvia scheduler per task periodici (report giornalieri)
        try:
            start_scheduler()
        except Exception as scheduler_error:
            logger.warning(f"Error starting scheduler (continuing anyway): {scheduler_error}")
            
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        # Notifica admin per errore startup (critico)
        try:
            from admin_notifications import enqueue_admin_notification
            from core.logger import get_correlation_id
            import asyncio
            
            # Crea task per notifica (non blocca startup)
            async def notify_startup_error():
                await enqueue_admin_notification(
                    event_type="error",
                    telegram_id=0,
                    payload={
                        "error_type": "startup_error",
                        "error_message": str(e),
                        "error_code": "STARTUP_ERROR",
                        "component": "gioia-processor",
                        "severity": "critical"
                    },
                    correlation_id=get_correlation_id()
                )
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(notify_startup_error())
                else:
                    loop.run_until_complete(notify_startup_error())
            except Exception:
                pass  # Non bloccare startup se notifica fallisce
        except Exception:
            pass  # Non bloccare startup se import fallisce


@app.get("/health")
async def health_check():
    """Health check del servizio con informazioni dettagliate"""
    try:
        # Verifica configurazione
        config = get_config()
        
        # Verifica database
        db_status = "unknown"
        try:
            async for db in get_db():
                await db.execute(select(1))
                db_status = "connected"
                break
        except Exception as db_error:
            db_status = f"error: {str(db_error)}"
        
        # Verifica OpenAI
        openai_status = "configured" if os.getenv("OPENAI_API_KEY") else "not_configured"
        
        return {
            "status": "healthy",
            "service": "gioia-processor",
            "version": "2.0.0",
            "timestamp": str(datetime.utcnow()),
            "database": db_status,
            "openai": openai_status,
            "features": {
                "ia_targeted_enabled": config.ia_targeted_enabled,
                "llm_fallback_enabled": config.llm_fallback_enabled,
                "ocr_enabled": config.ocr_enabled
            },
            "endpoints": {
                "process_inventory": "/process-inventory",
                "process_movement": "/process-movement",
                "status": "/status/{job_id}",
                "snapshot": "/api/inventory/snapshot",
                "export": "/api/inventory/export.csv",
                "admin_trigger_report": "/admin/trigger-daily-report",
                "admin_update_wine_field": "/admin/update-wine-field"
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


@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Ottieni stato elaborazione per job_id.
    
    Mantiene compatibilità endpoint esistente.
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
                    import json
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
            
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/create-tables")
async def create_user_tables(
    telegram_id: int = Form(...),
    business_name: str = Form(...)
):
    """
    Crea tabelle utente nel processor (compatibilità con bot).
    
    Mantiene compatibilità endpoint esistente per onboarding.
    """
    try:
        async for db in get_db():
            user_tables = await ensure_user_tables_from_telegram_id(db, telegram_id, business_name)
            
            logger.info(
                f"Tabelle create per telegram_id={telegram_id}, "
                f"business_name={business_name}: {list(user_tables.keys())}"
            )
            
            return {
                "status": "success",
                "telegram_id": telegram_id,
                "business_name": business_name,
                "tables": user_tables
            }
            
    except Exception as e:
        logger.error(f"Error creating user tables: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating tables: {str(e)}")


# (Endpoint /process-movement migrato in api/routers/movements.py)

