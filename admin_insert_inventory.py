"""
Script admin per inserire manualmente inventari puliti nel database tramite processor API.

Lo script chiama l'API /admin/insert-inventory del processor che:
- Crea automaticamente tutte le tabelle necessarie (INVENTARIO, BACKUP, LOG, CONSUMI)
- Inserisce i vini direttamente nel database SENZA passare attraverso la pipeline
- NON esegue pulizie/normalizzazioni (CSV deve essere già pulito)

Uso:
    python admin_insert_inventory.py <telegram_id> <business_name> <file_csv> [--replace] [--processor-url URL]

Esempio:
    python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario_pulito.csv
    python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario_pulito.csv --replace
    python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario_pulito.csv --processor-url http://localhost:8001
"""
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from core.logger import setup_colored_logging

# Setup logging
setup_colored_logging("admin_insert")
logger = logging.getLogger(__name__)

# URL default processor (può essere sovrascritto con --processor-url o PROCESSOR_URL env)
def _normalize_url(url: str) -> str:
    """Normalizza URL aggiungendo http:// o https:// se manca il protocollo"""
    if not url:
        return "http://localhost:8001"
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        # Per localhost usa http, per altri usa https
        if "localhost" in url or "127.0.0.1" in url:
            url = f"http://{url}"
        else:
            url = f"https://{url}"
    return url

DEFAULT_PROCESSOR_URL_RAW = os.getenv("PROCESSOR_URL", "http://localhost:8001")
DEFAULT_PROCESSOR_URL = _normalize_url(DEFAULT_PROCESSOR_URL_RAW)


async def call_admin_api(
    processor_url: str,
    telegram_id: int,
    business_name: str,
    csv_file_path: str,
    mode: str = "add"
) -> dict:
    """
    Chiama l'API /admin/insert-inventory del processor.
    
    Questo endpoint inserisce direttamente senza passare attraverso la pipeline.
    
    Args:
        processor_url: URL base del processor (es: http://localhost:8001)
        telegram_id: ID Telegram utente
        business_name: Nome business
        csv_file_path: Path file CSV
        mode: Modalità ("add" o "replace")
    
    Returns:
        Dict con risultato inserimento
    """
    # Leggi file CSV
    if not Path(csv_file_path).exists():
        raise FileNotFoundError(f"File non trovato: {csv_file_path}")
    
    with open(csv_file_path, 'rb') as f:
        file_content = f.read()
    
    file_name = Path(csv_file_path).name
    
    # Prepara files e data
    files = {
        'file': (file_name, file_content, 'text/csv')
    }
    data = {
        'telegram_id': str(telegram_id),
        'business_name': business_name,
        'mode': mode
    }
    
    # Chiama API admin
    url = f"{processor_url.rstrip('/')}/admin/insert-inventory"
    
    logger.info(f"Chiamata API admin: {url}")
    logger.info(f"Parametri: telegram_id={telegram_id}, business_name={business_name}, mode={mode}")
    
    timeout = httpx.Timeout(120.0)  # Timeout più lungo per inserimenti grandi
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, files=files, data=data)
        
        if response.status_code != 200:
            error_text = response.text
            raise Exception(f"HTTP {response.status_code}: {error_text}")
        
        result = response.json()
        return result




