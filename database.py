from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text as sql_text
from datetime import datetime
import os
import logging
import re

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
    business_type = Column(String(100))  # enoteca, ristorante, bar, etc.
    location = Column(String(200))
    phone = Column(String(50))
    email = Column(String(200))
    onboarding_completed = Column(Boolean, default=False)
    
    # Relazioni rimosse - i vini sono ora in schemi separati per utente

# NOTA: I modelli Wine, InventoryBackup, InventoryLog NON sono più modelli Base
# Vengono creati dinamicamente negli schemi utente usando SQL diretto in ensure_user_schema()
# Questo garantisce isolamento completo dei dati per ogni utente.
#
# Le tabelle wines, inventory_backups, inventory_logs vengono create nello schema:
# user_{telegram_id}_{business_name_sanitized}
# con foreign key verso public.users(id)

class ProcessingJob(Base):
    """Job di elaborazione inventario asincrono"""
    __tablename__ = 'processing_jobs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(50), unique=True, nullable=False, index=True)  # UUID o ID univoco
    
    # Dati utente
    telegram_id = Column(Integer, nullable=False, index=True)
    business_name = Column(String(200))
    
    # Stato elaborazione
    status = Column(String(20), nullable=False, default='pending')  # pending, processing, completed, error
    file_type = Column(String(20))  # csv, excel, image
    file_name = Column(String(200))
    file_size_bytes = Column(Integer)
    
    # Progress
    total_wines = Column(Integer, default=0)
    processed_wines = Column(Integer, default=0)
    saved_wines = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    
    # Risultati (JSON)
    result_data = Column(Text)  # JSON con risultato completo
    error_message = Column(Text)
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_method = Column(String(50))  # csv_ai_enhanced, excel_ai_enhanced, ocr_ai_enhanced

# Configurazione database
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

def sanitize_schema_name(name: str) -> str:
    """
    Sanitizza nome per schema PostgreSQL.
    Rimuove caratteri speciali, converte in lowercase, sostituisce spazi con underscore.
    Limita a 63 caratteri (limite PostgreSQL per identificatori).
    """
    if not name:
        return "unnamed"
    
    # Converti in lowercase
    sanitized = name.lower()
    
    # Rimuovi caratteri speciali (mantieni solo lettere, numeri, underscore, spazi)
    sanitized = re.sub(r'[^a-z0-9_\s]', '', sanitized)
    
    # Sostituisci spazi multipli con underscore singolo
    sanitized = re.sub(r'\s+', '_', sanitized)
    
    # Rimuovi underscore multipli
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Rimuovi underscore iniziali/finali
    sanitized = sanitized.strip('_')
    
    # Limita a 63 caratteri (limite PostgreSQL)
    if len(sanitized) > 63:
        sanitized = sanitized[:63].rstrip('_')
    
    # Se vuoto dopo sanitizzazione, usa default
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized

def get_user_schema_name(telegram_id: int, business_name: str) -> str:
    """
    Genera nome schema per utente: user_{telegram_id}_{business_name_sanitized}
    """
    business_sanitized = sanitize_schema_name(business_name)
    schema_name = f"user_{telegram_id}_{business_sanitized}"
    
    # Limita lunghezza totale schema name (PostgreSQL limita a 63 caratteri)
    if len(schema_name) > 63:
        # Se troppo lungo, tronca business_name
        max_business_len = 63 - len(f"user_{telegram_id}_")
        business_sanitized = business_sanitized[:max_business_len].rstrip('_')
        schema_name = f"user_{telegram_id}_{business_sanitized}"
    
    return schema_name

