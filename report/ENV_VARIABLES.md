# 📋 Variabili Ambiente - Gioia Processor

## 🔧 Variabili Obbligatorie

### Database
```env
DATABASE_URL=postgresql://user:password@host:port/database
```
**Descrizione**: URL connessione PostgreSQL  
**Esempio**: `postgresql://postgres:password@localhost:5432/gioia_db`

---

## ⚙️ Variabili Opzionali

### Server
```env
PORT=8001
```
**Descrizione**: Porta server FastAPI  
**Default**: `8001`

---

### OpenAI (AI Features)
```env
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```
**Descrizione**: 
- `OPENAI_API_KEY`: API key OpenAI (se mancante, AI features disabilitate)
- `OPENAI_MODEL`: Modello OpenAI default  
**Default**: `gpt-4o-mini`

---

### Feature Flags
```env
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true
```
**Descrizione**: 
- `IA_TARGETED_ENABLED`: Abilita Stage 2 (IA mirata per header ambigui)
- `LLM_FALLBACK_ENABLED`: Abilita Stage 3 (LLM mode per file caotici)
- `OCR_ENABLED`: Abilita Stage 4 (OCR per immagini/PDF)  
**Default**: Tutti `true`

---

### Soglie e Configurazione
```env
CSV_MAX_ATTEMPTS=3
SCHEMA_SCORE_TH=0.7
MIN_VALID_ROWS=0.6
HEADER_CONFIDENCE_TH=0.75
```
**Descrizione**: 
- `CSV_MAX_ATTEMPTS`: Max tentativi parsing CSV
- `SCHEMA_SCORE_TH`: Soglia schema_score per Stage 1 (0.0-1.0)
- `MIN_VALID_ROWS`: Soglia valid_rows per Stage 1 (0.0-1.0)
- `HEADER_CONFIDENCE_TH`: Confidence threshold per header mapping (0.0-1.0)  
**Default**: 
- `CSV_MAX_ATTEMPTS=3`
- `SCHEMA_SCORE_TH=0.7`
- `MIN_VALID_ROWS=0.6`
- `HEADER_CONFIDENCE_TH=0.75`

---

### Stage 2 (IA Mirata)
```env
BATCH_SIZE_AMBIGUOUS_ROWS=20
MAX_LLM_TOKENS=300
LLM_MODEL_TARGETED=gpt-4o-mini
```
**Descrizione**: 
- `BATCH_SIZE_AMBIGUOUS_ROWS`: Batch size per righe ambigue (1-100)
- `MAX_LLM_TOKENS`: Max token per chiamate IA mirata (1-4000)
- `LLM_MODEL_TARGETED`: Modello LLM per Stage 2 (economico)  
**Default**: 
- `BATCH_SIZE_AMBIGUOUS_ROWS=20`
- `MAX_LLM_TOKENS=300`
- `LLM_MODEL_TARGETED=gpt-4o-mini`

---

### Stage 3 (LLM Mode)
```env
LLM_MODEL_EXTRACT=gpt-4o
```
**Descrizione**: Modello LLM per Stage 3 (robusto)  
**Default**: `gpt-4o`

---

### Stage 4 (OCR)
```env
OCR_EXTENSIONS=pdf,jpg,jpeg,png
```
**Descrizione**: Estensioni supportate per OCR (separate da virgola)  
**Default**: `pdf,jpg,jpeg,png`

---

### Database Batch
```env
DB_INSERT_BATCH_SIZE=500
```
**Descrizione**: Batch size per insert DB (1-10000)  
**Default**: `500`

---

### Processor Info
```env
PROCESSOR_NAME=Gioia Processor
PROCESSOR_VERSION=2.0.0
```
**Descrizione**: Info processor  
**Default**: 
- `PROCESSOR_NAME=Gioia Processor`
- `PROCESSOR_VERSION=2.0.0`

---

## 📝 Esempio `.env` Completo

```env
# Database (OBBLIGATORIO)
DATABASE_URL=postgresql://postgres:password@localhost:5432/gioia_db

# Server
PORT=8001

# OpenAI (opzionale - se mancante, AI disabilitata)
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini

# Feature Flags
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true

# Soglie
SCHEMA_SCORE_TH=0.7
MIN_VALID_ROWS=0.6
HEADER_CONFIDENCE_TH=0.75

# Stage 2
BATCH_SIZE_AMBIGUOUS_ROWS=20
MAX_LLM_TOKENS=300
LLM_MODEL_TARGETED=gpt-4o-mini

# Stage 3
LLM_MODEL_EXTRACT=gpt-4o

# Stage 4
OCR_EXTENSIONS=pdf,jpg,jpeg,png

# Database Batch
DB_INSERT_BATCH_SIZE=500
```

---

## 🧪 Come Testare

### Setup Locale
1. Copia `.env.example` in `.env`:
   ```bash
   cp .env.example .env
   ```

2. Modifica `.env` con i tuoi valori:
   - Imposta `DATABASE_URL` corretto
   - (Opzionale) Imposta `OPENAI_API_KEY` se vuoi testare AI features

3. Installa dipendenze:
   ```bash
   pip install -r requirements.txt
   ```

4. Testa con file fixture:
   ```bash
   pytest tests/test_phase9_local.py -v
   ```

### Test senza OpenAI
Se non hai `OPENAI_API_KEY`, i test useranno mock OpenAI automaticamente.

---

## ⚠️ Note Importanti

1. **DATABASE_URL è obbligatorio**: Senza database, il processor non funziona.

2. **OPENAI_API_KEY è opzionale**: Se mancante, AI features sono disabilitate ma il processor funziona comunque (Stage 1).

3. **Feature Flags**: Puoi disabilitare singoli stage per testare:
   - `IA_TARGETED_ENABLED=false` → Disabilita Stage 2
   - `LLM_FALLBACK_ENABLED=false` → Disabilita Stage 3
   - `OCR_ENABLED=false` → Disabilita Stage 4

4. **Soglie**: Aumenta `SCHEMA_SCORE_TH` o `MIN_VALID_ROWS` per essere più selettivi (più file vanno a Stage 2/3).

5. **Costi LLM**: 
   - Stage 2 usa `gpt-4o-mini` (economico)
   - Stage 3 usa `gpt-4o` (robusto ma costoso)
   - Usa `MAX_LLM_TOKENS` per limitare costi.

