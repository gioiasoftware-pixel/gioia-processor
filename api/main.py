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
from core.database import create_tables, get_db, ProcessingJob, ensure_user_tables, AsyncSessionLocal
from core.logger import setup_colored_logging
from api.routers import ingest, snapshot
from api.routers import movements
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
            
    except Exception as e:
        logger.error(f"Error during startup: {e}")


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
                "export": "/api/inventory/export.csv"
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
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            
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