async def insert_inventory_via_processor(
    processor_url: str,
    telegram_id: int,
    business_name: str,
    csv_file: str,
    replace: bool = False
) -> tuple[int, int]:
    """
    Inserisce inventario chiamando l'API del processor.
    
    Args:
        processor_url: URL base del processor
        telegram_id: ID Telegram utente
        business_name: Nome business
        csv_file: Path file CSV
        replace: Se True, sostituisce inventario esistente
    
    Returns:
        Tuple (saved_count, error_count)
    """
    # Verifica file esiste
    if not Path(csv_file).exists():
        raise FileNotFoundError(f"File non trovato: {csv_file}")
    
    # Verifica processor raggiungibile
    health_url = f"{processor_url.rstrip('/')}/health"
    try:
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(health_url)
            if response.status_code != 200:
                raise Exception(f"Processor non raggiungibile: HTTP {response.status_code}")
            health = response.json()
            logger.info(f"Processor health check: {health.get('status', 'unknown')}")
    except Exception as e:
        raise Exception(
            f"Impossibile raggiungere il processor all'URL {processor_url}. "
            f"Assicurati che il processor sia in esecuzione. Errore: {e}"
        )
    
    mode = "replace" if replace else "add"
    
    logger.info("=" * 60)
    logger.info("CHIAMATA PROCESSOR ADMIN API")
    logger.info("=" * 60)
    logger.info(f"Processor URL: {processor_url}")
    logger.info(f"Telegram ID: {telegram_id}")
    logger.info(f"Business Name: {business_name}")
    logger.info(f"CSV File: {csv_file}")
    logger.info(f"Mode: {mode.upper()}")
    logger.info("=" * 60)
    
    # Chiama API admin (inserimento diretto, senza pipeline)
    logger.info("Invio file al processor (endpoint admin)...")
    result = await call_admin_api(
        processor_url=processor_url,
        telegram_id=telegram_id,
        business_name=business_name,
        csv_file_path=csv_file,
        mode=mode
    )
    
    if result.get('status') != 'success':
        error_msg = result.get('detail', result.get('error', 'Errore sconosciuto'))
        raise Exception(f"Errore inserimento: {error_msg}")
    
    # Estrai risultati
    saved_count = result.get('saved_wines', 0)
    error_count = result.get('error_count', 0)
    total_wines = result.get('total_wines', 0)
    tables_created = result.get('tables_created', [])
    
    logger.info("=" * 60)
    logger.info("✅ INSERIMENTO COMPLETATO")
    logger.info("=" * 60)
    logger.info(f"Vini totali: {total_wines}")
    logger.info(f"Vini salvati: {saved_count}")
    logger.info(f"Errori: {error_count}")
    logger.info(f"Tabelle create: {', '.join(tables_created)}")
    logger.info("=" * 60)
    
    return saved_count, error_count


async def main():
    """Main entry point."""
    if len(sys.argv) < 4:
        print(__doc__)
        print("\n❌ Errore: Parametri mancanti")
        print("\nUso:")
        print("  python admin_insert_inventory.py <telegram_id> <business_name> <file_csv> [--replace] [--processor-url URL]")
        print("\nEsempio:")
        print('  python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario.csv')
        print('  python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario.csv --replace')
        print('  python admin_insert_inventory.py 123456789 "Ristorante XYZ" inventario.csv --processor-url http://localhost:8001')
        sys.exit(1)
    
    try:
        telegram_id = int(sys.argv[1])
        business_name = sys.argv[2]
        csv_file = sys.argv[3]
        
        # Parse opzioni
        replace = "--replace" in sys.argv
        
        # Parse processor URL
        processor_url = DEFAULT_PROCESSOR_URL
        if "--processor-url" in sys.argv:
            idx = sys.argv.index("--processor-url")
            if idx + 1 < len(sys.argv):
                processor_url = sys.argv[idx + 1]
            else:
                print("❌ Errore: --processor-url richiede un URL")
                sys.exit(1)
        
        logger.info("=" * 60)
        logger.info("ADMIN INSERT INVENTORY (via Processor API)")
        logger.info("=" * 60)
        logger.info(f"Processor URL: {processor_url}")
        logger.info(f"Telegram ID: {telegram_id}")
        logger.info(f"Business Name: {business_name}")
        logger.info(f"CSV File: {csv_file}")
        logger.info(f"Mode: {'REPLACE' if replace else 'ADD'}")
        logger.info("=" * 60)
        
        saved_count, error_count = await insert_inventory_via_processor(
            processor_url=processor_url,
            telegram_id=telegram_id,
            business_name=business_name,
            csv_file=csv_file,
            replace=replace
        )
        
        print("\n" + "=" * 60)
        print("✅ INSERIMENTO COMPLETATO")
        print("=" * 60)
        print(f"Vini salvati: {saved_count}")
        print(f"Errori: {error_count}")
        print("=" * 60)
        print("\n💡 Nota: Il processor ha creato automaticamente tutte le tabelle necessarie:")
        print("   - INVENTARIO")
        print("   - BACKUP")
        print("   - LOG")
        print("   - CONSUMI")
        print("=" * 60)
        
        if error_count > 0:
            sys.exit(1)
        
    except ValueError as e:
        logger.error(f"Errore parametri: {e}")
        print(f"\n❌ Errore: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File non trovato: {e}")
        print(f"\n❌ Errore: {e}")
        sys.exit(1)
    except TimeoutError as e:
        logger.error(f"Timeout: {e}")
        print(f"\n❌ Errore: {e}")
        print("\n💡 Suggerimento: Il file potrebbe essere troppo grande o il processor potrebbe essere lento.")
        print("   Verifica lo stato del processor e riprova.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Errore generico: {e}", exc_info=True)
        print(f"\n❌ Errore: {e}")
        print("\n💡 Suggerimenti:")
        print("   1. Verifica che il processor sia in esecuzione")
        print(f"   2. Verifica che l'URL sia corretto: {processor_url}")
        print("   3. Controlla i log del processor per dettagli")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
