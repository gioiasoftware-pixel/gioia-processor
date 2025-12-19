"""
Modulo migrazioni database - funzioni importabili direttamente
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import text as sql_text, select
from core.database import get_db, ensure_user_tables_from_telegram_id, User, AsyncSessionLocal

logger = logging.getLogger(__name__)


def find_migration_file(filename: str) -> Path:
    """
    Trova il file di migrazione cercando in percorsi multipli.
    
    Cerca in ordine:
    1. Percorso relativo a __file__ (core/migrations.py -> migrations/)
    2. Directory corrente di lavoro (cwd/migrations/)
    3. Percorso assoluto /app/migrations/ (Docker)
    4. Percorso relativo migrations/ dalla root progetto
    
    Returns:
        Path al file trovato
        
    Raises:
        FileNotFoundError se il file non viene trovato
    """
    # Lista di percorsi base da provare
    base_paths = [
        Path(__file__).parent.parent / "migrations",  # core/ -> migrations/
        Path(os.getcwd()) / "migrations",  # Directory corrente
        Path("/app") / "migrations",  # Docker standard
        Path("/app/gioia-processor") / "migrations",  # Docker con subdirectory
    ]
    
    # Aggiungi anche percorsi relativi dalla directory corrente
    current_dir = Path(os.getcwd())
    if current_dir.name == "gioia-processor":
        base_paths.insert(1, current_dir / "migrations")
    elif (current_dir / "gioia-processor").exists():
        base_paths.insert(1, current_dir / "gioia-processor" / "migrations")
    
    # Cerca il file in tutti i percorsi
    for base_path in base_paths:
        migration_file = base_path / filename
        if migration_file.exists() and migration_file.is_file():
            logger.debug(f"[MIGRATION] File trovato: {migration_file}")
            return migration_file
    
    # Se non trovato, prova a cercare ricorsivamente dalla directory corrente
    cwd = Path(os.getcwd())
    for root, dirs, files in os.walk(cwd):
        if "migrations" in dirs:
            migration_file = Path(root) / "migrations" / filename
            if migration_file.exists() and migration_file.is_file():
                logger.debug(f"[MIGRATION] File trovato (ricerca ricorsiva): {migration_file}")
                return migration_file
    
    # Nessun file trovato
    searched_paths = [str(p / filename) for p in base_paths]
    raise FileNotFoundError(
        f"File migrazione '{filename}' non trovato. Percorsi cercati: {searched_paths}"
    )


async def check_migration_006_applied(session) -> bool:
    """
    Verifica se la migrazione 006 (telegram_id nullable) è già stata applicata.
    
    Controlla:
    1. Se telegram_id è nullable nella tabella users
    2. Se l'indice unique parziale uq_users_telegram_id esiste
    
    Returns:
        True se migrazione già applicata, False altrimenti
    """
    try:
        # Verifica 1: Controlla se telegram_id è nullable
        check_nullable = sql_text("""
            SELECT is_nullable 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'users' 
            AND column_name = 'telegram_id'
        """)
        result = await session.execute(check_nullable)
        nullable_result = result.scalar_one_or_none()
        
        if nullable_result != 'YES':
            logger.info("[MIGRATION 006] telegram_id non è nullable - migrazione necessaria")
            return False
        
        # Verifica 2: Controlla se l'indice unique parziale esiste
        check_index = sql_text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'users' 
            AND indexname = 'uq_users_telegram_id'
        """)
        result = await session.execute(check_index)
        index_exists = result.scalar_one_or_none()
        
        if not index_exists:
            logger.info("[MIGRATION 006] Indice unique parziale non trovato - migrazione necessaria")
            return False
        
        logger.info("[MIGRATION 006] Migrazione già applicata (telegram_id nullable e indice presente)")
        return True
        
    except Exception as e:
        logger.warning(f"[MIGRATION 006] Errore durante verifica migrazione: {e}", exc_info=True)
        # In caso di errore, assumiamo che la migrazione non sia applicata (safe fallback)
        return False


async def migrate_006_telegram_id_nullable():
    """
    Migrazione 006: Rende telegram_id nullable in users.
    
    Esegue automaticamente la migrazione SQL solo se non già applicata.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Verifica se migrazione già applicata
            if await check_migration_006_applied(session):
                logger.info("[MIGRATION 006] Migrazione già applicata - skip")
                return True
            
            logger.info("[MIGRATION 006] Avvio migrazione: telegram_id nullable")
            
            # Leggi file migrazione SQL
            project_root = Path(__file__).parent.parent
            migration_file = project_root / "migrations" / "006_make_telegram_id_nullable.sql"
            
            if not migration_file.exists():
                logger.error(f"[MIGRATION 006] File migrazione non trovato: {migration_file}")
                return False
            
            with open(migration_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # Rimuovi solo commenti iniziali, mantieni tutto il resto
            lines = sql_content.split('\n')
            sql_clean = '\n'.join([
                line for line in lines 
                if not line.strip().startswith('--') or 'Esegui con:' in line
            ])
            
            # Esegui migrazione
            logger.info("[MIGRATION 006] Eseguendo statement SQL...")
            await session.execute(sql_text(sql_clean))
            await session.commit()
            
            # Verifica che la migrazione sia stata applicata correttamente
            if await check_migration_006_applied(session):
                logger.info("[MIGRATION 006] ✅ Migrazione completata con successo!")
                return True
            else:
                logger.error("[MIGRATION 006] ❌ Migrazione eseguita ma verifica fallita")
                return False
                
    except Exception as e:
        logger.error(f"[MIGRATION 006] ❌ Errore durante migrazione: {e}", exc_info=True)
        try:
            async with AsyncSessionLocal() as session:
                await session.rollback()
        except:
            pass
        return False


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
                table_consumi_name = f'"{user.id}/{user.business_name} Consumi e rifornimenti"'
                
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
                
                result = await db.execute(query_movements, {"user_id": user.id})
                movements = result.fetchall()
                
                if not movements:
                    logger.info(f"[MIGRATION] Nessun movimento per utente {user_id} - tabella Storico vino creata ma vuota")
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
                        "user_id": user.id,
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
                            "user_id": user_id,
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
                    f"[MIGRATION] Migrati {len(wines_dict)} vini per utente {user_id} "
                    f"({len(movements)} movimenti totali)"
                )
                
            except Exception as e:
                try:
                    await db.rollback()
                except Exception as rollback_error:
                    logger.warning(f"[MIGRATION] Errore durante rollback per utente {user_id}: {rollback_error}")
                logger.error(
                    f"[MIGRATION] Errore migrazione utente {user_id}: {e}",
                    exc_info=True
                )
                continue
        break
