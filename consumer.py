# processor/src/consumer.py
import os
import httpx
import logging
from messaging.stream import consume_forever
from database import save_inventory_to_db
from csv_processor import process_csv_file, process_excel_file
from ocr_processor import process_image_ocr

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TG_FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"

async def download_telegram_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        # 1) getFile per ottenere file_path
        r = await client.get(f"{TG_API}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        file_path = r.json()["result"]["file_path"]
        # 2) scarica il contenuto
        f = await client.get(f"{TG_FILE_BASE}/{file_path}")
        f.raise_for_status()
        return f.content

async def process_inventory_message(payload: dict):
    chat_id = int(payload["chat_id"])
    title = payload["title"]
    fmt = payload["format"]
    file_id = payload["telegram_file_id"]

    logger.info(f"Processing inventory: {title} ({fmt}) for chat {chat_id}")

    try:
        # Scarica file da Telegram
        content = await download_telegram_file(file_id)
        logger.info(f"Downloaded file: {len(content)} bytes")

        # Elabora file in base al tipo
        if fmt.lower() == "csv":
            wines_data = await process_csv_file(content)
        elif fmt.lower() in ["excel", "xlsx", "xls"]:
            wines_data = await process_excel_file(content)
        elif fmt.lower() in ["image", "jpg", "jpeg", "png", "photo"]:
            wines_data = await process_image_ocr(content)
        else:
            logger.error(f"Unsupported file type: {fmt}")
            return

        if not wines_data:
            logger.warning(f"No wines found in {title}")
            return

        # Salva nel database
        business_name = title.split(" - ")[0] if " - " in title else "Unknown"
        await save_inventory_to_db(chat_id, business_name, wines_data)
        
        logger.info(f"Successfully processed {len(wines_data)} wines from {title}")

    except Exception as e:
        logger.error(f"Error processing {title}: {e}")
        raise

async def main():
    # consumer_name: usa un identificatore dell'istanza (es. hostname) per scalare a N worker
    consumer_name = os.getenv("CONSUMER_NAME", "processor-1")
    logger.info(f"Starting consumer: {consumer_name}")
    await consume_forever(process_inventory_message, consumer_name)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
