"""
Job Manager per gioia-processor.

Gestisce creazione, aggiornamento e recupero job di elaborazione.
Migrato da main.py con miglioramenti.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import ProcessingJob, User

logger = logging.getLogger(__name__)


async def create_job(
    session: AsyncSession,
    telegram_id: int,
    business_name: str,
    file_type: str,
    file_name: str,
    file_size_bytes: int,
    client_msg_id: Optional[str] = None,
    update_id: Optional[int] = None
) -> str:
    """
    Crea un nuovo job di elaborazione.
    
    Args:
        session: Sessione database
        telegram_id: ID Telegram utente
        business_name: Nome business
        file_type: Tipo file (csv, excel, image, pdf)
        file_name: Nome file
        file_size_bytes: Dimensione file in bytes
        client_msg_id: ID messaggio client per idempotenza (opzionale)
        update_id: Telegram update_id per tracciamento (opzionale)
    
    Returns:
        job_id: ID univoco del job
    """
    # Genera job_id univoco
    job_id = str(uuid.uuid4())
    
    # Crea job nel database
    job = ProcessingJob(
        job_id=job_id,
        telegram_id=telegram_id,
        business_name=business_name,
        status='pending',
        file_type=file_type.lower(),
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        client_msg_id=client_msg_id,
        update_id=update_id
    )
    
    session.add(job)
    await session.commit()
    
    logger.info(f"[JOB_MANAGER] Created job {job_id} for telegram_id={telegram_id}, file={file_name}")
    
    return job_id


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    result_data: Optional[Dict[str, Any]] = None,
    total_wines: Optional[int] = None,
    processed_wines: Optional[int] = None,
    saved_wines: Optional[int] = None,
    error_count: Optional[int] = None,
    processing_method: Optional[str] = None
) -> bool:
    """
    Aggiorna stato di un job.
    
    Args:
        session: Sessione database
        job_id: ID job
        status: Nuovo stato ('pending', 'processing', 'completed', 'error')
        error_message: Messaggio errore (opzionale)
        result_data: Dati risultato JSON (opzionale)
        total_wines: Numero totale vini (opzionale)
        processed_wines: Numero vini processati (opzionale)
        saved_wines: Numero vini salvati (opzionale)
        error_count: Numero errori (opzionale)
        processing_method: Metodo elaborazione (opzionale)
    
    Returns:
        True se aggiornato con successo, False se job non trovato
    """
    try:
        stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            logger.warning(f"[JOB_MANAGER] Job {job_id} not found for status update")
            return False
        
        # Aggiorna stato
        job.status = status
        
        # Aggiorna timestamp in base allo stato
        if status == 'processing' and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in ['completed', 'error']:
            job.completed_at = datetime.utcnow()
        
        # Aggiorna campi opzionali
        if error_message is not None:
            job.error_message = error_message
        
        if result_data is not None:
            import json
            job.result_data = json.dumps(result_data, ensure_ascii=False)
        
        if total_wines is not None:
            job.total_wines = total_wines
        
        if processed_wines is not None:
            job.processed_wines = processed_wines
        
        if saved_wines is not None:
            job.saved_wines = saved_wines
        
        if error_count is not None:
            job.error_count = error_count
        
        if processing_method is not None:
            job.processing_method = processing_method
        
        await session.commit()
        
        logger.info(f"[JOB_MANAGER] Updated job {job_id} to status={status}")
        
        return True
        
    except Exception as e:
        logger.error(f"[JOB_MANAGER] Error updating job {job_id}: {e}", exc_info=True)
        await session.rollback()
        return False


async def get_job(session: AsyncSession, job_id: str) -> Optional[ProcessingJob]:
    """
    Recupera un job per ID.
    
    Args:
        session: Sessione database
        job_id: ID job
    
    Returns:
        ProcessingJob se trovato, None altrimenti
    """
    try:
        stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        
        return job
        
    except Exception as e:
        logger.error(f"[JOB_MANAGER] Error getting job {job_id}: {e}", exc_info=True)
        return None


async def get_job_by_client_msg_id(
    session: AsyncSession,
    telegram_id: int,
    client_msg_id: str
) -> Optional[ProcessingJob]:
    """
    Recupera un job per client_msg_id (idempotenza).
    
    Args:
        session: Sessione database
        telegram_id: ID Telegram utente
        client_msg_id: ID messaggio client
    
    Returns:
        ProcessingJob se trovato, None altrimenti
    """
    try:
        stmt = select(ProcessingJob).where(
            ProcessingJob.telegram_id == telegram_id,
            ProcessingJob.client_msg_id == client_msg_id
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        
        return job
        
    except Exception as e:
        logger.error(f"[JOB_MANAGER] Error getting job by client_msg_id: {e}", exc_info=True)
        return None


async def get_user_jobs(
    session: AsyncSession,
    telegram_id: int,
    limit: int = 10,
    status: Optional[str] = None
) -> List[ProcessingJob]:
    """
    Recupera job di un utente.
    
    Args:
        session: Sessione database
        telegram_id: ID Telegram utente
        limit: Numero massimo job da recuperare
        status: Filtra per stato (opzionale)
    
    Returns:
        Lista ProcessingJob
    """
    try:
        stmt = select(ProcessingJob).where(ProcessingJob.telegram_id == telegram_id)
        
        if status:
            stmt = stmt.where(ProcessingJob.status == status)
        
        stmt = stmt.order_by(ProcessingJob.created_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        jobs = result.scalars().all()
        
        return list(jobs)
        
    except Exception as e:
        logger.error(f"[JOB_MANAGER] Error getting user jobs: {e}", exc_info=True)
        return []

