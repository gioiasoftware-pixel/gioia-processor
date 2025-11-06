"""
Router per movimenti inventario (consumo/rifornimento).

Endpoint:
- POST /process-movement: Crea job e avvia elaborazione in background.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException
from sqlalchemy import select, text as sql_text

from core.database import get_db, ensure_user_tables, ProcessingJob, User
from core.logger import log_with_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["movements"])  # senza prefix per mantenere /process-movement


async def process_movement_background(
    job_id: str,
    telegram_id: int,
    business_name: str,
    wine_name: str,
    movement_type: str,  # 'consumo' o 'rifornimento'
    quantity: int
):
    """
    Elabora movimento inventario in background.
    Aggiorna job in base all'esito e scrive log strutturati.
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

            log_with_context(
                "info",
                f"[MOVEMENT] Job {job_id}: Started processing movement: {movement_type} {quantity} {wine_name}",
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

            # Assicura tabelle
            user_tables = await ensure_user_tables(db, telegram_id, business_name)
            table_inventario = user_tables["inventario"]
            table_consumi = user_tables["consumi"]

            # ✅ TRANSACTIONE ATOMICA con FOR UPDATE per evitare race condition (come vecchia versione)
            # Cerca vino nell'inventario con FOR UPDATE (lock riga) - inizia transazione
            wine_name_pattern = f"%{wine_name}%"
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: Cercando vino '{wine_name}' (pattern: '{wine_name_pattern}') "
                f"per user_id={user.id} in tabella {table_inventario}"
            )
            
            search_wine = sql_text(f"""
                SELECT id, name, producer, quantity 
                FROM {table_inventario} 
                WHERE user_id = :user_id 
                AND (
                    LOWER(name) LIKE LOWER(:wine_name_pattern)
                    OR LOWER(producer) LIKE LOWER(:wine_name_pattern)
                )
                FOR UPDATE  -- ✅ LOCK row per serializzare accessi
                LIMIT 1
            """)
            
            res = await db.execute(search_wine, {
                "user_id": user.id,
                "wine_name_pattern": wine_name_pattern
            })
            wine_row = res.fetchone()

            if not wine_row:
                logger.warning(
                    f"[MOVEMENT] Job {job_id}: Wine not found | "
                    f"telegram_id={telegram_id}, business={business_name}, "
                    f"search_pattern='{wine_name_pattern}', table={table_inventario}"
                )
                err = f"Vino '{wine_name}' non trovato"
                job.status = 'error'
                job.error_message = err
                job.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Accedi ai campi tramite chiavi (Row object)
            wine_id = wine_row[0]  # id
            wine_name_db = wine_row[1]  # name
            wine_producer = wine_row[2] if len(wine_row) > 2 else None  # producer
            quantity_before = wine_row[3] if len(wine_row) > 3 else 0  # quantity
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: Found wine | "
                f"wine_id={wine_id}, wine_name='{wine_name_db}', "
                f"quantity_before={quantity_before}, requested={quantity}"
            )

            try:
                # Calcola nuova quantità (come vecchia versione - calcolo diretto)
                if movement_type == 'consumo':
                    if quantity_before < quantity:
                        logger.warning(
                            f"[MOVEMENT] Job {job_id}: Insufficient quantity | "
                            f"wine_id={wine_id}, wine_name='{wine_name_db}', "
                            f"available={quantity_before}, requested={quantity}"
                        )
                        error_msg = f"Quantità insufficiente: disponibili {quantity_before}, richieste {quantity}"
                        job.status = 'error'
                        job.error_message = error_msg
                        job.completed_at = datetime.utcnow()
                        await db.commit()
                        return
                    quantity_after = quantity_before - quantity
                elif movement_type == 'rifornimento':
                    quantity_after = quantity_before + quantity
                else:
                    raise ValueError("movement_type deve essere 'consumo' o 'rifornimento'")

                # ✅ UPDATE in stessa transazione (come vecchia versione)
                update_wine = sql_text(f"""
                    UPDATE {table_inventario}
                    SET quantity = :quantity_after,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :wine_id
                """)
                await db.execute(update_wine, {
                    "quantity_after": quantity_after,
                    "wine_id": wine_id
                })
                logger.info(f"[MOVEMENT] Job {job_id}: UPDATE inventario eseguito - quantity: {quantity_before} → {quantity_after}")

                # Inserisci log movimento con schema corretto della tabella
                quantity_change = quantity if movement_type == 'rifornimento' else -quantity
                logger.info(
                    f"[MOVEMENT] Job {job_id}: Inserendo log movimento - "
                    f"wine_name='{wine_name_db}', quantity_change={quantity_change}, "
                    f"quantity_before={quantity_before}, quantity_after={quantity_after}"
                )
                
                insert_mov = sql_text(f"""
                    INSERT INTO {table_consumi}
                        (user_id, wine_name, wine_producer, movement_type, quantity_change, quantity_before, quantity_after, movement_date)
                    VALUES (:user_id, :wine_name, :wine_producer, :movement_type, :quantity_change, :quantity_before, :quantity_after, CURRENT_TIMESTAMP)
                """)
                await db.execute(insert_mov, {
                    "user_id": user.id,
                    "wine_name": wine_name_db,
                    "wine_producer": wine_producer,
                    "movement_type": movement_type,
                    "quantity_change": quantity_change,
                    "quantity_before": quantity_before,
                    "quantity_after": quantity_after
                })
                
                logger.info(f"[MOVEMENT] Job {job_id}: INSERT log movimento eseguito")

                await db.commit()
                logger.info(f"[MOVEMENT] Job {job_id}: Commit transazione completato")

            except Exception as te:
                await db.rollback()
                logger.error(
                    f"[MOVEMENT] Job {job_id}: Transaction error | telegram_id={telegram_id}, business={business_name}, "
                    f"wine_name={wine_name}, movement_type={movement_type}, quantity={quantity} | Error: {str(te)}",
                    exc_info=True
                )
                raise

            processing_time = (datetime.utcnow() - start_time).total_seconds()

            result_data = {
                "status": "success",
                "movement_type": movement_type,
                "wine_name": wine_name_db,
                "quantity": quantity,
                "quantity_before": quantity_before,
                "quantity_after": quantity_after,
                "telegram_id": telegram_id,
                "business_name": business_name,
                "processing_time_seconds": round(processing_time, 2)
            }

            job.status = 'completed'
            job.result_data = json.dumps(result_data)
            job.completed_at = datetime.utcnow()
            await db.commit()
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: Job aggiornato a 'completed' | "
                f"result_data salvato: {json.dumps(result_data)[:200]}"
            )

            log_with_context(
                "info",
                f"[MOVEMENT] Job {job_id}: Movement processed successfully - {movement_type} {quantity} {wine_name_db}",
                telegram_id=telegram_id
            )
            break

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(
            f"[MOVEMENT] Job {job_id}: {error_msg} | telegram_id={telegram_id}, business={business_name}, "
            f"wine_name={wine_name}, movement_type={movement_type}, quantity={quantity}",
            exc_info=True
        )
        try:
            async for db in get_db():
                stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()
                job.status = 'error'
                job.error_message = error_msg
                job.completed_at = datetime.utcnow()
                await db.commit()
                break
        except Exception:
            pass


