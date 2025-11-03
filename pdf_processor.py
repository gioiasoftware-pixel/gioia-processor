"""
Processore PDF per inventario vini.
Se il PDF è "pulito" (testo estraibile) → tratta come CSV/Excel.
Se il PDF è scansione (immagine) → tratta come OCR.
"""
import io
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from csv_processor import process_csv_file, process_excel_file, create_smart_column_mapping, extract_wine_data_from_row
from ocr_processor import process_image_ocr
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    try:
        import PyPDF2
        PDF_SUPPORT = True
    except ImportError:
        PDF_SUPPORT = False
        logger.warning("PDF libraries not available. Install pdfplumber or PyPDF2 for PDF support.")

try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_PDF_SUPPORT = True
except ImportError:
    OCR_PDF_SUPPORT = False
    logger.warning("pdf2image/pytesseract not available. PDF OCR fallback disabled.")


async def process_pdf_file(file_content: bytes, file_name: str = "document.pdf") -> List[Dict[str, Any]]:
    """
    Processa file PDF per estrarre inventario vini.
    Se il PDF ha testo estraibile (nativo) → tratta come CSV/Excel.
    Se il PDF è scansione → tratta come OCR.
    """
    if not PDF_SUPPORT:
        raise ValueError("PDF support not available. Install pdfplumber or PyPDF2.")
    
    try:
        # PRIMA: Prova estrazione testo nativo (PDF pulito)
        text_content, has_text = extract_text_from_pdf(file_content)
        
        if has_text and text_content:
            logger.info(f"PDF has extractable text ({len(text_content)} chars), treating as structured data")
            # Prova a parsare come CSV/Excel (tabella)
            wines = await parse_pdf_as_table(text_content, file_name)
            if wines:
                return wines
        
        # SECONDA: Se testo nativo fallisce o PDF è scansione, usa OCR
        logger.info("PDF text extraction failed or PDF is scanned image, using OCR")
        if OCR_PDF_SUPPORT:
            wines = await process_pdf_with_ocr(file_content)
            return wines
        else:
            raise ValueError("PDF appears to be scanned but OCR support not available. Install pdf2image and pytesseract.")
            
    except Exception as e:
        logger.error(f"Error processing PDF file: {e}")
        raise


def extract_text_from_pdf(file_content: bytes) -> Tuple[str, bool]:
    """
    Estrae testo nativo da PDF (se disponibile).
    Returns: (text_content, has_text)
    """
    try:
        pdf_file = io.BytesIO(file_content)
        
        # Prova con pdfplumber (più robusto per tabelle)
        if 'pdfplumber' in globals():
            text_parts = []
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    # Prova estrazione tabella prima
                    tables = page.extract_tables()
                    if tables:
                        # PDF ha tabelle → testo strutturato
                        for table in tables:
                            for row in table:
                                if row:
                                    text_parts.append(" | ".join(str(cell) if cell else "" for cell in row))
                    
                    # Fallback: estrai testo normale
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            
            text = "\n".join(text_parts)
            return text, bool(text and len(text.strip()) > 10)
        
        # Fallback: PyPDF2
        elif 'PyPDF2' in globals():
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text_parts = []
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            text = "\n".join(text_parts)
            return text, bool(text and len(text.strip()) > 10)
        
        return "", False
        
    except Exception as e:
        logger.warning(f"Error extracting text from PDF: {e}")
        return "", False


