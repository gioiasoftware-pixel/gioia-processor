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
    CREA DIRETTAMENTE le tabelle "Storico vino" per gli utenti esistenti usando formato user_id
    """
    async for db in get_db():
        # Trova tutti gli utenti
        stmt = select(User)
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        logger.info(f"[MIGRATION] Trovati {len(users)} utenti da migrare")
        
        for user in users:
            # Salva user_id prima di qualsiasi operazione che potrebbe fallire
            user_id = user.id
            user_business_name = user.business_name
            
            try:
                if not user_business_name:
                    logger.info(f"[MIGRATION] Skip utente {user_id}: business_name mancante")
                    continue
                
                logger.info(f"[MIGRATION] Processo utente {user_id} (business_name={user_business_name})")
                
                # CREA DIRETTAMENTE la tabella "Storico vino" usando formato user_id
                table_storico_name = f'"{user_id}/{user_business_name} Storico vino"'
                
                # Verifica se esiste già
                check_storico = sql_text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = :table_name
                """)
                result_storico = await db.execute(check_storico, {"table_name": f"{user_id}/{user_business_name} Storico vino"})
                storico_exists = result_storico.scalar_one_or_none()
                
                if not storico_exists:
                    # Crea direttamente la tabella Storico vino con formato user_id
                    create_storico = sql_text(f"""
                        CREATE TABLE {table_storico_name} (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            wine_name VARCHAR(200) NOT NULL,
                            wine_producer VARCHAR(200),
                            wine_vintage INTEGER,
                            current_stock INTEGER NOT NULL DEFAULT 0,
                            history JSONB NOT NULL DEFAULT '[]'::jsonb,
                            first_movement_date TIMESTAMP,
                            last_movement_date TIMESTAMP,
                            total_consumi INTEGER DEFAULT 0,
                            total_rifornimenti INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, wine_name, wine_producer, wine_vintage)
                        )
                    """)
                    await db.execute(create_storico)
                    
                    # Indici per Storico vino
                    indexes_storico = [
                        f"CREATE INDEX IF NOT EXISTS idx_storico_{user_id}_wine_name ON {table_storico_name} (wine_name)",
                        f"CREATE INDEX IF NOT EXISTS idx_storico_{user_id}_wine_producer ON {table_storico_name} (wine_producer)",
                        f"CREATE INDEX IF NOT EXISTS idx_storico_{user_id}_last_movement ON {table_storico_name} (last_movement_date)",
                        f"CREATE INDEX IF NOT EXISTS idx_storico_{user_id}_history_gin ON {table_storico_name} USING GIN (history)"
                    ]
                    for index_sql in indexes_storico:
                        await db.execute(sql_text(index_sql))
                    
                    logger.info(f"[MIGRATION] ✓✓✓ Tabella Storico vino creata: {table_storico_name}")
                    await db.commit()
                else:
                    logger.info(f"[MIGRATION] ✓ Tabella Storico vino già esistente: {table_storico_name}")
                
                # Nome tabella consumi (formato user_id)
                table_consumi_name = f'"{user_id}/{user_business_name} Consumi e rifornimenti"'
                
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
                    FROM {table_consumi_name}
                    WHERE user_id = :user_id
                    ORDER BY movement_date ASC
                """)
                
                result = await db.execute(query_movements, {"user_id": user_id})
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
                        SELECT id FROM {table_storico_name}
                        WHERE user_id = :user_id
                        AND wine_name = :wine_name
                        AND (wine_producer = :wine_producer OR (wine_producer IS NULL AND :wine_producer IS NULL))
                        LIMIT 1
                    """)
                    result = await db.execute(check_existing, {
                        "user_id": user_id,
                        "wine_name": wine_data["wine_name"],
                        "wine_producer": wine_data["wine_producer"]
                    })
                    existing = result.fetchone()
                    
                    if existing:
                        # UPDATE
                        update_storico = sql_text(f"""
                            UPDATE {table_storico_name}
                            SET current_stock = :current_stock,
                                history = CAST(:history AS jsonb),
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
                            INSERT INTO {table_storico_name}
                                (user_id, wine_name, wine_producer, current_stock, history,
                                 first_movement_date, last_movement_date, total_consumi, total_rifornimenti)
                            VALUES (:user_id, :wine_name, :wine_producer, :current_stock, CAST(:history AS jsonb),
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