@router.post("/process-movement")
async def process_movement(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    wine_name: str = Form(...),
    movement_type: str = Form(...),  # 'consumo' o 'rifornimento'
    quantity: int = Form(...)
):
    """
    Crea job movimento e elabora SINCRONAMENTE (come vecchia versione).
    Ritorna risultato immediatamente senza bisogno di polling.
    """
    import uuid
    
    try:
        logger.info(
            f"Creating movement job for telegram_id: {telegram_id}, business: {business_name}, {movement_type} {quantity} {wine_name}"
        )

        if movement_type not in ['consumo', 'rifornimento']:
            raise HTTPException(status_code=400, detail="movement_type deve essere 'consumo' o 'rifornimento'")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity deve essere > 0")

        job_id = str(uuid.uuid4())

        async for db in get_db():
            job = ProcessingJob(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                status='pending',
                file_type='movement',
                file_name=f"{movement_type}_{wine_name}",
                file_size_bytes=0
            )
            db.add(job)
            await db.commit()
            break

        logger.info(f"Movement job {job_id} created, processing synchronously")
        
        # ✅ Elabora movimento in modo SINCRONO (operazioni veloci, < 1 secondo)
        # Questo permette al bot di ricevere immediatamente il risultato
        try:
            await process_movement_background(
                job_id=job_id,
                telegram_id=telegram_id,
                business_name=business_name,
                wine_name=wine_name,
                movement_type=movement_type,
                quantity=quantity
            )
            
            # Recupera risultato dal job completato
            async for db in get_db():
                stmt = select(ProcessingJob).where(ProcessingJob.job_id == job_id)
                result = await db.execute(stmt)
                job = result.scalar_one()
                
                if job.status == 'completed':
                    # Job completato con successo
                    result_data = json.loads(job.result_data) if job.result_data else {}
                    return {
                        "status": "success",
                        "job_id": job_id,
                        "wine_name": result_data.get("wine_name", wine_name),
                        "quantity": quantity,
                        "quantity_before": result_data.get("quantity_before", 0),
                        "quantity_after": result_data.get("quantity_after", 0),
                        "movement_type": movement_type,
                        "telegram_id": telegram_id,
                        "message": f"Movimento {movement_type} completato con successo"
                    }
                elif job.status == 'error':
                    # Job fallito
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "error": job.error_message or "Errore sconosciuto durante l'elaborazione",
                        "error_message": job.error_message or "Errore sconosciuto durante l'elaborazione",
                        "telegram_id": telegram_id
                    }
                else:
                    # Stato inatteso
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "error": f"Stato job inatteso: {job.status}",
                        "error_message": f"Stato job inatteso: {job.status}",
                        "telegram_id": telegram_id
                    }
                break
        except Exception as e:
            logger.error(
                f"Error processing movement synchronously: {e} | "
                f"telegram_id={telegram_id}, wine_name={wine_name}, "
                f"movement_type={movement_type}, quantity={quantity}",
                exc_info=True
            )
            return {
                "status": "error",
                "job_id": job_id,
                "error": f"Errore durante elaborazione: {str(e)}",
                "error_message": f"Errore durante elaborazione: {str(e)}",
                "telegram_id": telegram_id
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating movement job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

