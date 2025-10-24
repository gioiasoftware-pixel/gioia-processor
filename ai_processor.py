import openai
import json
import logging
import os
from typing import List, Dict, Any, Optional
import tiktoken

logger = logging.getLogger(__name__)

class AIProcessor:
    """Processore AI per analisi intelligente di inventari vini"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.encoding = tiktoken.get_encoding("cl100k_base")
        
    def count_tokens(self, text: str) -> int:
        """Conta i token per evitare limiti OpenAI"""
        return len(self.encoding.encode(text))
    
    async def analyze_csv_structure(self, csv_content: str) -> Dict[str, Any]:
        """
        Analizza struttura CSV con AI per identificare colonne vini
        """
        try:
            # Prepara prompt per analisi CSV
            prompt = f"""
Analizza questo file CSV di inventario vini e identifica:
1. Quali colonne contengono: nome vino, annata, produttore, regione/paese, prezzo, quantità, tipo vino
2. Mappa le colonne trovate nel formato JSON
3. Identifica il separatore (virgola, punto e virgola, tab)
4. Suggerisci miglioramenti per la struttura

CSV Content:
{csv_content[:2000]}  # Limita a 2000 caratteri per evitare limiti token

Rispondi SOLO con JSON nel formato:
{{
    "column_mapping": {{
        "name": "nome_colonna_vino",
        "vintage": "nome_colonna_annata",
        "producer": "nome_colonna_produttore",
        "region": "nome_colonna_regione",
        "price": "nome_colonna_prezzo",
        "quantity": "nome_colonna_quantita",
        "wine_type": "nome_colonna_tipo"
    }},
    "separator": "virgola|punto_virgola|tab",
    "suggestions": ["suggerimento1", "suggerimento2"],
    "confidence": 0.95
}}
"""
            
            # Verifica limiti token
            if self.count_tokens(prompt) > 4000:
                logger.warning("Prompt troppo lungo, riduco contenuto")
                prompt = prompt[:1500] + "..."
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Sei un esperto di vini e analisi dati. Analizza file CSV di inventari vini con precisione."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info(f"AI analysis completed with confidence: {result.get('confidence', 0)}")
            return result
            
        except Exception as e:
            logger.error(f"Error in AI CSV analysis: {e}")
            return {
                "column_mapping": {},
                "separator": "virgola",
                "suggestions": [],
                "confidence": 0.0
            }
    
    async def extract_wines_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Estrae dati vini da testo usando AI
        """
        try:
            prompt = f"""
Analizza questo testo di inventario vini e estrai tutti i vini con i loro dettagli.

Testo:
{text[:3000]}  # Limita per evitare limiti token

Per ogni vino trovato, estrai:
- Nome vino
- Annata (solo anno 4 cifre)
- Produttore
- Regione/Paese
- Prezzo (solo numero)
- Quantità (solo numero)
- Tipo vino (rosso/bianco/rosato/spumante)

Rispondi SOLO con JSON array:
[
    {{
        "name": "Nome Vino",
        "vintage": "2020",
        "producer": "Nome Produttore",
        "region": "Regione/Paese",
        "price": 25.50,
        "quantity": 12,
        "wine_type": "rosso"
    }}
]
"""
            
            # Verifica limiti token
            if self.count_tokens(prompt) > 4000:
                logger.warning("Prompt troppo lungo, riduco contenuto")
                prompt = prompt[:2000] + "..."
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Sei un esperto di vini. Estrai dati vini da testi con massima precisione. Usa solo anni 4 cifre per le annate."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            wines = json.loads(response.choices[0].message.content)
            logger.info(f"AI extracted {len(wines)} wines from text")
            return wines
            
        except Exception as e:
            logger.error(f"Error in AI wine extraction: {e}")
            return []
    
    async def classify_wine_type(self, wine_name: str, additional_info: str = "") -> str:
        """
        Classifica tipo di vino usando AI
        """
        try:
            prompt = f"""
Classifica il tipo di vino basandoti su nome e informazioni.

Nome vino: {wine_name}
Informazioni aggiuntive: {additional_info}

Scegli SOLO tra: rosso, bianco, rosato, spumante, sconosciuto

Rispondi con una sola parola.
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Sei un esperto di vini. Classifica il tipo di vino basandoti sul nome e caratteristiche."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            wine_type = response.choices[0].message.content.strip().lower()
            logger.info(f"AI classified '{wine_name}' as '{wine_type}'")
            return wine_type
            
        except Exception as e:
            logger.error(f"Error in AI wine classification: {e}")
            return "sconosciuto"
    
    async def improve_wine_data(self, wine_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migliora dati vino usando AI per correggere errori e completare informazioni
        """
        try:
            prompt = f"""
Migliora e completa questi dati di un vino:

Dati attuali:
{json.dumps(wine_data, ensure_ascii=False, indent=2)}

Correzioni da applicare:
1. Corregge errori di ortografia nel nome vino
2. Completa informazioni mancanti se possibile
3. Standardizza formato nomi produttori
4. Verifica e corregge annate
5. Standardizza nomi regioni/paesi

Rispondi SOLO con JSON migliorato:
{{
    "name": "Nome Vino Corretto",
    "vintage": "2020",
    "producer": "Nome Produttore Standardizzato",
    "region": "Regione/Paese",
    "price": 25.50,
    "quantity": 12,
    "wine_type": "rosso",
    "notes": "Note aggiuntive se rilevanti"
}}
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Sei un esperto di vini. Migliora e completa dati vini con precisione e conoscenza del settore."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            improved_data = json.loads(response.choices[0].message.content)
            logger.info(f"AI improved wine data for: {improved_data.get('name', 'Unknown')}")
            return improved_data
            
        except Exception as e:
            logger.error(f"Error in AI wine data improvement: {e}")
            return wine_data
    
    async def validate_wine_data(self, wines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Valida e filtra dati vini usando AI
        """
        try:
            if not wines:
                return []
            
            prompt = f"""
Valida questi dati di vini e rimuovi duplicati o dati non validi:

Vini:
{json.dumps(wines[:10], ensure_ascii=False, indent=2)}  # Limita a 10 vini per evitare limiti

Criteri di validazione:
1. Nome vino deve essere presente e valido
2. Annata deve essere un anno valido (1900-2024)
3. Prezzo deve essere un numero positivo
4. Quantità deve essere un numero positivo
5. Rimuovi duplicati basati su nome e annata

Rispondi SOLO con JSON array dei vini validi:
[
    {{
        "name": "Nome Vino",
        "vintage": "2020",
        "producer": "Produttore",
        "region": "Regione/Paese",
        "price": 25.50,
        "quantity": 12,
        "wine_type": "rosso"
    }}
]
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Sei un esperto di vini. Valida e filtra dati vini rimuovendo duplicati e dati non validi."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            validated_wines = json.loads(response.choices[0].message.content)
            logger.info(f"AI validated {len(validated_wines)} wines from {len(wines)} original")
            return validated_wines
            
        except Exception as e:
            logger.error(f"Error in AI wine validation: {e}")
            return wines

# Istanza globale del processore AI
ai_processor = AIProcessor()
