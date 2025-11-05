# 🐛 Diagnostica Bug Test Fase 9

**Data analisi**: 2025-01-XX  
**Scope**: Test Phase 9 (Mock, Local, Performance, Costi LLM, Error Handling)

---

## 🔍 Metodologia Analisi

Analisi statica del codice dei test per identificare:
1. **Errori di sintassi** - Import mancanti, chiamate async non corrette
2. **Errori logici** - Mock non configurati correttamente, asserzioni errate
3. **Inconsistenze** - Test che non verificano correttamente il comportamento atteso
4. **Problemi di integrazione** - Mock non compatibili con codice reale

---

## 🐛 BUG TROVATI

### **BUG #1: Verifica modello LLM nei test costi - call_args non strutturato correttamente**

**File**: `tests/test_llm_costs.py`  
**Test**: `test_stage2_uses_gpt4o_mini`, `test_stage3_uses_gpt4o`  
**Linee**: 58-65, 107-114

**Problema**:
```python
call_args = mock_client.chat.completions.create.call_args
if call_args and 'kwargs' in call_args:
    model = call_args.kwargs.get('model', '')
```

**Analisi**:
- `call_args` è una tupla `(args, kwargs)`, non un dict con chiave `'kwargs'`
- La verifica `'kwargs' in call_args` è sempre falsa
- Dovrebbe essere `call_args[1].get('model')` o `call_args.kwargs.get('model')` se `call_args` è un `Call` object

**Impatto**: ⚠️ **MEDIO** - Test non verificano correttamente che il modello corretto sia usato

**Fix necessario**:
```python
call_args = mock_client.chat.completions.create.call_args
if call_args:
    # call_args è una tupla (args, kwargs)
    kwargs = call_args[1] if len(call_args) > 1 else {}
    model = kwargs.get('model', '')
    assert 'gpt-4o-mini' in model or model == 'gpt-4o-mini'
```

---

### **BUG #2: Test error handling - chiamata async senza decorator**

**File**: `tests/test_error_handling.py`  
**Test**: `test_invalid_json_from_ai_handled`  
**Linea**: 421

**Problema**:
```python
def test_invalid_json_from_ai_handled(self):  # NO @pytest.mark.asyncio
    ...
    mapping = await disambiguate_headers(headers, {})  # await senza async
```

**Analisi**:
- Funzione non è `async` ma usa `await`
- Manca decorator `@pytest.mark.asyncio`
- Causerà `SyntaxError` o `RuntimeError`

**Impatto**: 🔴 **ALTO** - Test fallirà con errore

**Fix necessario**:
```python
@pytest.mark.asyncio
async def test_invalid_json_from_ai_handled(self):
    ...
```

---

### **BUG #3: Mock OpenAI client - call_args non traccia parametri chiamata**

**File**: `tests/mocks.py`  
**Classe**: `MockOpenAIClient`  
**Linee**: 38-63

**Problema**:
- `MockOpenAIClient` configura `chat.completions.create` come `Mock(return_value=...)` 
- Ma quando il codice reale chiama `client.chat.completions.create(model=..., messages=...)`, i parametri non sono tracciati correttamente
- I test che verificano `call_args.kwargs.get('model')` non funzioneranno

**Analisi**:
- Il mock ritorna un valore ma non traccia i parametri passati
- `call_args` potrebbe essere `None` o non avere la struttura attesa

**Impatto**: ⚠️ **MEDIO** - Test che verificano parametri non funzioneranno

**Fix necessario**:
- Il mock dovrebbe essere configurato per tracciare chiamate: `Mock(side_effect=...)` o usare `call_args_list`

---

### **BUG #4: Test local - mock batch_insert_wines non compatibile**

**File**: `tests/test_phase9_local.py`  
**Test**: `test_upload_clean_csv`, `test_upload_ambiguous_headers_csv`, etc.  
**Linee**: 59, 120, etc.

**Problema**:
```python
mock_insert.return_value = AsyncMock(return_value=True)
```

**Analisi**:
- `batch_insert_wines` è una funzione async reale
- Il mock `AsyncMock(return_value=True)` potrebbe non essere compatibile
- Dovrebbe essere `AsyncMock(return_value=True)` o meglio ancora patchare direttamente la funzione

**Impatto**: ⚠️ **MEDIO** - Test potrebbe fallire se chiamata reale non mockata correttamente

**Fix necessario**:
```python
mock_insert.return_value = True  # o AsyncMock() con return_value
# Oppure usare patch direttamente sulla funzione
```

---

### **BUG #5: Test error handling - disambiguate_headers chiamata senza await**

**File**: `tests/test_error_handling.py`  
**Test**: `test_invalid_json_from_ai_handled`  
**Linea**: 421

**Problema**:
- Funzione non async ma usa `await disambiguate_headers()`
- `disambiguate_headers` è async (verificato in `llm_targeted.py`)

**Impatto**: 🔴 **ALTO** - Test fallirà

