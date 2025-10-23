import pytesseract
from PIL import Image
import io
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def process_image_ocr(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Processa immagine con OCR e estrae dati sui vini
    """
    try:
        # Apri immagine
        image = Image.open(io.BytesIO(file_content))
        logger.info(f"Image loaded: {image.size}, mode: {image.mode}")
        
        # Converti in RGB se necessario
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Esegui OCR
        ocr_text = pytesseract.image_to_string(image, lang='ita+eng')
        logger.info(f"OCR extracted {len(ocr_text)} characters")
        
        # Estrai dati vini dal testo OCR
        wines_data = extract_wines_from_ocr_text(ocr_text)
        
        logger.info(f"Extracted {len(wines_data)} wines from OCR")
        return wines_data
        
    except Exception as e:
        logger.error(f"Error processing image with OCR: {e}")
        raise

def extract_wines_from_ocr_text(text: str) -> List[Dict[str, Any]]:
    """
    Estrae dati vini dal testo OCR
    """
    wines_data = []
    
    # Pulisci testo
    cleaned_text = clean_ocr_text(text)
    
    # Dividi in righe
    lines = [line.strip() for line in cleaned_text.split('\n') if line.strip()]
    
    # Pattern per riconoscere vini
    wine_patterns = [
        # Pattern: Nome Vino - Annata - Produttore - Prezzo
        r'([A-Za-z\s\-\.]+?)\s*-\s*(\d{4})\s*-\s*([A-Za-z\s\-\.]+?)\s*-\s*([€\d\.,\s]+)',
        # Pattern: Nome Vino (Annata) - Produttore
        r'([A-Za-z\s\-\.]+?)\s*\((\d{4})\)\s*-\s*([A-Za-z\s\-\.]+)',
        # Pattern: Nome Vino - Produttore - Annata
        r'([A-Za-z\s\-\.]+?)\s*-\s*([A-Za-z\s\-\.]+?)\s*-\s*(\d{4})',
    ]
    
    for line in lines:
        wine_data = None
        
        # Prova pattern specifici
        for pattern in wine_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                wine_data = extract_wine_from_match(match, pattern)
                break
        
        # Se non trovato con pattern, prova estrazione generica
        if not wine_data:
            wine_data = extract_wine_generic(line)
        
        if wine_data and wine_data.get('name'):
            wines_data.append(wine_data)
    
    # Se non trovato nulla con pattern, prova estrazione per blocchi
    if not wines_data:
        wines_data = extract_wines_by_blocks(cleaned_text)
    
    return wines_data

def clean_ocr_text(text: str) -> str:
    """
    Pulisce testo OCR
    """
    # Rimuovi caratteri di controllo
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Normalizza spazi
    text = re.sub(r'\s+', ' ', text)
    
    # Rimuovi righe troppo corte (probabilmente rumore)
    lines = [line for line in text.split('\n') if len(line.strip()) > 3]
    
    return '\n'.join(lines)

def extract_wine_from_match(match, pattern: str) -> Dict[str, Any]:
    """
    Estrae dati vino da un match di pattern
    """
    groups = match.groups()
    wine_data = {}
    
    if len(groups) >= 2:
        wine_data['name'] = groups[0].strip()
        
        # Cerca annata nei gruppi
        for group in groups[1:]:
            if re.match(r'\d{4}', str(group)):
                wine_data['vintage'] = group
                break
        
        # Cerca produttore (di solito il secondo gruppo se non è annata)
        for group in groups[1:]:
            if not re.match(r'\d{4}', str(group)) and not re.match(r'[€\d\.,\s]+', str(group)):
                wine_data['producer'] = group.strip()
                break
        
        # Cerca prezzo
        for group in groups:
            if re.search(r'[€\d\.,]', str(group)):
                price_str = str(group).replace('€', '').replace(',', '.').strip()
                price_match = re.search(r'[\d\.,]+', price_str)
                if price_match:
                    try:
                        wine_data['price'] = float(price_match.group().replace(',', '.'))
                    except ValueError:
                        pass
                break
    
    # Classifica tipo vino
    if 'name' in wine_data:
        wine_data['wine_type'] = classify_wine_type(wine_data['name'])
    
    wine_data['quantity'] = 1
    
    return wine_data

def extract_wine_generic(line: str) -> Dict[str, Any]:
    """
    Estrae dati vino da una riga generica
    """
    wine_data = {}
    
    # Cerca annata
    vintage_match = re.search(r'\b(19|20)\d{2}\b', line)
    if vintage_match:
        wine_data['vintage'] = vintage_match.group()
    
    # Cerca prezzo
    price_match = re.search(r'[€\d\.,\s]+\d+[€\d\.,\s]*', line)
    if price_match:
        price_str = price_match.group().replace('€', '').replace(',', '.').strip()
        try:
            wine_data['price'] = float(re.sub(r'[^\d\.]', '', price_str))
        except ValueError:
            pass
    
    # Il resto dovrebbe essere nome vino
    # Rimuovi annata e prezzo dalla riga per ottenere il nome
    name_line = line
    if vintage_match:
        name_line = name_line.replace(vintage_match.group(), '')
    if price_match:
        name_line = name_line.replace(price_match.group(), '')
    
    # Pulisci e prendi come nome
    name = re.sub(r'[^\w\s\-\.]', ' ', name_line).strip()
    name = re.sub(r'\s+', ' ', name)
    
    if len(name) > 2:
        wine_data['name'] = name
    
    # Classifica tipo vino
    if 'name' in wine_data:
        wine_data['wine_type'] = classify_wine_type(wine_data['name'])
    
    wine_data['quantity'] = 1
    
    return wine_data

def extract_wines_by_blocks(text: str) -> List[Dict[str, Any]]:
    """
    Estrae vini dividendo il testo in blocchi
    """
    wines_data = []
    
    # Dividi in paragrafi
    paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 10]
    
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split('\n') if line.strip()]
        
        for line in lines:
            # Se la riga contiene numeri (probabilmente prezzo o annata)
            if re.search(r'\d', line):
                wine_data = extract_wine_generic(line)
                if wine_data and wine_data.get('name'):
                    wines_data.append(wine_data)
    
    return wines_data

def classify_wine_type(text: str) -> str:
    """
    Classifica il tipo di vino dal testo
    """
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['rosso', 'red', 'nero', 'black', 'sangiovese', 'barbera', 'nebbiolo']):
        return 'rosso'
    elif any(word in text_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon']):
        return 'bianco'
    elif any(word in text_lower for word in ['rosato', 'rosé', 'rose']):
        return 'rosato'
    elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco', 'moscato', 'frizzante']):
        return 'spumante'
    else:
        return 'sconosciuto'
