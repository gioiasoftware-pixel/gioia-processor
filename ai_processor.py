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

IMPORTANTE: La colonna QUANTITÀ è OBBLIGATORIA e DEVE essere sempre identificata.
Cerca colonne che potrebbero rappresentare quantità anche se hanno nomi diversi come:
"q iniziale", "q. iniziale", "quantità iniziale", "qty", "qta", "pezzi", "bottiglie", "scorta", "stock", "disp", "disponibilità".

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

NOTA: Se trovi una colonna che sembra rappresentare quantità ma non è esplicitamente chiamata "quantità", 
usa comunque "quantity" come chiave nel mapping. La colonna quantity DEVE essere sempre presente.
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
        Migliora dati vino usando AI per correggere errori e completare informazioni.
        Usa GPT-4 per massima qualità (usato solo per OCR dove i dati possono essere più sporchi).
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
            logger.info(f"AI improved wine data (GPT-4) for: {improved_data.get('name', 'Unknown')}")
            return improved_data
            
        except Exception as e:
            logger.error(f"Error in AI wine data improvement: {e}")
            return wine_data
    
    async def validate_wine_data(self, wines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Valida e filtra dati vini usando AI.
        Processa in batch per gestire grandi inventari.
        """
        try:
            if not wines:
                return []
            
            # Processa in batch di 20 vini alla volta per evitare limiti token
            batch_size = 20
            all_validated_wines = []
            
            for i in range(0, len(wines), batch_size):
                batch = wines[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(wines) + batch_size - 1) // batch_size
                
                logger.info(f"Validating wine batch {batch_num}/{total_batches} ({len(batch)} wines)")
                
                prompt = f"""
Valida questi dati di vini e rimuovi SOLO duplicati esatti (stesso nome E stessa annata):

Vini da validare:
{json.dumps(batch, ensure_ascii=False, indent=2)}

Criteri di validazione (MOLTO PERMISSIVI):
1. Nome vino deve essere presente (non vuoto) - ACCETTA qualsiasi nome valido
2. Annata: accetta qualsiasi anno (anche null/mancante) - NON FILTRARE se manca
3. Prezzo: accetta qualsiasi valore (anche null/mancante) - NON FILTRARE se manca
4. Quantità: accetta qualsiasi valore (anche null/mancante) - NON FILTRARE se manca
5. Rimuovi SOLO duplicati esatti: stesso nome E stessa annata (se presente)

IMPORTANTE:
- NON rimuovere vini se mancano dati (prezzo, quantità, annata)
- NON rimuovere vini se i dati sembrano "strani" o non standard
- MANTIENI TUTTI I VINI tranne duplicati esatti
- Se un vino ha nome, deve essere incluso

Rispondi SOLO con JSON array di TUTTI i vini validi (mantieni tutti tranne duplicati):
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
                
                # Controlla dimensione prompt
                if self.count_tokens(prompt) > 8000:
                    # Se troppo grande, riduci batch
                    logger.warning(f"Prompt troppo grande ({self.count_tokens(prompt)} tokens), riduco batch a {len(batch) // 2}")
                    # Processa metà batch alla volta
                    mid = len(batch) // 2
                    sub_batch1 = batch[:mid]
                    sub_batch2 = batch[mid:]
                    
                    for sub_batch in [sub_batch1, sub_batch2]:
                        if not sub_batch:
                            continue
                        sub_prompt = prompt.replace(json.dumps(batch, ensure_ascii=False, indent=2), 
                                                   json.dumps(sub_batch, ensure_ascii=False, indent=2))
                        try:
                            response = self.client.chat.completions.create(
                                model="gpt-4",
                                messages=[
                                    {"role": "system", "content": "Sei un esperto di vini. Valida e filtra dati vini rimuovendo SOLO duplicati esatti. MANTIENI tutti i vini validi anche con dati parziali."},
                                    {"role": "user", "content": sub_prompt}
                                ],
                                temperature=0.1,
                                max_tokens=4000
                            )
                            
                            validated_batch = json.loads(response.choices[0].message.content)
                            all_validated_wines.extend(validated_batch)
                        except Exception as e:
                            logger.warning(f"Error validating sub-batch: {e}, keeping original wines")
                            all_validated_wines.extend(sub_batch)
                    continue
                
                try:
                    response = self.client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": "Sei un esperto di vini. Valida e filtra dati vini rimuovendo SOLO duplicati esatti. MANTIENI tutti i vini validi anche con dati parziali."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1,
                        max_tokens=4000
                    )
                    
                    validated_batch = json.loads(response.choices[0].message.content)
                    all_validated_wines.extend(validated_batch)
                    logger.info(f"Batch {batch_num}/{total_batches}: validated {len(validated_batch)}/{len(batch)} wines")
                    
                except Exception as e:
                    logger.warning(f"Error validating batch {batch_num}: {e}, keeping original wines")
                    # Se errore, mantieni vini originali del batch
                    all_validated_wines.extend(batch)
            
            # Rimuovi duplicati finali manualmente (stesso nome + stessa annata)
            seen = set()
            final_wines = []
            for wine in all_validated_wines:
                key = (wine.get('name', '').lower().strip(), str(wine.get('vintage', '')))
                if key not in seen:
                    seen.add(key)
                    final_wines.append(wine)
            
            logger.info(f"AI validated {len(final_wines)} wines from {len(wines)} original (removed {len(wines) - len(final_wines)} duplicates)")
            return final_wines
            
        except Exception as e:
            logger.error(f"Error in AI wine validation: {e}")
            # In caso di errore, ritorna tutti i vini originali
            logger.warning("Returning all original wines due to validation error")
            return wines

# Istanza globale del processore AI
ai_processor = AIProcessor()
