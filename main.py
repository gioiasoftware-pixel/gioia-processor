from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import asyncio
from database import get_db, create_tables, save_inventory_to_db, get_inventory_status
from csv_processor import process_csv_file, process_excel_file
from ocr_processor import process_image_ocr
from ai_processor import ai_processor
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
    """Inizializza database e AI al startup"""
    try:
        await create_tables()
        logger.info("Database tables created successfully")
        
        # Verifica configurazione AI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("OpenAI API key configured - AI features enabled")
        else:
            logger.warning("OpenAI API key not found - AI features disabled")
            
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@app.get("/health")
async def health_check():
    """Health check del servizio"""
    # Verifica stato AI
    ai_status = "enabled" if os.getenv("OPENAI_API_KEY") else "disabled"
    
    return {
        "status": "healthy", 
        "service": "gioia-processor",
        "ai_enabled": ai_status,
        "features": ["csv_processing", "excel_processing", "ocr", "ai_enhancement"]
    }

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
        
        # Informazioni AI per debugging
        ai_enabled = "yes" if os.getenv("OPENAI_API_KEY") else "no"
        
        return {
            "status": "success",
            "total_wines": len(wines_data),
            "business_name": business_name,
            "telegram_id": telegram_id,
            "inventory_id": inventory_id,
            "ai_enhanced": ai_enabled,
            "processing_method": f"ai_enhanced_{file_type.lower()}"
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

@app.get("/ai/status")
async def ai_status():
    """Stato dell'AI processor"""
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return {
                "ai_enabled": False,
                "message": "OpenAI API key not configured"
            }
        
        # Test connessione OpenAI
        try:
            # Test semplice con AI
            test_result = await ai_processor.classify_wine_type("Chianti Classico")
            return {
                "ai_enabled": True,
                "openai_connected": True,
                "test_classification": test_result,
                "message": "AI processor ready"
            }
        except Exception as e:
            return {
                "ai_enabled": True,
                "openai_connected": False,
                "error": str(e),
                "message": "AI processor configured but not responding"
            }
            
    except Exception as e:
        return {
            "ai_enabled": False,
            "error": str(e),
            "message": "Error checking AI status"
        }

@app.post("/ai/test")
async def test_ai_processing(
    text: str = Form(...)
):
    """Test AI processing con testo"""
    try:
        # Estrai vini dal testo usando AI
        wines = await ai_processor.extract_wines_from_text(text)
        
        return {
            "status": "success",
            "wines_found": len(wines),
            "wines": wines,
            "ai_processing": True
        }
        
    except Exception as e:
        logger.error(f"Error in AI test: {e}")
        raise HTTPException(status_code=500, detail=f"AI test failed: {str(e)}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