**Fix necessario**: Aggiungere `@pytest.mark.asyncio` e `async def`

---

### **BUG #6: Test performance - parse_classic non async ma test usa async**

**File**: `tests/test_performance.py`  
**Test**: `test_stage1_small_csv_under_2s`  
**Linea**: 24

**Problema**:
- `parse_classic` è funzione sincrona (verificato in `parser.py`)
- Test è sincrono (corretto) ma potrebbe essere confuso con altri test async

**Impatto**: ✅ **NESSUNO** - Test corretto, solo nota

---

### **BUG #7: Test costi LLM - verifica call_args con struttura Mock errata**

**File**: `tests/test_llm_costs.py`  
**Test**: `test_stage2_max_tokens_respected`, `test_stage3_max_tokens_reasonable`  
**Linee**: 213-220, 251-260

**Problema**:
```python
call_args = mock_client.chat.completions.create.call_args
if call_args and 'kwargs' in call_args:
    max_tokens_called = call_args.kwargs.get('max_tokens')
```

**Analisi**:
- Stesso problema di BUG #1
- `call_args` è tupla `(args, kwargs)`, non dict

**Impatto**: ⚠️ **MEDIO** - Test non verificano correttamente max_tokens

**Fix necessario**: Vedere BUG #1

---

### **BUG #8: Test error handling - extract_llm_mode signature non corretta**

**File**: `tests/test_error_handling.py`  
**Test**: `test_stage3_failure_handled`  
**Linea**: 216

**Problema**:
```python
wines_data, metrics, decision = await extract_llm_mode(
    text_chunk, "test.txt", telegram_id=123, business_name="Test"
)
```

**Analisi**:
- Verificare signature reale di `extract_llm_mode` in `llm_extract.py`
- Potrebbe ritornare 4 valori (incluso `stage_used`) o 3 valori

**Impatto**: ⚠️ **MEDIO** - Test potrebbe fallire se signature non corretta

**Fix necessario**: Verificare signature e aggiustare unpacking

---

### **BUG #9: Import mancante - RateLimitError in test_phase9_mocks.py**

**File**: `tests/test_phase9_mocks.py`  
**Linea**: 9

**Problema**:
```python
from openai import RateLimitError
```

**Analisi**:
- Se `openai` non è installato o versione non supporta `RateLimitError`, test fallirà
- Inoltre, il mock in `mocks.py` crea un errore custom invece di usare `RateLimitError` reale

**Impatto**: ⚠️ **BASSO** - Solo se openai non installato o versione vecchia

**Fix necessario**: 
- Usare try/except per import o
- Usare mock custom (già fatto in `mocks.py`)

---

### **BUG #10: Test local - get_db mock non compatibile con async generator**

**File**: `tests/test_phase9_local.py`  
**Test**: `test_upload_clean_csv`, etc.  
**Linee**: 47-49

**Problema**:
```python
async def db_gen():
    yield mock_db
mock_get_db.return_value = db_gen()
```

**Analisi**:
- `get_db()` è un async generator (usa `async for`)
- Il mock crea una funzione async che yield, ma `return_value` potrebbe non funzionare correttamente
- Dovrebbe essere `mock_get_db.return_value = db_gen()` chiamato correttamente

**Impatto**: ⚠️ **MEDIO** - Test potrebbe fallire se async generator non mockato correttamente

**Fix necessario**: 
```python
async def db_gen():
    yield mock_db
mock_get_db.return_value = db_gen()
# Oppure usare AsyncMock con side_effect
```

---

## 📊 Riepilogo Bug

| Bug # | Severità | File | Test | Status |
|-------|----------|------|------|--------|
| #1 | ⚠️ MEDIO | `test_llm_costs.py` | `test_stage2_uses_gpt4o_mini`, `test_stage3_uses_gpt4o` | Verifica modello non funziona |
| #2 | 🔴 ALTO | `test_error_handling.py` | `test_invalid_json_from_ai_handled` | async/await non corretto |
| #3 | ⚠️ MEDIO | `mocks.py` | `MockOpenAIClient` | call_args non traccia parametri |
| #4 | ⚠️ MEDIO | `test_phase9_local.py` | Tutti i test upload | Mock batch_insert_wines |
| #5 | 🔴 ALTO | `test_error_handling.py` | `test_invalid_json_from_ai_handled` | Chiamata async senza decorator |
| #6 | ✅ NESSUNO | `test_performance.py` | `test_stage1_small_csv_under_2s` | Solo nota |
| #7 | ⚠️ MEDIO | `test_llm_costs.py` | `test_stage2_max_tokens_respected` | Verifica max_tokens non funziona |
| #8 | ⚠️ MEDIO | `test_error_handling.py` | `test_stage3_failure_handled` | Signature extract_llm_mode |
| #9 | ⚠️ BASSO | `test_phase9_mocks.py` | Import RateLimitError | Import opzionale |
| #10 | ⚠️ MEDIO | `test_phase9_local.py` | Tutti i test upload | Mock get_db async generator |

