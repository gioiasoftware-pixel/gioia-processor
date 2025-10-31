from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
import os
import logging

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
    
    # Relazioni
    wines = relationship("Wine", back_populates="user", cascade="all, delete-orphan")
    inventory_backups = relationship("InventoryBackup", back_populates="user", cascade="all, delete-orphan")
    inventory_logs = relationship("InventoryLog", back_populates="user", cascade="all, delete-orphan")

class Wine(Base):
    """Modello per l'inventario vini"""
    __tablename__ = 'wines'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati vino
    name = Column(String(200), nullable=False)
    producer = Column(String(200))
    vintage = Column(Integer)  # Annata
    grape_variety = Column(String(200))  # Vitigno
    region = Column(String(200))
    country = Column(String(100))
    
    # Classificazione
    wine_type = Column(String(50))  # rosso, bianco, rosato, spumante, etc.
    classification = Column(String(100))  # DOCG, DOC, IGT, etc.
    
    # Quantità e prezzi
    quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=0)  # Scorta minima
    cost_price = Column(Float)  # Prezzo di acquisto
    selling_price = Column(Float)  # Prezzo di vendita
    
    # Dettagli
    alcohol_content = Column(Float)  # Gradazione alcolica
    description = Column(Text)
    notes = Column(Text)
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="wines")

class InventoryBackup(Base):
    """Backup dell'inventario iniziale per ogni utente"""
    __tablename__ = 'inventory_backups'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati del backup
    backup_name = Column(String(200), nullable=False)  # "Inventario Iniziale", "Backup Giorno X"
    backup_data = Column(Text, nullable=False)  # JSON con tutti i dati inventario
    backup_type = Column(String(20), default="initial")  # 'initial', 'daily', 'manual'
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="inventory_backups")

class InventoryLog(Base):
    """Log di consumi e rifornimenti per ogni utente"""
    __tablename__ = 'inventory_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati del movimento
    wine_name = Column(String(200), nullable=False)
    wine_producer = Column(String(200))
    movement_type = Column(String(20), nullable=False)  # 'consumo', 'rifornimento', 'aggiustamento'
    quantity_change = Column(Integer, nullable=False)  # Positivo per rifornimenti, negativo per consumi
    quantity_before = Column(Integer, nullable=False)  # Quantità prima del movimento
    quantity_after = Column(Integer, nullable=False)   # Quantità dopo il movimento
    
    # Dettagli
    notes = Column(Text)
    movement_date = Column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="inventory_logs")

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

async def create_tables():
    """Crea tabelle nel database"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

async def save_inventory_to_db(session, telegram_id: int, business_name: str, wines_data: list):
    """
    Salva inventario e vini nel database
    """
    try:
        from sqlalchemy import select
        
        # Trova o crea utente
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
        
        # Normalizza e aggiungi vini
        saved_count = 0
        for wine_data in wines_data:
            try:
                # Normalizza vintage: converti stringa a int
                vintage = wine_data.get("vintage")
                if vintage:
                    if isinstance(vintage, str):
                        # Estrai solo numeri (anni 1900-2099)
                        import re
                        vintage_match = re.search(r'\b(19|20)\d{2}\b', str(vintage))
                        vintage = int(vintage_match.group()) if vintage_match else None
                    elif isinstance(vintage, (int, float)):
                        vintage = int(vintage)
                    else:
                        vintage = None
                
                # Normalizza quantity: converti a int
                quantity = wine_data.get("quantity", 1)
                if isinstance(quantity, str):
                    import re
                    qty_match = re.search(r'\d+', str(quantity))
                    quantity = int(qty_match.group()) if qty_match else 1
                else:
                    quantity = int(quantity) if quantity else 1
                
                # Normalizza price: converti a float
                price = wine_data.get("price")
                if price:
                    if isinstance(price, str):
                        import re
                        price_clean = re.sub(r'[^\d.,]', '', str(price).replace(',', '.'))
                        price = float(price_clean) if price_clean else None
                    else:
                        price = float(price) if price else None
                
                wine = Wine(
                    user_id=user.id,
                    name=wine_data.get("name", ""),
                    vintage=vintage,  # Ora è int o None
                    producer=wine_data.get("producer"),
                    region=wine_data.get("region"),
                    selling_price=price,  # Ora è float o None
                    quantity=quantity,  # Ora è int
                    wine_type=wine_data.get("wine_type"),
                    notes=wine_data.get("notes"),
                    description=wine_data.get("description")
                )
                session.add(wine)
                saved_count += 1
            except Exception as e:
                logger.warning(f"Error normalizing wine data {wine_data.get('name', 'Unknown')}: {e}")
                continue
        
        await session.commit()
        logger.info(f"Saved {len(wines_data)} wines for user {telegram_id}")
        return user.id
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving inventory to database: {e}")
        raise

async def get_user_inventories(session, telegram_id: int):
    """Ottieni inventari di un utente"""
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = select(User).where(User.telegram_id == telegram_id).options(selectinload(User.wines))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return []
        
        return user.wines
    except Exception as e:
        logger.error(f"Error getting user inventories: {e}")
        raise

async def get_inventory_status(session, telegram_id: int):
    """Ottieni stato elaborazione per utente"""
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
                "status": "not_found"
            }
        
        wines_count = len(user.wines) if user.wines else 0
        
        return {
            "telegram_id": telegram_id,
            "total_wines": wines_count,
            "onboarding_completed": user.onboarding_completed,
            "business_name": user.business_name,
            "status": "completed" if user.onboarding_completed else "processing"
        }
    except Exception as e:
        logger.error(f"Error getting inventory status: {e}")
        raise
