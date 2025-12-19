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
    user_id: int,
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
                telegram_id=user_id  # Mantenuto per retrocompatibilità log
            )

            # Trova utente per user_id
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                job.status = 'error'
                job.error_message = f"Utente user_id={user_id} non trovato"
                job.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Assicura tabelle usando user_id direttamente
            user_tables = await ensure_user_tables(db, user_id, business_name)
            table_inventario = user_tables["inventario"]
            table_consumi = user_tables["consumi"]
            table_storico = user_tables.get("storico")  # Nuova tabella Storico vino

            # ✅ TRANSACTIONE ATOMICA con FOR UPDATE per evitare race condition (come vecchia versione)
            # Cerca vino nell'inventario con FOR UPDATE (lock riga) - inizia transazione
            wine_name_pattern = f"%{wine_name}%"
            wine_name_lower = wine_name.strip().lower()
            
            # Determina se il termine è probabilmente un nome di uvaggio
            # Lista di uvaggi italiani e internazionali comuni
            common_grape_varieties = {
                'vermentino', 'nero', 'davola', 'nero d\'avola', 'nerodavola',
                'sangiovese', 'montepulciano', 'barbera', 'nebbiolo', 'dolcetto',
                'pinot', 'pinot grigio', 'pinot nero', 'pinot bianco',
                'chardonnay', 'sauvignon', 'cabernet', 'merlot', 'syrah', 'shiraz',
                'prosecco', 'glera', 'moscato', 'corvina', 'rondinella',
                'garganega', 'trebbiano', 'malvasia', 'canaiolo', 'colorino',
                'fiano', 'greco', 'falanghina', 'aglianico', 'primitivo', 'negroamaro',
                'frapatto', 'nerello', 'carricante', 'catarratto', 'inzolia',
                'gewurztraminer', 'gewurtzraminer', 'riesling', 'traminer',
                'garnacha', 'tempranillo', 'grenache', 'mourvedre'
            }
            # Normalizza il termine per confronto (rimuovi apostrofi/spazi)
            wine_name_normalized = wine_name_lower.replace(' ', '').replace('\'', '').replace('-', '')
            is_likely_grape_variety = (
                wine_name_lower in common_grape_varieties or 
                wine_name_normalized in common_grape_varieties or
                any(gv in wine_name_lower for gv in common_grape_varieties if len(gv) >= 6)
            )
            
            # Determina se è un produttore (es. "ca del bosco")
            is_likely_producer = any(word in wine_name_lower for word in [' del ', ' di ', ' da ', 'ca ', 'ca\'', 'castello', 'tenuta', 'azienda'])
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: Cercando vino '{wine_name}' (pattern: '{wine_name_pattern}') "
                f"per user_id={user.id} in tabella {table_inventario} | "
                f"is_likely_grape_variety={is_likely_grape_variety}, is_likely_producer={is_likely_producer}"
            )
            
            # Costruisci ORDER BY con priorità in base al tipo di ricerca
            if is_likely_producer:
                # Per produttori, producer ha priorità più alta
                order_by_clause = """
                    CASE 
                        WHEN LOWER(producer) LIKE LOWER(:wine_name_pattern) THEN 1
                        WHEN LOWER(name) LIKE LOWER(:wine_name_pattern) THEN 2
                        WHEN LOWER(grape_variety) LIKE LOWER(:wine_name_pattern) THEN 3
                        ELSE 4
                    END ASC, name ASC
                """
            elif is_likely_grape_variety:
                # Per uvaggi, grape_variety ha priorità più alta rispetto a name
                order_by_clause = """
                    CASE 
                        WHEN LOWER(grape_variety) LIKE LOWER(:wine_name_pattern) THEN 1
                        WHEN LOWER(producer) LIKE LOWER(:wine_name_pattern) THEN 2
                        WHEN LOWER(name) LIKE LOWER(:wine_name_pattern) THEN 3
                        ELSE 4
                    END ASC, name ASC
                """
            else:
                # Per altri, name ha priorità più alta
                order_by_clause = """
                    CASE 
                        WHEN LOWER(name) LIKE LOWER(:wine_name_pattern) THEN 1
                        WHEN LOWER(producer) LIKE LOWER(:wine_name_pattern) THEN 2
                        WHEN LOWER(grape_variety) LIKE LOWER(:wine_name_pattern) THEN 3
                        ELSE 4
                    END ASC, name ASC
                """
            
            # Funzione per normalizzare plurali italiani per uvaggi e nomi
            # Es: "vermentini" -> "vermentino", "spumanti" -> "spumante"
            def normalize_plural_for_search(term: str) -> list[str]:
                """Ritorna lista di varianti: originale, senza plurale, con -o finale (per maschili)"""
                variants = [term]
                if len(term) > 2:
                    if term.endswith('i'):
                        # Plurale maschile: "vermentini" -> "vermentino"
                        base = term[:-1]
                        variants.append(base + 'o')  # vermentino
                        variants.append(base)  # vermentin (match parziale)
                    elif term.endswith('e'):
                        # Plurale femminile o altro: "bianche" -> "bianco"
                        base = term[:-1]
                        variants.append(base + 'a')  # bianca
                        variants.append(base + 'o')  # bianco
                        variants.append(base)  # bianch
                return list(set(variants))  # Rimuovi duplicati
            
            # Genera varianti plurali del nome vino
            search_variants = normalize_plural_for_search(wine_name_lower)  # Fix: definito prima dell'uso
            
            # Costruisci condizioni WHERE con varianti plurali
            where_conditions = [
                "LOWER(name) LIKE LOWER(:wine_name_pattern)",
                "LOWER(producer) LIKE LOWER(:wine_name_pattern)",
                "LOWER(grape_variety) LIKE LOWER(:wine_name_pattern)"
            ]
            
            # Aggiungi condizioni per varianti plurali (es. "vermentini" -> "vermentino")
            params_dict = {
                "user_id": user.id,
                "wine_name_pattern": wine_name_pattern
            }
            
            for idx, variant in enumerate(search_variants[1:], start=1):  # Skip primo (originale)
                variant_pattern = f"%{variant}%"
                param_key = f"wine_name_variant_{idx}"
                where_conditions.extend([
                    f"LOWER(name) LIKE LOWER(:{param_key})",
                    f"LOWER(grape_variety) LIKE LOWER(:{param_key})"
                ])
                params_dict[param_key] = variant_pattern
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: 🔍 Searching wine in database | "
                f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity}, "
                f"user_id={user_id}, business_name='{business_name}', "
                f"search_pattern='{wine_name_pattern}', variants={len(search_variants)}"
            )
            
            search_wine = sql_text(f"""
                SELECT id, name, producer, quantity 
                FROM {table_inventario} 
                WHERE user_id = :user_id 
                AND ({' OR '.join(where_conditions)})
                ORDER BY {order_by_clause}
                FOR UPDATE  -- ✅ LOCK row per serializzare accessi
                LIMIT 1
            """)
            
            res = await db.execute(search_wine, params_dict)
            wine_row = res.fetchone()

            if not wine_row:
                logger.warning(
                    f"[MOVEMENT] Job {job_id}: ❌ Wine not found in database | "
                    f"wine_name='{wine_name}', telegram_id={telegram_id}, business_name='{business_name}', "
                    f"search_pattern='{wine_name_pattern}', table={table_inventario}"
                )
                err = f"Vino '{wine_name}' non trovato"
                job.status = 'error'
                job.error_message = err
                job.completed_at = datetime.utcnow()
                await db.commit()
                
                # Notifica admin per movimento fallito (vino non trovato)
                try:
                    from admin_notifications import enqueue_admin_notification
                    
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=user_id,  # Mantenuto per retrocompatibilità notifiche
                        payload={
                            "business_name": business_name,
                            "error_type": "movement_wine_not_found",
                            "error_message": err,
                            "error_code": "MOVEMENT_WINE_NOT_FOUND",
                            "component": "gioia-processor",
                            "movement_type": movement_type,
                            "wine_name": wine_name,
                            "quantity": quantity,
                            "search_pattern": wine_name_pattern,
                            "user_id": user_id
                        },
                        correlation_id=job_id
                    )
                except Exception as notif_error:
                    logger.warning(f"Errore invio notifica admin: {notif_error}", exc_info=True)
                
                return

            # Accedi ai campi tramite chiavi (Row object)
            wine_id = wine_row[0]  # id
            wine_name_db = wine_row[1]  # name
            wine_producer = wine_row[2] if len(wine_row) > 2 else None  # producer
            quantity_before = wine_row[3] if len(wine_row) > 3 else 0  # quantity
            
            logger.info(
                f"[MOVEMENT] Job {job_id}: ✅ Wine found in database | "
                f"wine_id={wine_id}, wine_name='{wine_name_db}', "
                f"producer='{wine_producer or 'N/A'}', quantity_before={quantity_before}, requested={quantity}, movement_type={movement_type}"
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
                        
                        # Notifica admin per movimento fallito (quantità insufficiente)
                        try:
                            from admin_notifications import enqueue_admin_notification
                            
                            await enqueue_admin_notification(
                                event_type="error",
                                telegram_id=user_id,  # Mantenuto per retrocompatibilità notifiche
                                payload={
                                    "business_name": business_name,
                                    "error_type": "movement_insufficient_quantity",
                                    "error_message": error_msg,
                                    "error_code": "MOVEMENT_INSUFFICIENT_QUANTITY",
                                    "component": "gioia-processor",
                                    "movement_type": movement_type,
                                    "wine_name": wine_name_db,
                                    "wine_id": wine_id,
                                    "quantity_requested": quantity,
                                    "quantity_available": quantity_before,
                                    "user_id": user_id
                                },
                                correlation_id=job_id
                            )
                        except Exception as notif_error:
                            logger.warning(f"Errore invio notifica admin: {notif_error}", exc_info=True)
                        
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

                # Aggiorna/crea riga in "Storico vino" (fonte unica di verità per stock)
                if table_storico:
                    movement_date = datetime.utcnow()
                    movement_entry = {
                        "type": movement_type,
                        "quantity": quantity,
                        "date": movement_date.isoformat(),
                        "quantity_before": quantity_before,
                        "quantity_after": quantity_after
                    }
                    
                    # Cerca se esiste già una riga per questo vino
                    search_storico = sql_text(f"""
                        SELECT id, current_stock, history, total_consumi, total_rifornimenti
                        FROM {table_storico}
                        WHERE user_id = :user_id
                        AND wine_name = :wine_name
                        AND (wine_producer = :wine_producer OR (wine_producer IS NULL AND :wine_producer IS NULL))
                        FOR UPDATE
                        LIMIT 1
                    """)
                    result_storico = await db.execute(search_storico, {
                        "user_id": user.id,
                        "wine_name": wine_name_db,
                        "wine_producer": wine_producer
                    })
                    storico_row = result_storico.fetchone()
                    
                    if storico_row:
                        # Aggiorna riga esistente
                        # Parse history (potrebbe essere stringa JSON o già lista)
                        existing_history_raw = storico_row[2] or []
                        if isinstance(existing_history_raw, str):
                            existing_history = json.loads(existing_history_raw)
                        else:
                            existing_history = existing_history_raw if existing_history_raw else []
                        existing_history.append(movement_entry)
                        
                        new_total_consumi = storico_row[3] or 0
                        new_total_rifornimenti = storico_row[4] or 0
                        
                        if movement_type == 'consumo':
                            new_total_consumi += quantity
                        else:
                            new_total_rifornimenti += quantity
                        
                        update_storico = sql_text(f"""
                            UPDATE {table_storico}
                            SET current_stock = :current_stock,
                                history = :history::jsonb,
                                total_consumi = :total_consumi,
                                total_rifornimenti = :total_rifornimenti,
                                last_movement_date = :movement_date,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :storico_id
                        """)
                        await db.execute(update_storico, {
                            "current_stock": quantity_after,
                            "history": json.dumps(existing_history),
                            "total_consumi": new_total_consumi,
                            "total_rifornimenti": new_total_rifornimenti,
                            "movement_date": movement_date,
                            "storico_id": storico_row[0]
                        })
                        logger.info(f"[MOVEMENT] Job {job_id}: UPDATE storico vino eseguito")
                    else:
                        # Crea nuova riga
                        history = [movement_entry]
                        
                        insert_storico = sql_text(f"""
                            INSERT INTO {table_storico}
                                (user_id, wine_name, wine_producer, wine_vintage, current_stock, history,
                                 first_movement_date, last_movement_date, total_consumi, total_rifornimenti)
                            VALUES (:user_id, :wine_name, :wine_producer, :wine_vintage, :current_stock, :history::jsonb,
                                    :movement_date, :movement_date, :total_consumi, :total_rifornimenti)
                        """)
                        await db.execute(insert_storico, {
                            "user_id": user.id,
                            "wine_name": wine_name_db,
                            "wine_producer": wine_producer,
                            "wine_vintage": None,  # TODO: estrai da INVENTARIO se disponibile
                            "current_stock": quantity_after,
                            "history": json.dumps(history),
                            "movement_date": movement_date,
                            "total_consumi": quantity if movement_type == 'consumo' else 0,
                            "total_rifornimenti": quantity if movement_type == 'rifornimento' else 0
                        })
                        logger.info(f"[MOVEMENT] Job {job_id}: INSERT storico vino eseguito")

                await db.commit()
                logger.info(f"[MOVEMENT] Job {job_id}: Commit transazione completato")

            except Exception as te:
                await db.rollback()
                logger.error(
                    f"[MOVEMENT] Job {job_id}: Transaction error | user_id={user_id}, business={business_name}, "
                    f"wine_name={wine_name}, movement_type={movement_type}, quantity={quantity} | Error: {str(te)}",
                    exc_info=True
                )
                
                # Notifica admin per errore transazione movimento
                try:
                    from admin_notifications import enqueue_admin_notification
                    
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=user_id,  # Mantenuto per retrocompatibilità notifiche
                        payload={
                            "business_name": business_name,
                            "error_type": "movement_transaction_error",
                            "error_message": str(te),
                            "error_code": "MOVEMENT_TRANSACTION_ERROR",
                            "component": "gioia-processor",
                            "movement_type": movement_type,
                            "wine_name": wine_name,
                            "quantity": quantity,
                            "wine_id": wine_id if 'wine_id' in locals() else None,
                            "user_id": user_id
                        },
                        correlation_id=job_id
                    )
                except Exception as notif_error:
                    logger.warning(f"Errore invio notifica admin: {notif_error}", exc_info=True)
                
                raise

            processing_time = (datetime.utcnow() - start_time).total_seconds()

            result_data = {
                "status": "success",
                "movement_type": movement_type,
                "wine_id": wine_id,  # ID vino per tracciamento e correlazione log
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
                telegram_id=user_id  # Mantenuto per retrocompatibilità log
            )
            break

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        # Usa funzione helper che logga e notifica admin automaticamente
        from core.alerting import log_error_and_notify_admin
        await log_error_and_notify_admin(
            message=f"[MOVEMENT] Job {job_id}: {error_msg} | telegram_id={telegram_id}, business={business_name}, "
                    f"wine_name={wine_name}, movement_type={movement_type}, quantity={quantity}",
            telegram_id=telegram_id,
            correlation_id=job_id,
            component="gioia-processor",
            error_type="movement_unexpected_error",
            exc_info=True,
            business_name=business_name,
            job_id=job_id,
            movement_type=movement_type,
            wine_name=wine_name,
            quantity=quantity,
            error_code="MOVEMENT_UNEXPECTED_ERROR"
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
        except Exception as update_error:
            logger.error(f"[MOVEMENT] Errore aggiornamento job {job_id} a status 'error': {update_error}", exc_info=True)


@router.post("/process-movement")
async def process_movement(
    user_id: int = Form(...),
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
            f"Creating movement job for user_id: {user_id}, business: {business_name}, {movement_type} {quantity} {wine_name}"
        )

        if movement_type not in ['consumo', 'rifornimento']:
            raise HTTPException(status_code=400, detail="movement_type deve essere 'consumo' o 'rifornimento'")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity deve essere > 0")

        job_id = str(uuid.uuid4())

        async for db in get_db():
            job = ProcessingJob(
                job_id=job_id,
                telegram_id=user_id,  # ProcessingJob usa ancora telegram_id per retrocompatibilità schema DB
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
                user_id=user_id,
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
                        "wine_id": result_data.get("wine_id"),  # ID vino per tracciamento
                        "wine_name": result_data.get("wine_name", wine_name),
                        "quantity": quantity,
                        "quantity_before": result_data.get("quantity_before", 0),
                        "quantity_after": result_data.get("quantity_after", 0),
                        "movement_type": movement_type,
                        "user_id": user_id,
                        "message": f"Movimento {movement_type} completato con successo"
                    }
                elif job.status == 'error':
                    # Job fallito
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "error": job.error_message or "Errore sconosciuto durante l'elaborazione",
                        "error_message": job.error_message or "Errore sconosciuto durante l'elaborazione",
                        "user_id": user_id
                    }
                else:
                    # Stato inatteso
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "error": f"Stato job inatteso: {job.status}",
                        "error_message": f"Stato job inatteso: {job.status}",
                        "user_id": user_id
                    }
                break
        except Exception as e:
            logger.error(
                f"Error processing movement synchronously: {e} | "
                f"user_id={user_id}, wine_name={wine_name}, "
                f"movement_type={movement_type}, quantity={quantity}",
                exc_info=True
            )
            return {
                "status": "error",
                "job_id": job_id,
                "error": f"Errore durante elaborazione: {str(e)}",
                "error_message": f"Errore durante elaborazione: {str(e)}",
                "user_id": user_id
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating movement job: {e}", exc_info=True)
        
        # Notifica admin per errore creazione job movimento
        try:
            from admin_notifications import enqueue_admin_notification
            
            await enqueue_admin_notification(
                event_type="error",
                telegram_id=user_id,  # Mantenuto per retrocompatibilità notifiche
                payload={
                    "business_name": business_name,
                    "error_type": "movement_job_creation_error",
                    "error_message": str(e),
                    "error_code": "MOVEMENT_JOB_CREATION_ERROR",
                    "component": "gioia-processor",
                    "movement_type": movement_type,
                    "wine_name": wine_name,
                    "quantity": quantity,
                    "user_id": user_id
                },
                correlation_id=None
            )
        except Exception as notif_error:
            logger.warning(f"Errore invio notifica admin: {notif_error}")
        
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

