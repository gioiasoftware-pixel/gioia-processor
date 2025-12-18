"""
Modulo migrazioni database - funzioni importabili direttamente
"""
import json
import logging
from datetime import datetime
from sqlalchemy import text as sql_text, select
from core.database import get_db, ensure_user_tables_from_telegram_id, User

logger = logging.getLogger(__name__)


async def migrate_wine_history():
    """
    Migra storico vini da "Consumi e rifornimenti" a "Storico vino"
    """
    async for db in get_db():
        # Trova tutti gli utenti
        stmt = select(User)
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        logger.info(f"[MIGRATION] Trovati {len(users)} utenti da migrare")
        
        for user in users:
            try:
                if not user.telegram_id or not user.business_name:
                    logger.info(f"[MIGRATION] Skip utente {user.id}: telegram_id o business_name mancante")
                    continue
                
                logger.info(f"[MIGRATION] Processo utente {user.id} (telegram_id={user.telegram_id}, business_name={user.business_name})")
                
                # Assicura che tabelle esistano (crea "Storico vino" se non esiste)
                # IMPORTANTE: Questo crea la tabella "Storico vino" anche se non esiste
                user_tables = await ensure_user_tables_from_telegram_id(db, user.telegram_id, user.business_name)
                table_consumi = user_tables["consumi"]
                table_storico = user_tables.get("storico")
                
                if not table_storico:
                    logger.error(f"[MIGRATION] ✗✗✗ Tabella Storico vino non creata per utente {user.id} - questo non dovrebbe succedere!")
                    continue
                
                logger.info(f"[MIGRATION] ✓ Tabella Storico vino verificata/creata: {table_storico}")
                
                # Leggi tutti i movimenti per questo utente
                query_movements = sql_text(f"""
                    SELECT 
                        wine_name,
                        wine_producer,
                        movement_type,
                        quantity_change,
                        quantity_before,
                        quantity_after,
                        movement_date
                    FROM {table_consumi}
                    WHERE user_id = :user_id
                    ORDER BY movement_date ASC
                """)
                
                result = await db.execute(query_movements, {"user_id": user.id})
                movements = result.fetchall()
                
                if not movements:
                    logger.info(f"[MIGRATION] Nessun movimento per utente {user.id} - tabella Storico vino creata ma vuota")
                    # Commit per assicurarsi che la tabella creata sia persistita
                    await db.commit()
                    continue
                
                # Raggruppa per vino (wine_name + wine_producer)
                wines_dict = {}
                
                for mov in movements:
                    wine_key = (mov.wine_name, mov.wine_producer or "")
                    
                    if wine_key not in wines_dict:
                        wines_dict[wine_key] = {
                            "wine_name": mov.wine_name,
                            "wine_producer": mov.wine_producer,
                            "movements": [],
                            "current_stock": 0,
                            "first_movement_date": None,
                            "last_movement_date": None
                        }
                    
                    # Aggiungi movimento
                    wines_dict[wine_key]["movements"].append({
                        "type": mov.movement_type,
                        "quantity": abs(mov.quantity_change),
                        "date": mov.movement_date.isoformat() if mov.movement_date else None,
                        "quantity_before": mov.quantity_before,
                        "quantity_after": mov.quantity_after
                    })
                    
                    # Aggiorna current_stock (ultimo quantity_after)
                    wines_dict[wine_key]["current_stock"] = mov.quantity_after
                    
                    # Aggiorna date
                    if not wines_dict[wine_key]["first_movement_date"]:
                        wines_dict[wine_key]["first_movement_date"] = mov.movement_date
                    wines_dict[wine_key]["last_movement_date"] = mov.movement_date
                
                # Inserisci/aggiorna in "Storico vino"
                for wine_key, wine_data in wines_dict.items():
                    # Calcola totali
                    total_consumi = sum(
                        m["quantity"] for m in wine_data["movements"] 
                        if m["type"] == "consumo"
                    )
                    total_rifornimenti = sum(
                        m["quantity"] for m in wine_data["movements"] 
                        if m["type"] == "rifornimento"
                    )
                    
                    # Verifica se esiste già
                    check_existing = sql_text(f"""
                        SELECT id FROM {table_storico}
                        WHERE user_id = :user_id
                        AND wine_name = :wine_name
                        AND (wine_producer = :wine_producer OR (wine_producer IS NULL AND :wine_producer IS NULL))
                        LIMIT 1
                    """)
                    result = await db.execute(check_existing, {
                        "user_id": user.id,
                        "wine_name": wine_data["wine_name"],
                        "wine_producer": wine_data["wine_producer"]
                    })
                    existing = result.fetchone()
                    
                    if existing:
                        # UPDATE
                        update_storico = sql_text(f"""
                            UPDATE {table_storico}
                            SET current_stock = :current_stock,
                                history = :history::jsonb,
                                total_consumi = :total_consumi,
                                total_rifornimenti = :total_rifornimenti,
                                first_movement_date = :first_date,
                                last_movement_date = :last_date,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :storico_id
                        """)
                        await db.execute(update_storico, {
                            "current_stock": wine_data["current_stock"],
                            "history": json.dumps(wine_data["movements"]),
                            "total_consumi": total_consumi,
                            "total_rifornimenti": total_rifornimenti,
                            "first_date": wine_data["first_movement_date"],
                            "last_date": wine_data["last_movement_date"],
                            "storico_id": existing[0]
                        })
                    else:
                        # INSERT
                        insert_storico = sql_text(f"""
                            INSERT INTO {table_storico}
                                (user_id, wine_name, wine_producer, current_stock, history,
                                 first_movement_date, last_movement_date, total_consumi, total_rifornimenti)
                            VALUES (:user_id, :wine_name, :wine_producer, :current_stock, :history::jsonb,
                                    :first_date, :last_date, :total_consumi, :total_rifornimenti)
                        """)
                        await db.execute(insert_storico, {
                            "user_id": user.id,
                            "wine_name": wine_data["wine_name"],
                            "wine_producer": wine_data["wine_producer"],
                            "current_stock": wine_data["current_stock"],
                            "history": json.dumps(wine_data["movements"]),
                            "first_date": wine_data["first_movement_date"],
                            "last_date": wine_data["last_movement_date"],
                            "total_consumi": total_consumi,
                            "total_rifornimenti": total_rifornimenti
                        })
                
                await db.commit()
                logger.info(
                    f"[MIGRATION] Migrati {len(wines_dict)} vini per utente {user.id} "
                    f"({len(movements)} movimenti totali)"
                )
                
            except Exception as e:
                await db.rollback()
                logger.error(
                    f"[MIGRATION] Errore migrazione utente {user.id}: {e}",
                    exc_info=True
                )
                continue
        break