async def ensure_user_schema(session, telegram_id: int, business_name: str) -> str:
    """
    Crea schema utente se non esiste e crea tutte le tabelle usando SQL diretto.
    Ritorna nome schema creato.
    """
    schema_name = get_user_schema_name(telegram_id, business_name)
    
    try:
        # Verifica se schema esiste
        check_schema = sql_text(f"""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name = :schema_name
        """)
        result = await session.execute(check_schema, {"schema_name": schema_name})
        exists = result.scalar_one_or_none()
        
        if not exists:
            # Crea schema
            create_schema = sql_text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
            await session.execute(create_schema)
            await session.commit()
            logger.info(f"Created schema: {schema_name}")
        
        # Verifica se tabella wines esiste nello schema
        check_table = sql_text(f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = :schema_name AND table_name = 'wines'
        """)
        result = await session.execute(check_table, {"schema_name": schema_name})
        table_exists = result.scalar_one_or_none()
        
        if not table_exists:
            # Crea tabelle usando SQL diretto (evita problemi con ForeignKey di SQLAlchemy)
            
            # Tabella wines
            create_wines = sql_text(f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}".wines (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    producer VARCHAR(200),
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
            await session.execute(create_wines)
            
            # Tabella inventory_backups
            create_backups = sql_text(f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}".inventory_backups (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    backup_name VARCHAR(200) NOT NULL,
                    backup_data TEXT NOT NULL,
                    backup_type VARCHAR(20) DEFAULT 'initial',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await session.execute(create_backups)
            
            # Tabella inventory_logs
            create_logs = sql_text(f"""
                CREATE TABLE IF NOT EXISTS "{schema_name}".inventory_logs (
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
            await session.execute(create_logs)
            
            await session.commit()
            logger.info(f"Created tables in schema {schema_name}: wines, inventory_backups, inventory_logs")
        
        logger.info(f"Ensured schema {schema_name} with all tables")
        return schema_name
        
    except Exception as e:
        logger.error(f"Error ensuring user schema {schema_name}: {e}")
        raise

async def create_tables():
    """
    Crea solo tabelle condivise nello schema public: User e ProcessingJob.
    Wine, InventoryBackup, InventoryLog vengono creati dinamicamente negli schemi utente.
    """
    try:
        # Crea solo User e ProcessingJob nello schema public
        # I modelli Wine, InventoryBackup, InventoryLog sono stati rimossi dalla Base
        # quindi non verranno creati qui
        async with engine.begin() as conn:
            # Crea solo le tabelle dei modelli Base esistenti (User e ProcessingJob)
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database tables created successfully (public schema): users, processing_jobs")
        logger.info("Note: Wine, InventoryBackup, InventoryLog are created per-user in separate schemas via ensure_user_schema()")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

async def save_inventory_to_db(session, telegram_id: int, business_name: str, wines_data: list):
    """
    Salva inventario e vini nel database nello schema utente specifico.
    """
    try:
        from sqlalchemy import select, Table, MetaData, insert
        from sqlalchemy import text as sql_text
        
        # Trova o crea utente (in schema public)
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            # Crea nuovo utente
            user = User(
            telegram_id=telegram_id,
            business_name=business_name,
                onboarding_completed=True
            )
            session.add(user)
            await session.flush()
        
        # Aggiorna business_name se necessario
        if not user.business_name:
            user.business_name = business_name
            user.onboarding_completed = True
        
        # Assicura che schema utente esista
        user_schema = await ensure_user_schema(session, telegram_id, business_name)
        
        # Imposta search_path per questa sessione (opzionale, usiamo qualificazione esplicita)
        # await session.execute(sql_text(f'SET search_path TO "{user_schema}", public'))
        
        # Normalizza e aggiungi vini nello schema utente
        saved_count = 0
        error_count = 0
        errors_log = []
        
        for wine_data in wines_data:
            errors = []
            warnings = []
            
            try:
                # Normalizza vintage: converti stringa a int
                vintage = wine_data.get("vintage")
                vintage_original = vintage
                if vintage:
                    if isinstance(vintage, str):
                        # Estrai solo numeri (anni 1900-2099)
                        import re
                        vintage_match = re.search(r'\b(19|20)\d{2}\b', str(vintage))
                        if vintage_match:
                            vintage = int(vintage_match.group())
                        else:
                            vintage = None
                            warnings.append(f"Annata '{vintage_original}' non valida - salvato senza annata")
                    elif isinstance(vintage, (int, float)):
                        vintage = int(vintage)
                        # Verifica range valido
                        if vintage < 1900 or vintage > 2099:
                            warnings.append(f"Annata {vintage} fuori range - salvato comunque")
                    else:
                        vintage = None
                        warnings.append(f"Tipo annata non riconosciuto: {type(vintage_original).__name__}")
                else:
                    warnings.append("Annata mancante")
                
                # Normalizza quantity: converti a int
                quantity = wine_data.get("quantity", 1)
                quantity_original = quantity
                try:
                    if isinstance(quantity, str):
                        import re
                        qty_match = re.search(r'\d+', str(quantity))
                        quantity = int(qty_match.group()) if qty_match else 1
                        if qty_match is None:
                            warnings.append(f"Quantità '{quantity_original}' non valida - impostata a 1")
                    else:
                        quantity = int(quantity) if quantity else 1
                        if quantity <= 0:
                            warnings.append(f"Quantità {quantity} non valida - impostata a 1")
                            quantity = 1
                except (ValueError, TypeError) as e:
                    warnings.append(f"Errore conversione quantità '{quantity_original}': {e} - impostata a 1")
                    quantity = 1
                
                # Normalizza price: converti a float
                price = wine_data.get("price")
                price_original = price
                if price:
                    try:
                        if isinstance(price, str):
                            import re
                            price_clean = re.sub(r'[^\d.,]', '', str(price).replace(',', '.'))
                            price = float(price_clean) if price_clean else None
                            if price is None:
                                warnings.append(f"Prezzo '{price_original}' non valido - salvato senza prezzo")
                        else:
                            price = float(price) if price else None
                            if price and price < 0:
                                warnings.append(f"Prezzo negativo {price} - salvato comunque")
                    except (ValueError, TypeError) as e:
                        warnings.append(f"Errore conversione prezzo '{price_original}': {e} - salvato senza prezzo")
                        price = None
                
                # Prepara note con errori/warning
                notes_parts = []
                if wine_data.get("notes"):
                    notes_parts.append(str(wine_data.get("notes")))
                
                if warnings:
                    notes_parts.append("\n⚠️ AVVISI ELABORAZIONE:")
                    notes_parts.extend([f"  • {w}" for w in warnings])
                
                if errors:
                    notes_parts.append("\n❌ ERRORI:")
                    notes_parts.extend([f"  • {e}" for e in errors])
                
                combined_notes = "\n".join(notes_parts) if notes_parts else None
                
                # Salva vino nello schema utente usando SQL diretto
                insert_wine = sql_text(f"""
                    INSERT INTO "{user_schema}".wines 
                    (user_id, name, producer, vintage, grape_variety, region, country, 
                     wine_type, classification, quantity, min_quantity, cost_price, selling_price, 
                     alcohol_content, description, notes, created_at, updated_at)
                    VALUES 
                    (:user_id, :name, :producer, :vintage, :grape_variety, :region, :country,
                     :wine_type, :classification, :quantity, :min_quantity, :cost_price, :selling_price,
                     :alcohol_content, :description, :notes, :created_at, :updated_at)
                    RETURNING id
                """)
                
                result = await session.execute(insert_wine, {
                    "user_id": user.id,
                    "name": wine_data.get("name", "Vino senza nome"),
                    "producer": wine_data.get("producer"),
                    "vintage": vintage,
                    "grape_variety": wine_data.get("grape_variety"),
                    "region": wine_data.get("region"),
                    "country": wine_data.get("country"),
                    "wine_type": wine_data.get("wine_type"),
                    "classification": wine_data.get("classification"),
                    "quantity": quantity,
                    "min_quantity": wine_data.get("min_quantity", 0),
                    "cost_price": wine_data.get("cost_price"),
                    "selling_price": price,
                    "alcohol_content": wine_data.get("alcohol_content"),
                    "description": wine_data.get("description"),
                    "notes": combined_notes,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                })
                wine_id = result.scalar_one()
                
                if warnings or errors:
                    error_count += 1
                    errors_log.append({
                        "wine": wine_data.get("name", "Sconosciuto"),
                        "warnings": warnings,
                        "errors": errors
                    })
                
                saved_count += 1
                
            except Exception as e:
                # Errore critico - salva comunque il vino con note di errore
                logger.error(f"Errore critico normalizzando vino {wine_data.get('name', 'Unknown')}: {e}")
                error_count += 1
                errors_log.append({
                    "wine": wine_data.get("name", "Sconosciuto"),
                    "errors": [f"Errore critico: {str(e)}"]
                })
                
                # Prova a salvare comunque con dati disponibili nello schema utente
                try:
                    error_note = f"❌ ERRORE ELABORAZIONE: {str(e)}\n⚠️ Vino salvato con dati parziali. Verificare manualmente."
                    if wine_data.get("notes"):
                        error_note = f"{wine_data.get('notes')}\n\n{error_note}"
                    
                    insert_wine_error = sql_text(f"""
                        INSERT INTO "{user_schema}".wines 
                        (user_id, name, producer, vintage, region, wine_type, quantity, notes, description, created_at, updated_at)
                        VALUES 
                        (:user_id, :name, :producer, :vintage, :region, :wine_type, :quantity, :notes, :description, :created_at, :updated_at)
                        RETURNING id
                    """)
                    
                    result = await session.execute(insert_wine_error, {
                        "user_id": user.id,
                        "name": wine_data.get("name", "Vino senza nome - ERRORE"),
                        "producer": wine_data.get("producer"),
                        "vintage": None,
                        "region": wine_data.get("region"),
                        "wine_type": wine_data.get("wine_type"),
                        "quantity": 1,
                        "notes": error_note,
                        "description": wine_data.get("description"),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })
                    wine_id = result.scalar_one()
                    saved_count += 1
                except Exception as save_error:
                    logger.error(f"Impossibile salvare vino {wine_data.get('name', 'Unknown')} anche con dati parziali: {save_error}")
                    continue
        
        await session.commit()
        
        if error_count > 0:
            logger.warning(f"Saved {saved_count} wines for user {telegram_id} in schema {user_schema}, {error_count} con warning/errori")
            logger.warning(f"Errors summary: {errors_log}")
        else:
            logger.info(f"Saved {saved_count} wines for user {telegram_id} in schema {user_schema} without errors")
        
        return {
            "user_id": user.id,
            "saved_count": saved_count,
            "total_count": len(wines_data),
            "error_count": error_count,
            "errors": errors_log,
            "schema_name": user_schema
        }
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving inventory to database: {e}")
        raise

async def get_user_inventories(session, telegram_id: int):
    """Ottieni inventari di un utente dallo schema specifico"""
    try:
        from sqlalchemy import select
        
        # Trova utente
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.business_name:
            return []
        
        # Ottieni nome schema utente
        user_schema = get_user_schema_name(telegram_id, user.business_name)
        
        # Query vini dallo schema utente
        select_wines = sql_text(f'SELECT * FROM "{user_schema}".wines WHERE user_id = :user_id ORDER BY created_at DESC')
        result = await session.execute(select_wines, {"user_id": user.id})
        
        # Converti risultati in dizionari
        wines = []
        for row in result:
            wines.append({
                "id": row.id,
                "user_id": row.user_id,
                "name": row.name,
                "producer": row.producer,
                "vintage": row.vintage,
                "grape_variety": row.grape_variety,
                "region": row.region,
                "country": row.country,
                "wine_type": row.wine_type,
                "classification": row.classification,
                "quantity": row.quantity,
                "min_quantity": row.min_quantity,
                "cost_price": row.cost_price,
                "selling_price": row.selling_price,
                "alcohol_content": row.alcohol_content,
                "description": row.description,
                "notes": row.notes,
                "created_at": row.created_at,
                "updated_at": row.updated_at
            })
        
        return wines
    except Exception as e:
        logger.error(f"Error getting user inventories: {e}")
        # Se schema non esiste, ritorna lista vuota
        return []

async def get_inventory_status(session, telegram_id: int):
    """Ottieni stato elaborazione per utente dallo schema specifico"""
    try:
        from sqlalchemy import select
        
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return {
                "telegram_id": telegram_id,
                "total_wines": 0,
                "onboarding_completed": False,
                "status": "not_found",
                "schema_name": None
            }
        
        wines_count = 0
        user_schema = None
        
        if user.business_name:
            # Conta vini nello schema utente
            try:
                user_schema = get_user_schema_name(telegram_id, user.business_name)
                count_query = sql_text(f'SELECT COUNT(*) FROM "{user_schema}".wines WHERE user_id = :user_id')
                result = await session.execute(count_query, {"user_id": user.id})
                wines_count = result.scalar_one() or 0
            except Exception as schema_error:
                logger.warning(f"Schema {user_schema} not found or error counting wines: {schema_error}")
                wines_count = 0
        
        return {
            "telegram_id": telegram_id,
            "total_wines": wines_count,
            "onboarding_completed": user.onboarding_completed,
            "business_name": user.business_name,
            "status": "completed" if user.onboarding_completed else "processing",
            "schema_name": user_schema
        }
    except Exception as e:
        logger.error(f"Error getting inventory status: {e}")
        raise

async def delete_user_schema(session, telegram_id: int, business_name: str) -> dict:
    """
    Cancella schema utente e tutte le sue tabelle.
    SOLO PER telegram_id = 927230913 (admin/owner)
    Ritorna risultato operazione.
    """
    # Controllo sicurezza: solo l'owner può cancellare schemi
    ADMIN_TELEGRAM_ID = 927230913
    
    if telegram_id != ADMIN_TELEGRAM_ID:
        logger.warning(f"Unauthorized schema deletion attempt by telegram_id: {telegram_id}")
        return {
            "success": False,
            "message": "Non autorizzato. Solo l'amministratore può cancellare schemi.",
            "telegram_id": telegram_id
        }
    
    try:
        schema_name = get_user_schema_name(telegram_id, business_name)
        
        # Verifica che schema esista
        check_schema = sql_text(f"""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name = :schema_name
        """)
        result = await session.execute(check_schema, {"schema_name": schema_name})
        exists = result.scalar_one_or_none()
        
        if not exists:
            return {
                "success": False,
                "message": f"Schema {schema_name} non trovato",
                "schema_name": schema_name
            }
        
        # Conta vini prima della cancellazione
        count_query = sql_text(f'SELECT COUNT(*) FROM "{schema_name}".wines')
        result = await session.execute(count_query)
        wines_count = result.scalar_one() or 0
        
        # Cancella schema (cascade cancella tutte le tabelle)
        drop_schema = sql_text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        await session.execute(drop_schema)
        await session.commit()
        
        logger.info(f"ADMIN {telegram_id} deleted schema {schema_name} ({wines_count} wines deleted)")
        
        return {
            "success": True,
            "message": f"Schema {schema_name} cancellato con successo",
            "schema_name": schema_name,
            "wines_deleted": wines_count,
            "telegram_id": telegram_id
        }
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting schema for user {telegram_id}: {e}")
        return {
            "success": False,
            "message": f"Errore cancellazione schema: {str(e)}",
            "schema_name": schema_name,
            "telegram_id": telegram_id
        }
