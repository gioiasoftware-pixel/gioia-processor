from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import uvicorn
import os
import asyncio
import json
from datetime import datetime
from database import get_db, create_tables, save_inventory_to_db, get_inventory_status
from config import validate_config
from csv_processor import process_csv_file, process_excel_file
from ocr_processor import process_image_ocr
from ai_processor import ai_processor
import logging
from typing import Optional

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
        # Valida configurazione
        validate_config()
        
        # Crea tabelle database
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
    """Health check del servizio con informazioni dettagliate"""
    try:
        # Verifica stato AI
        ai_status = "enabled" if os.getenv("OPENAI_API_KEY") else "disabled"
        
        # Verifica database
        db_status = "connected"
        try:
            async for db in get_db():
                # Test connessione database
                await db.execute(text("SELECT 1"))
                break
        except Exception as e:
            db_status = f"error: {str(e)[:100]}"
            logger.error(f"Database health check failed: {e}")
        
        # Verifica variabili ambiente critiche
        env_status = {
            "DATABASE_URL": "configured" if os.getenv("DATABASE_URL") else "missing",
            "PORT": os.getenv("PORT", "8001"),
            "OPENAI_API_KEY": "configured" if os.getenv("OPENAI_API_KEY") else "missing"
        }
        
        return {
            "status": "healthy", 
            "service": "gioia-processor",
            "version": "1.0.0",
            "ai_enabled": ai_status,
            "database_status": db_status,
            "environment": env_status,
            "features": ["csv_processing", "excel_processing", "ocr", "ai_enhancement"],
            "endpoints": {
                "health": "/health",
                "process": "/process-inventory", 
                "status": "/status/{telegram_id}",
                "ai_status": "/ai/status",
                "ai_test": "/ai/test"
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "gioia-processor", 
            "error": str(e),
            "timestamp": str(datetime.utcnow())
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
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"Processing inventory for telegram_id: {telegram_id}, business: {business_name}, type: {file_type}")
        
        # Validazione input
        if not telegram_id or telegram_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid telegram_id")
        
        if not business_name or len(business_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Business name is required")
        
        if not file_type or file_type.lower() not in ["csv", "excel", "xlsx", "xls", "image", "jpg", "jpeg", "png"]:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Leggi contenuto file
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        if len(file_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
        
        logger.info(f"File size: {len(file_content)} bytes")
        
        # Processa file in base al tipo
        wines_data = []
        processing_method = ""
        
        try:
            if file_type.lower() == "csv":
                wines_data = await process_csv_file(file_content)
                processing_method = "csv_ai_enhanced"
            elif file_type.lower() in ["excel", "xlsx", "xls"]:
                wines_data = await process_excel_file(file_content)
                processing_method = "excel_ai_enhanced"
            elif file_type.lower() in ["image", "jpg", "jpeg", "png"]:
                wines_data = await process_image_ocr(file_content)
                processing_method = "ocr_ai_enhanced"
            
            logger.info(f"Extracted {len(wines_data)} wines from {file_type} file")
            
        except Exception as processing_error:
            logger.error(f"Error processing {file_type} file: {processing_error}")
            raise HTTPException(status_code=422, detail=f"Error processing {file_type} file: {str(processing_error)}")
        
        # Salva nel database
        inventory_id = None
        try:
            async for db in get_db():
                inventory_id = await save_inventory_to_db(db, telegram_id, business_name, wines_data)
                break
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Successfully processed {len(wines_data)} wines for inventory {inventory_id} in {processing_time:.2f}s")
        
        # Informazioni AI per debugging
        ai_enabled = "yes" if os.getenv("OPENAI_API_KEY") else "no"
        
        return {
            "status": "success",
            "total_wines": len(wines_data),
            "business_name": business_name,
            "telegram_id": telegram_id,
            "inventory_id": inventory_id,
            "ai_enhanced": ai_enabled,
            "processing_method": processing_method,
            "processing_time_seconds": round(processing_time, 2),
            "file_type": file_type,
            "file_size_bytes": len(file_content)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing inventory: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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

@app.get("/debug/info")
async def debug_info():
    """Informazioni di debug per troubleshooting"""
    try:
        import sys
        import platform
        
        return {
            "service": "gioia-processor",
            "version": "1.0.0",
            "python_version": sys.version,
            "platform": platform.platform(),
            "environment_variables": {
                "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else None,
                "PORT": os.getenv("PORT"),
                "OPENAI_API_KEY": "***" if os.getenv("OPENAI_API_KEY") else None,
                "ENVIRONMENT": os.getenv("ENVIRONMENT", "production")
            },
            "database_test": await test_database_connection(),
            "ai_test": await test_ai_connection(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

async def test_database_connection():
    """Test connessione database"""
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            return {"status": "connected", "error": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def test_ai_connection():
    """Test connessione AI"""
    try:
        if not os.getenv("OPENAI_API_KEY"):
            return {"status": "not_configured", "error": "OPENAI_API_KEY not set"}
        
        # Test semplice
        result = await ai_processor.classify_wine_type("Chianti")
        return {"status": "connected", "test_result": result, "error": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/debug/logs")
async def debug_logs():
    """Logs recenti per debugging"""
    try:
        # Simula logs (in produzione usare un sistema di logging reale)
        return {
            "service": "gioia-processor",
            "logs": [
                {"level": "INFO", "message": "Service started", "timestamp": datetime.utcnow().isoformat()},
                {"level": "INFO", "message": "Database connected", "timestamp": datetime.utcnow().isoformat()},
                {"level": "INFO", "message": "AI processor ready", "timestamp": datetime.utcnow().isoformat()}
            ],
            "note": "This is a simplified log view. Check Railway dashboard for full logs."
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/process-inventory-graphql")
async def process_inventory_graphql(request: Request):
    """
    Elabora file inventario usando formato GraphQL multipart
    """
    try:
        # Leggi il contenuto della richiesta
        form = await request.form()
        
        # Estrai operations e map
        operations_str = form.get("operations")
        map_str = form.get("map")
        
        if not operations_str or not map_str:
            raise HTTPException(status_code=400, detail="Missing operations or map")
        
        # Parse JSON
        operations = json.loads(operations_str)
        file_map = json.loads(map_str)
        
        # Estrai variabili
        variables = operations.get("variables", {})
        telegram_id = variables.get("telegram_id")
        business_name = variables.get("business_name")
        file_type = variables.get("file_type")
        
        # Estrai file usando la mappa
        file_key = list(file_map.keys())[0]  # Prende la prima chiave (es. "0")
        file = form.get(file_key)
        
        if not file:
            raise HTTPException(status_code=400, detail="File not found in request")
        
        logger.info(f"GraphQL Processing inventory for telegram_id: {telegram_id}, business: {business_name}, type: {file_type}")
        
        # Usa la stessa logica dell'endpoint standard
        return await process_inventory_logic(telegram_id, business_name, file_type, file)
        
    except Exception as e:
        logger.error(f"Error in GraphQL endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_inventory_logic(telegram_id: int, business_name: str, file_type: str, file):
    """
    Logica comune per elaborazione inventario
    """
    start_time = datetime.utcnow()
    
    try:
        # Validazione input
        if not telegram_id or telegram_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid telegram_id")
        
        if not business_name or len(business_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Business name is required")
        
        if not file_type or file_type.lower() not in ["csv", "excel", "xlsx", "xls", "image", "jpg", "jpeg", "png", "photo"]:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        # Leggi contenuto file
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Processa file in base al tipo
        if file_type.lower() in ["csv"]:
            wines_data = await process_csv_file(file_content)
        elif file_type.lower() in ["excel", "xlsx", "xls"]:
            wines_data = await process_excel_file(file_content)
        elif file_type.lower() in ["image", "jpg", "jpeg", "png", "photo"]:
            wines_data = await process_image_ocr(file_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
        
        if not wines_data:
            return {
                "status": "error",
                "error": "No wines found in file",
                "telegram_id": telegram_id
            }
        
        # Salva nel database
        await save_inventory_to_db(telegram_id, business_name, wines_data)
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Inventory processed successfully: {len(wines_data)} wines in {processing_time:.2f}s")
        
        return {
            "status": "success",
            "total_wines": len(wines_data),
            "business_name": business_name,
            "telegram_id": telegram_id,
            "processing_time": processing_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing inventory: {e}")
        return {
            "status": "error",
            "error": str(e),
            "telegram_id": telegram_id
        }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