async def parse_pdf_as_table(text_content: str, file_name: str) -> List[Dict[str, Any]]:
    """
    Prova a parsare il testo PDF come tabella CSV/Excel.
    """
    try:
        # Prova a convertire testo in CSV/Excel usando euristiche
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        
        # Se il testo contiene separatori tabella (|, \t, ;, ,), prova parsing strutturato
        if any('|' in line or '\t' in line or ';' in line or (',' in line and len(line.split(',')) >= 3) for line in lines[:5]):
            # Prova come CSV con vari separatori
            for sep in ['|', '\t', ';', ',']:
                try:
                    csv_content = "\n".join(lines)
                    df = pd.read_csv(io.StringIO(csv_content), sep=sep, engine='python', on_bad_lines='skip')
                    
                    if len(df.columns) >= 2:  # Almeno 2 colonne (nome + qualcosa)
                        logger.info(f"Parsed PDF as CSV with separator '{sep}' -> {len(df)} rows, {len(df.columns)} columns")
                        
                        # Usa lo stesso mapping intelligente dei CSV/Excel
                        original_columns = list(df.columns)
                        smart_mapping = create_smart_column_mapping(original_columns)
                        
                        if smart_mapping:
                            df = df.rename(columns=smart_mapping)
                        
                        # Estrai vini
                        wines_data = []
                        for index, row in df.iterrows():
                            try:
                                wine_data = extract_wine_data_from_row(row)
                                if wine_data and wine_data.get('name'):
                                    wines_data.append(wine_data)
                            except Exception as e:
                                logger.warning(f"Error processing PDF row {index}: {e}")
                                continue
                        
                        if wines_data:
                            logger.info(f"Extracted {len(wines_data)} wines from PDF text table")
                            return wines_data
                except Exception:
                    continue
        
        # Fallback: parsing line-by-line (meno strutturato)
        wines_data = []
        for line in lines:
            if re.search(r'\d', line):  # Linea con numeri (probabilmente vino)
                # Estrai dati base
                wine_data = extract_wine_from_text_line(line)
                if wine_data and wine_data.get('name'):
                    wines_data.append(wine_data)
        
        if wines_data:
            logger.info(f"Extracted {len(wines_data)} wines from PDF text (line-by-line)")
            return wines_data
        
        return []
        
    except Exception as e:
        logger.error(f"Error parsing PDF as table: {e}")
        return []


def extract_wine_from_text_line(line: str) -> Dict[str, Any]:
    """
    Estrae dati vino da una riga di testo PDF.
    """
    wine_data = {}
    
    # Cerca annata
    vintage_match = re.search(r'\b(19|20)\d{2}\b', line)
    if vintage_match:
        wine_data['vintage'] = int(vintage_match.group())
    
    # Cerca prezzo
    price_match = re.search(r'[€\d\.,]+\d+[€\d\.,]*', line)
    if price_match:
        price_str = price_match.group().replace('€', '').replace(',', '.').strip()
        try:
            wine_data['selling_price'] = float(re.sub(r'[^\d\.]', '', price_str))
        except ValueError:
            pass
    
    # Estrai nome (resto della riga dopo rimozione annata/prezzo)
    name_line = line
    if vintage_match:
        name_line = name_line.replace(vintage_match.group(), '')
    if price_match:
        name_line = name_line.replace(price_match.group(), '')
    
    name = re.sub(r'[^\w\s\-\.\'’]', ' ', name_line).strip()
    name = re.sub(r'\s+', ' ', name)
    
    if len(name) > 2:
        wine_data['name'] = name
        wine_data['quantity'] = 1
    
    return wine_data


async def process_pdf_with_ocr(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Processa PDF come scansione usando OCR (converte pagine in immagini).
    """
    try:
        if not OCR_PDF_SUPPORT:
            raise ValueError("OCR support not available for PDF")
        
        # Converti PDF in immagini
        images = convert_from_bytes(file_content, dpi=300)
        logger.info(f"Converted PDF to {len(images)} images for OCR")
        
        # Processa ogni immagine con OCR
        all_wines = []
        for idx, image in enumerate(images):
            logger.info(f"Processing PDF page {idx + 1}/{len(images)} with OCR")
            
            # Converti immagine PIL in bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # Usa processore OCR esistente
            wines = await process_image_ocr(img_bytes.read())
            all_wines.extend(wines)
        
        logger.info(f"Extracted {len(all_wines)} wines from PDF via OCR")
        return all_wines
        
    except Exception as e:
        logger.error(f"Error processing PDF with OCR: {e}")
        raise

