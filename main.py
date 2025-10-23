from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import asyncio
from database import get_db, create_tables, save_inventory_to_db, get_inventory_status
from csv_processor import process_csv_file, process_excel_file
from ocr_processor import process_image_ocr
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gioia Processor", version="1.0.0")

# CORS per comunicazione con bot
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Inizializza database al startup"""
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")

@app.get("/health")
async def health_check():
    """Health check del servizio"""
    return {"status": "healthy", "service": "gioia-processor"}

@app.post("/process-inventory")
async def process_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file_type: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Elabora file inventario e salva nel database
    """
    try:
        logger.info(f"Processing inventory for telegram_id: {telegram_id}, business: {business_name}, type: {file_type}")
        
        # Leggi contenuto file
        file_content = await file.read()
        
        # Processa file in base al tipo
        if file_type.lower() == "csv":
            wines_data = await process_csv_file(file_content)
        elif file_type.lower() in ["excel", "xlsx", "xls"]:
            wines_data = await process_excel_file(file_content)
        elif file_type.lower() in ["image", "jpg", "jpeg", "png"]:
            wines_data = await process_image_ocr(file_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Salva nel database
        async for db in get_db():
            inventory_id = await save_inventory_to_db(db, telegram_id, business_name, wines_data)
            break
        
        logger.info(f"Successfully processed {len(wines_data)} wines for inventory {inventory_id}")
        
        return {
            "status": "success",
            "total_wines": len(wines_data),
            "business_name": business_name,
            "telegram_id": telegram_id,
            "inventory_id": inventory_id
        }
        
    except Exception as e:
        logger.error(f"Error processing inventory: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing inventory: {str(e)}")

@app.get("/status/{telegram_id}")
async def get_status(telegram_id: int):
    """
    Restituisce stato elaborazione per utente
    """
    try:
        async for db in get_db():
            status_data = await get_inventory_status(db, telegram_id)
            return status_data
    except Exception as e:
        logger.error(f"Error getting status for telegram_id {telegram_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
