import pandas as pd
import io
import re
import logging
from typing import List, Dict, Any
from ai_processor import ai_processor

logger = logging.getLogger(__name__)

async def process_csv_file(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Processa file CSV e estrae dati sui vini usando AI
    """
    try:
        # Leggi CSV da bytes
        df = pd.read_csv(io.BytesIO(file_content))
        logger.info(f"CSV loaded with {len(df)} rows and {len(df.columns)} columns")
        
        # Usa AI per analizzare struttura CSV
        csv_text = df.to_string()
        ai_analysis = await ai_processor.analyze_csv_structure(csv_text)
        
        # Applica mapping AI se disponibile
        if ai_analysis.get('column_mapping'):
            column_mapping = ai_analysis['column_mapping']
            logger.info(f"AI detected column mapping: {column_mapping}")
        else:
            # Fallback a mapping tradizionale
            column_mapping = {
                'nome': 'name', 'vino': 'name', 'wine': 'name',
                'annata': 'vintage', 'year': 'vintage',
                'produttore': 'producer', 'producer': 'producer',
                'regione': 'region', 'region': 'region',
                'prezzo': 'price', 'price': 'price',
                'quantità': 'quantity', 'qty': 'quantity',
                'tipo': 'wine_type', 'type': 'wine_type'
            }
        
        # Normalizza nomi colonne
        df.columns = df.columns.str.lower().str.strip()
        
        # Rinomina colonne
        df = df.rename(columns=column_mapping)
        
        wines_data = []
        
        for index, row in df.iterrows():
            try:
                wine_data = extract_wine_data_from_row(row)
                if wine_data and wine_data.get('name'):
                    # Usa AI per migliorare dati vino
                    improved_wine = await ai_processor.improve_wine_data(wine_data)
                    wines_data.append(improved_wine)
            except Exception as e:
                logger.warning(f"Error processing row {index}: {e}")
                continue
        
        # Usa AI per validare e filtrare vini
        validated_wines = await ai_processor.validate_wine_data(wines_data)
        
        # Filtra vini (ora accetta tutti i vini)
        filtered_wines = filter_italian_wines(validated_wines)
        
        logger.info(f"AI processed {len(filtered_wines)} wines from CSV (confidence: {ai_analysis.get('confidence', 0)})")
        return filtered_wines
        
    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        raise

async def process_excel_file(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Processa file Excel e estrae dati sui vini usando AI
    """
    try:
        # Leggi Excel da bytes
        df = pd.read_excel(io.BytesIO(file_content))
        logger.info(f"Excel loaded with {len(df)} rows and {len(df.columns)} columns")
        
        # Usa AI per analizzare struttura Excel
        excel_text = df.to_string()
        ai_analysis = await ai_processor.analyze_csv_structure(excel_text)
        
        # Applica mapping AI se disponibile
        if ai_analysis.get('column_mapping'):
            column_mapping = ai_analysis['column_mapping']
            logger.info(f"AI detected column mapping: {column_mapping}")
        else:
            # Fallback a mapping tradizionale
            column_mapping = {
                'nome': 'name', 'vino': 'name', 'wine': 'name',
                'annata': 'vintage', 'year': 'vintage',
                'produttore': 'producer', 'producer': 'producer',
                'regione': 'region', 'region': 'region',
                'prezzo': 'price', 'price': 'price',
                'quantità': 'quantity', 'qty': 'quantity',
                'tipo': 'wine_type', 'type': 'wine_type'
            }
        
        # Normalizza nomi colonne
        df.columns = df.columns.str.lower().str.strip()
        
        # Rinomina colonne
        df = df.rename(columns=column_mapping)
        
        wines_data = []
        
        for index, row in df.iterrows():
            try:
                wine_data = extract_wine_data_from_row(row)
                if wine_data and wine_data.get('name'):
                    # Usa AI per migliorare dati vino
                    improved_wine = await ai_processor.improve_wine_data(wine_data)
                    wines_data.append(improved_wine)
            except Exception as e:
                logger.warning(f"Error processing row {index}: {e}")
                continue
        
        # Usa AI per validare e filtrare vini
        validated_wines = await ai_processor.validate_wine_data(wines_data)
        
        # Filtra vini (ora accetta tutti i vini)
        filtered_wines = filter_italian_wines(validated_wines)
        
        logger.info(f"AI processed {len(filtered_wines)} wines from Excel (confidence: {ai_analysis.get('confidence', 0)})")
        return filtered_wines
        
    except Exception as e:
        logger.error(f"Error processing Excel file: {e}")
        raise

def extract_wine_data_from_row(row: pd.Series) -> Dict[str, Any]:
    """
    Estrae dati vino da una riga del DataFrame
    """
    wine_data = {}
    
    # Nome vino
    if 'name' in row and pd.notna(row['name']):
        wine_data['name'] = str(row['name']).strip()
    
    # Annata
    if 'vintage' in row and pd.notna(row['vintage']):
        vintage = str(row['vintage']).strip()
        # Estrai solo numeri per l'annata
        vintage_match = re.search(r'\b(19|20)\d{2}\b', vintage)
        if vintage_match:
            wine_data['vintage'] = vintage_match.group()
    
    # Produttore
    if 'producer' in row and pd.notna(row['producer']):
        wine_data['producer'] = str(row['producer']).strip()
    
    # Regione
    if 'region' in row and pd.notna(row['region']):
        wine_data['region'] = str(row['region']).strip()
    
    # Prezzo
    if 'price' in row and pd.notna(row['price']):
        try:
            price_str = str(row['price']).replace(',', '.').replace('€', '').strip()
            # Estrai solo numeri e punti
            price_clean = re.sub(r'[^\d.,]', '', price_str)
            if price_clean:
                wine_data['price'] = float(price_clean.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Quantità
    if 'quantity' in row and pd.notna(row['quantity']):
        try:
            qty_str = str(row['quantity']).strip()
            qty_match = re.search(r'\d+', qty_str)
            if qty_match:
                wine_data['quantity'] = int(qty_match.group())
        except (ValueError, TypeError):
            wine_data['quantity'] = 1
    else:
        wine_data['quantity'] = 1
    
    # Tipo vino
    if 'wine_type' in row and pd.notna(row['wine_type']):
        wine_type = str(row['wine_type']).lower().strip()
        wine_data['wine_type'] = classify_wine_type(wine_type)
    else:
        # Prova a classificare dal nome
        if 'name' in wine_data:
            wine_data['wine_type'] = classify_wine_type(wine_data['name'])
    
    return wine_data

def classify_wine_type(text: str) -> str:
    """
    Classifica il tipo di vino dal testo
    """
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['rosso', 'red', 'nero', 'black', 'sangiovese', 'barbera', 'nebbiolo', 'cabernet', 'merlot', 'pinot noir', 'syrah', 'shiraz']):
        return 'rosso'
    elif any(word in text_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon', 'riesling', 'gewürztraminer', 'moscato']):
        return 'bianco'
    elif any(word in text_lower for word in ['rosato', 'rosé', 'rose', 'pink']):
        return 'rosato'
    elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco', 'moscato', 'frizzante', 'sparkling', 'cava', 'crémant']):
        return 'spumante'
    else:
        return 'sconosciuto'

def clean_wine_name(name: str) -> str:
    """
    Pulisce il nome del vino
    """
    if not name:
        return ""
    
    # Rimuovi caratteri speciali eccessivi
    cleaned = re.sub(r'[^\w\s\-\.]', ' ', name)
    # Rimuovi spazi multipli
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def filter_italian_wines(wines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filtra vini per mantenere solo quelli italiani (funzione rimossa - ora accetta tutti i vini)
    """
    # Ora accetta tutti i vini, non solo quelli italiani
    return wines