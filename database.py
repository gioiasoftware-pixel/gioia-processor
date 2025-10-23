from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

# Base per i modelli
Base = declarative_base()

class Inventory(Base):
    """Modello per inventari"""
    __tablename__ = "inventories"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    business_name = Column(String(255), nullable=False)
    status = Column(String(50), default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relazione con vini
    wines = relationship("Wine", back_populates="inventory", cascade="all, delete-orphan")

class Wine(Base):
    """Modello per vini"""
    __tablename__ = "wines"
    
    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, ForeignKey("inventories.id"), nullable=False)
    name = Column(String(255), nullable=False)
    vintage = Column(String(10))
    producer = Column(String(255))
    region = Column(String(255))
    price = Column(Float)
    quantity = Column(Integer, default=1)
    wine_type = Column(String(50))  # rosso/bianco/rosato/spumante
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relazione con inventario
    inventory = relationship("Inventory", back_populates="wines")

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
        # Crea nuovo inventario
        inventory = Inventory(
            telegram_id=telegram_id,
            business_name=business_name,
            status="processing"
        )
        session.add(inventory)
        await session.flush()  # Per ottenere l'ID
        
        # Aggiungi vini
        for wine_data in wines_data:
            wine = Wine(
                inventory_id=inventory.id,
                name=wine_data.get("name", ""),
                vintage=wine_data.get("vintage"),
                producer=wine_data.get("producer"),
                region=wine_data.get("region"),
                price=wine_data.get("price"),
                quantity=wine_data.get("quantity", 1),
                wine_type=wine_data.get("wine_type"),
                notes=wine_data.get("notes")
            )
            session.add(wine)
        
        # Aggiorna status inventario
        inventory.status = "completed"
        
        await session.commit()
        logger.info(f"Saved inventory {inventory.id} with {len(wines_data)} wines")
        return inventory.id
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error saving inventory to database: {e}")
        raise

async def get_user_inventories(session, telegram_id: int):
    """Ottieni inventari di un utente"""
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = select(Inventory).where(Inventory.telegram_id == telegram_id).options(selectinload(Inventory.wines))
        result = await session.execute(stmt)
        inventories = result.scalars().all()
        return inventories
    except Exception as e:
        logger.error(f"Error getting user inventories: {e}")
        raise

async def get_inventory_status(session, telegram_id: int):
    """Ottieni stato elaborazione per utente"""
    try:
        inventories = await get_user_inventories(session, telegram_id)
        
        total_inventories = len(inventories)
        completed_inventories = len([inv for inv in inventories if inv.status == "completed"])
        last_processed = max([inv.created_at for inv in inventories]) if inventories else None
        
        return {
            "telegram_id": telegram_id,
            "total_inventories": total_inventories,
            "completed_inventories": completed_inventories,
            "last_processed": last_processed,
            "status": "completed" if completed_inventories == total_inventories else "processing"
        }
    except Exception as e:
        logger.error(f"Error getting inventory status: {e}")
        raise
