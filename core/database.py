"""
Database core module per gioia-processor.

Gestisce connessioni, tabelle dinamiche e batch insert/upsert.
Migrato da database.py con miglioramenti batch.
"""
import logging
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text as sql_text, select
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.config import get_config

logger = logging.getLogger(__name__)

# Base per i modelli
Base = declarative_base()


class User(Base):
    """Modello per gli utenti del bot"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Dati onboarding
    business_name = Column(String(200))
    business_type = Column(String(100))
    location = Column(String(200))
    phone = Column(String(50))
    email = Column(String(200))
    onboarding_completed = Column(Boolean, default=False)


class ProcessingJob(Base):
    """Job di elaborazione inventario asincrono"""
    __tablename__ = 'processing_jobs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Dati utente
    telegram_id = Column(Integer, nullable=False, index=True)
    business_name = Column(String(200))
    
    # Stato elaborazione
    status = Column(String(20), nullable=False, default='pending')
    file_type = Column(String(20))
    file_name = Column(String(200))
    file_size_bytes = Column(Integer)
    
    # Progress
    total_wines = Column(Integer, default=0)
    processed_wines = Column(Integer, default=0)
    saved_wines = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    
    # Risultati (JSON)
    result_data = Column(Text)
    error_message = Column(Text)
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_method = Column(String(50))
    
    # Idempotenza
    client_msg_id = Column(String(200))
    update_id = Column(Integer)


# Configurazione database
def get_database_url() -> str:
    """Ottiene DATABASE_URL dalla configurazione."""
    config = get_config()
    return config.database_url


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/gioia_processor")

# Engine asincrono per PostgreSQL
engine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False
)

# Session factory asincrona
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db():
    """Dependency per ottenere sessione database"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_user_table_name(telegram_id: int, business_name: str, table_type: str) -> str:
    """
    Genera nome tabella nel formato: "{telegram_id}/{business_name} {table_type}"
    
    Args:
        telegram_id: ID Telegram dell'utente
        business_name: Nome del locale
        table_type: Tipo tabella ("INVENTARIO", "INVENTARIO backup", "LOG interazione", "Consumi e rifornimenti")
    
    Returns:
        Nome tabella quotato per PostgreSQL
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    table_name = f'"{telegram_id}/{business_name} {table_type}"'
    return table_name


async def ensure_user_tables(session, telegram_id: int, business_name: str) -> dict:
    """
    Crea le 4 tabelle utente nello schema public se non esistono.
    
    Tabelle create:
    1. "{telegram_id}/{business_name} INVENTARIO" - Inventario vini
    2. "{telegram_id}/{business_name} INVENTARIO backup" - Backup inventario
    3. "{telegram_id}/{business_name} LOG interazione" - Log interazioni bot
    4. "{telegram_id}/{business_name} Consumi e rifornimenti" - Consumi e rifornimenti
    
    Ritorna dict con nomi tabelle create.
    """
    if not business_name:
        business_name = "Upload Manuale"
    
    try:
        # Verifica e crea/aggiorna utente nella tabella users
        upsert_user = sql_text("""
            INSERT INTO users (telegram_id, business_name, created_at, updated_at)
            VALUES (:telegram_id, :business_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET 
                business_name = EXCLUDED.business_name, 
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)
        result_user = await session.execute(upsert_user, {"telegram_id": telegram_id, "business_name": business_name})
        user_id = result_user.scalar_one()
        logger.info(f"User {telegram_id} ensured with id {user_id}, business_name: {business_name}")
        
        await session.commit()
        
        # Nomi tabelle
        table_inventario = get_user_table_name(telegram_id, business_name, "INVENTARIO")
        table_backup = get_user_table_name(telegram_id, business_name, "INVENTARIO backup")
        table_log = get_user_table_name(telegram_id, business_name, "LOG interazione")
        table_consumi = get_user_table_name(telegram_id, business_name, "Consumi e rifornimenti")
        
        # Verifica se almeno una tabella esiste
        table_name_check = f"{telegram_id}/{business_name} INVENTARIO"
        check_table = sql_text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = :table_name
        """)
        result = await session.execute(check_table, {"table_name": table_name_check})
        table_exists = result.scalar_one_or_none()
        
        if not table_exists:
            # Crea tabella INVENTARIO
            create_inventario = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_inventario} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    producer VARCHAR(200),
                    supplier VARCHAR(200),
                    vintage INTEGER,
                    grape_variety VARCHAR(200),
                    region VARCHAR(200),
                    country VARCHAR(100),
                    wine_type VARCHAR(50),
                    classification VARCHAR(100),
                    quantity INTEGER DEFAULT 0,
                    min_quantity INTEGER DEFAULT 0,
                    cost_price FLOAT,
                    selling_price FLOAT,
                    alcohol_content FLOAT,
                    description TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_inventario)
            
            # Crea indici per performance
            create_indexes = sql_text(f"""
                CREATE INDEX IF NOT EXISTS idx_{telegram_id}_name ON {table_inventario} (name);
                CREATE INDEX IF NOT EXISTS idx_{telegram_id}_winery ON {table_inventario} (producer);
                CREATE INDEX IF NOT EXISTS idx_{telegram_id}_vintage ON {table_inventario} (vintage);
                CREATE INDEX IF NOT EXISTS idx_{telegram_id}_type ON {table_inventario} (wine_type);
                CREATE INDEX IF NOT EXISTS idx_{telegram_id}_updated ON {table_inventario} (updated_at);
            """)
            await session.execute(create_indexes)
            
            # Crea tabella INVENTARIO backup
            create_backup = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_backup} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    backup_name VARCHAR(200) NOT NULL,
                    backup_data TEXT NOT NULL,
                    backup_type VARCHAR(20) DEFAULT 'initial',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_backup)
            
            # Crea tabella LOG interazione
            create_log = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_log} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    interaction_type VARCHAR(50) NOT NULL,
                    interaction_data TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_log)
            
            # Crea tabella Consumi e rifornimenti
            create_consumi = sql_text(f"""
                CREATE TABLE IF NOT EXISTS {table_consumi} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    wine_name VARCHAR(200) NOT NULL,
                    wine_producer VARCHAR(200),
                    movement_type VARCHAR(20) NOT NULL,
                    quantity_change INTEGER NOT NULL,
                    quantity_before INTEGER NOT NULL,
                    quantity_after INTEGER NOT NULL,
                    notes TEXT,
                    movement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_consumi)
            
            logger.info(f"Created tables for {telegram_id}/{business_name}: INVENTARIO, INVENTARIO backup, LOG interazione, Consumi e rifornimenti")
        else:
            # Tabella esiste già - verifica colonna supplier
            try:
                check_supplier = sql_text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = :table_name
                    AND column_name = 'supplier'
                """)
                result_supplier = await session.execute(check_supplier, {"table_name": table_name_check})
                supplier_exists = result_supplier.scalar_one_or_none()
                
                if not supplier_exists:
                    alter_table = sql_text(f"ALTER TABLE {table_inventario} ADD COLUMN IF NOT EXISTS supplier VARCHAR(200)")
                    await session.execute(alter_table)
                    logger.info(f"Added supplier column to existing table {table_inventario}")
            except Exception as e:
                logger.warning(f"Error checking/adding supplier column for {table_inventario}: {e}")
            
            logger.info(f"Tables already exist for {telegram_id}/{business_name}")
        
        return {
            "inventario": table_inventario,
            "backup": table_backup,
            "log": table_log,
            "consumi": table_consumi
        }
        
    except Exception as e:
        logger.error(f"Error ensuring user tables for {telegram_id}/{business_name}: {e}")
        raise


async def batch_insert_wines(
    session,
    table_name: str,
    wines: List[Dict[str, Any]],
    batch_size: Optional[int] = None,
    user_id: int = None
) -> tuple[int, int]:
    """
    Inserisce vini in batch usando asyncpg con transaction atomica.
    
    Conforme a "Update processor.md" - Batch insert atomici.
    
    Args:
        session: Sessione database async
        table_name: Nome tabella inventario (già quotato)
        wines: Lista dizionari con dati vini (schema WineItemModel)
        batch_size: Dimensione batch (default da config, 500)
        user_id: ID utente (necessario per foreign key)
    
    Returns:
        Tuple (saved_count, error_count)
    """
    config = get_config()
    if batch_size is None:
        batch_size = config.db_insert_batch_size
    
    saved_count = 0
    error_count = 0
    
    if not wines:
        return saved_count, error_count
    
    try:
        # Processa in batch
        for i in range(0, len(wines), batch_size):
            batch = wines[i:i + batch_size]
            
            try:
                # Prepara valori per batch insert
                values_list = []
                for wine in batch:
                    # Normalizza dati vino (compatibile con WineItemModel)
                    values = {
                        "user_id": user_id,
                        "name": wine.get("name", ""),
                        "producer": wine.get("winery") or wine.get("producer"),
                        "supplier": wine.get("supplier"),
                        "vintage": wine.get("vintage"),
                        "grape_variety": wine.get("grape_variety"),
                        "region": wine.get("region"),
                        "country": wine.get("country"),
                        "wine_type": wine.get("type") or wine.get("wine_type"),
                        "classification": wine.get("classification"),
                        "quantity": wine.get("qty") or wine.get("quantity", 0),
                        "min_quantity": wine.get("min_quantity", 0),
                        "cost_price": wine.get("cost_price"),
                        "selling_price": wine.get("price") or wine.get("selling_price"),
                        "alcohol_content": wine.get("alcohol_content"),
                        "description": wine.get("description"),
                        "notes": wine.get("notes"),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    values_list.append(values)
                
                # Batch insert usando executemany (più efficiente)
                insert_stmt = sql_text(f"""
                    INSERT INTO {table_name} 
                    (user_id, name, producer, supplier, vintage, grape_variety, region, country, 
                     wine_type, classification, quantity, min_quantity, cost_price, selling_price, 
                     alcohol_content, description, notes, created_at, updated_at)
                    VALUES 
                    (:user_id, :name, :producer, :supplier, :vintage, :grape_variety, :region, :country,
                     :wine_type, :classification, :quantity, :min_quantity, :cost_price, :selling_price,
                     :alcohol_content, :description, :notes, :created_at, :updated_at)
                """)
                
                await session.execute(insert_stmt, values_list)
                saved_count += len(batch)
                
                logger.debug(f"[BATCH_INSERT] Inserted batch {i//batch_size + 1}: {len(batch)} wines")
                
            except Exception as batch_error:
                error_count += len(batch)
                logger.error(f"[BATCH_INSERT] Error inserting batch {i//batch_size + 1}: {batch_error}", exc_info=True)
                # Continua con prossimo batch
                continue
        
        logger.info(f"[BATCH_INSERT] Completed: {saved_count} saved, {error_count} errors out of {len(wines)} total")
        return saved_count, error_count
        
    except Exception as e:
        logger.error(f"[BATCH_INSERT] Fatal error: {e}", exc_info=True)
        raise


async def create_tables():
    """
    Crea solo tabelle condivise nello schema public: User e ProcessingJob.
    """
    try:
        async with engine.begin() as conn:
            # Crea solo le tabelle dei modelli Base esistenti (User e ProcessingJob)
            await conn.run_sync(Base.metadata.create_all)
            
            # AUTO-MIGRAZIONE: Aggiungi colonne mancanti a processing_jobs per idempotenza
            try:
                check_client_msg_id = sql_text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'processing_jobs' AND column_name = 'client_msg_id'
                """)
                result = await conn.execute(check_client_msg_id)
                client_msg_id_exists = result.scalar() is not None
                
                if not client_msg_id_exists:
                    add_client_msg_id = sql_text("ALTER TABLE processing_jobs ADD COLUMN client_msg_id VARCHAR(200)")
                    await conn.execute(add_client_msg_id)
                    logger.info("Added client_msg_id column to processing_jobs")
                
                check_update_id = sql_text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'processing_jobs' AND column_name = 'update_id'
                """)
                result = await conn.execute(check_update_id)
                update_id_exists = result.scalar() is not None
                
                if not update_id_exists:
                    add_update_id = sql_text("ALTER TABLE processing_jobs ADD COLUMN update_id INTEGER")
                    await conn.execute(add_update_id)
                    logger.info("Added update_id column to processing_jobs")
                
                # Crea indici per performance
                try:
                    create_idx = sql_text("""
                        CREATE INDEX IF NOT EXISTS idx_jobs_user_client 
                        ON processing_jobs (telegram_id, client_msg_id)
                        WHERE client_msg_id IS NOT NULL
                    """)
                    await conn.execute(create_idx)
                    
                    create_unique_idx = sql_text("""
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_user_client 
                        ON processing_jobs (telegram_id, client_msg_id)
                        WHERE client_msg_id IS NOT NULL
                    """)
                    await conn.execute(create_unique_idx)
                    logger.info("Created indexes for client_msg_id on processing_jobs")
                except Exception as idx_error:
                    logger.warning(f"Index creation skipped (may already exist): {idx_error}")
                    
            except Exception as migrate_error:
                logger.warning(f"Auto-migration for processing_jobs skipped: {migrate_error}")
        
        logger.info("Database tables created successfully (public schema): users, processing_jobs")
        logger.info("Note: Tabelle inventario vengono create per-utente nello schema public via ensure_user_tables()")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

