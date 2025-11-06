# Test Suite per gioia-processor

## 📋 Panoramica

Questa directory contiene la suite completa di test per il refactored `gioia-processor`.

## 🧪 Test Disponibili

### Test Unitari (46 test)
- `test_parsers.py` - 9 test per parser CSV/Excel
- `test_normalization.py` - 18 test per normalizzazione header/valori
- `test_validation.py` - 12 test per validazione Pydantic
- `test_gate.py` - 7 test per routing file

### Test LLM/OCR (23 test)
- `test_llm_targeted.py` - 6 test per Stage 2 (IA mirata) con mock OpenAI
- `test_llm_extract.py` - 9 test per Stage 3 (LLM mode) con mock OpenAI
- `test_ocr.py` - 8 test per Stage 4 (OCR) con mock pytesseract

### Test Integration (7 test)
- `test_ingest_flow.py` - 7 test per pipeline completa (Stage 0-4)

### Test Endpoint (10 test)
- `test_endpoints.py` - 10 test per endpoint API (health, process-inventory, status, etc.)

**Totale: ~86 test**

## 🚀 Eseguire i Test

### Installare dipendenze
```bash
pip install -r requirements.txt
```

### Eseguire tutti i test
```bash
pytest tests/
```

### Eseguire test specifici
```bash
pytest tests/test_parsers.py
pytest tests/test_ingest_flow.py
```

### Eseguire con verbose
```bash
pytest tests/ -v
```

### Eseguire con coverage
```bash
pytest tests/ --cov=ingest --cov=core --cov=api
```

## 📁 Fixture Test

I file di test si trovano in `tests/data/`:
- `clean.csv` - CSV pulito per Stage 1
- `messy_delimiters.csv` - CSV con delimitatori misti
- `ambiguous_headers.csv` - CSV con header ambigui (Stage 2)
- `chaotic.csv` - CSV caotico per Stage 3 (LLM)

## 🔧 Mock e Fixture

### Mock OpenAI
Tutti i test LLM usano mock per simulare chiamate OpenAI senza usare API key reali.

### Mock pytesseract
I test OCR usano mock per simulare estrazione testo senza dipendenze esterne.

### Fixture comuni
Vedi `conftest.py` per fixture comuni (mock_config, sample_csv_content, etc.).

## 📊 Coverage Target

- **Unitari**: >90% coverage
- **Integration**: >80% coverage
- **Endpoint**: >70% coverage

## ⚠️ Note

- I test **non richiedono** database reale (usano mock)
- I test **non richiedono** OpenAI API key (usano mock)
- I test **non richiedono** pytesseract installato (usano mock)
- Tutti i test sono **idempotenti** e possono essere eseguiti in parallelo