**Totale**: 10 bug trovati
- 🔴 **ALTO**: 2 bug (bloccanti)
- ⚠️ **MEDIO**: 7 bug (funzionali ma non bloccanti)
- ⚠️ **BASSO**: 1 bug (minore)

---

## 🔧 Fix Applicati

### **✅ Fix Prioritari (Bloccanti)**
1. **✅ BUG #2 e #5**: Fix async/await in `test_invalid_json_from_ai_handled`
   - Aggiunto `@pytest.mark.asyncio` e `async def`
   
2. **✅ BUG #8**: Fix signature `extract_llm_mode` e unpacking
   - Corretto: `extract_llm_mode(file_content: bytes, file_name: str, ext: str)` → ritorna `(wines_data, metrics, decision)`
   - Fix test: `text_chunk.encode('utf-8')` invece di `text_chunk` come stringa
   - Fix test: `process_file()` ritorna `(wines_data, metrics, decision, stage_used)` - 4 valori

### **✅ Fix Funzionali**
3. **✅ BUG #1 e #7**: Fix verifica `call_args` per modello e max_tokens
   - Corretto: `call_args` è tupla `(args, kwargs)`, non dict
   - Fix: `kwargs = call_args[1] if len(call_args) > 1 else {}`
   - Applicato a: `test_stage2_uses_gpt4o_mini`, `test_stage3_uses_gpt4o`, `test_stage2_max_tokens_respected`, `test_stage3_max_tokens_reasonable`

4. **✅ BUG #6**: Fix test `test_metrics_schema_score`
   - `calculate_schema_score` prende DataFrame, non lista
   - Fix: Creare DataFrame con pandas

5. **✅ BUG #6**: Fix test `test_metrics_valid_rows`
   - Rimosso `@pytest.mark.asyncio` (funzione sincrona)

6. **✅ BUG #8**: Fix test `test_pipeline_clean_csv` e `test_pipeline_ambiguous_headers`
   - Corretto unpacking: `process_file()` ritorna 4 valori, non dict

### **⚠️ Fix Da Applicare (Funzionali)**
7. **BUG #3**: Migliorare `MockOpenAIClient` per tracciare parametri
   - Il mock attuale non traccia correttamente i parametri passati
   - Suggerimento: Usare `Mock` con `side_effect` o verificare `call_args_list`

8. **BUG #4**: Fix mock `batch_insert_wines`
   - Verificare che mock sia compatibile con chiamata reale async
   - Suggerimento: Usare `AsyncMock()` direttamente

9. **BUG #10**: Fix mock `get_db` async generator
   - Verificare che async generator funzioni correttamente
   - Suggerimento: Usare `AsyncMock` con `side_effect` che yield

### **⚠️ Fix Da Applicare (Minori)**
10. **BUG #9**: Gestire import RateLimitError opzionale
    - Aggiungere try/except per import opzionale

---

## 📝 Note

- La maggior parte dei bug riguarda la verifica dei parametri passati ai mock OpenAI
- I test che verificano `call_args.kwargs` non funzioneranno correttamente
- I test async/await sono corretti nella maggior parte dei casi, tranne `test_invalid_json_from_ai_handled`
- I mock sono configurati correttamente per ritornare valori, ma non tracciano parametri per verifiche

---

**Prossimi passi**: 
1. ✅ Fix bug prioritari (Priorità 1) - COMPLETATO
2. ✅ Fix bug funzionali principali (Priorità 2) - COMPLETATO
3. ⚠️ Migliorare mock OpenAI per tracciare parametri (BUG #3)
4. ⚠️ Verificare mock async generator (BUG #10)
5. ⚠️ Testare tutti i fix applicati con pytest

**Status Fix**: 
- ✅ **5 bug fix applicati** (BUG #1, #2, #5, #6, #7, #8)
- ⚠️ **3 bug fix da applicare** (BUG #3, #4, #10)
- ⚠️ **1 bug minore** (BUG #9)

**Test Fix Applicati**:
- `test_invalid_json_from_ai_handled` - Aggiunto async/await ✅
- `test_stage2_uses_gpt4o_mini` - Fix call_args ✅
- `test_stage3_uses_gpt4o` - Fix call_args ✅
- `test_stage2_max_tokens_respected` - Fix call_args ✅
- `test_stage3_max_tokens_reasonable` - Fix call_args ✅
- `test_stage3_failure_handled` - Fix signature extract_llm_mode ✅
- `test_all_stages_fail_user_friendly_error` - Fix signature process_file ✅
- `test_database_insert_error_handled` - Fix signature process_file ✅
- `test_metrics_schema_score` - Fix signature calculate_schema_score ✅
- `test_metrics_valid_rows` - Rimosso async ✅
- `test_pipeline_clean_csv` - Fix signature process_file ✅
- `test_pipeline_ambiguous_headers` - Fix signature process_file ✅

