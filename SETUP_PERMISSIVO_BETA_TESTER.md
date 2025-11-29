# 🚀 Setup Configurazione Permissiva - Beta Tester

**Guida Rapida**: Come configurare il processor per accettare inventari già puliti

---

## 📍 Servizio da Configurare

**Directory/Servizio**: `gioia-processor` (su Railway)

---

## ✅ Variabili da Aggiungere in Railway

Vai su **Railway Dashboard** → Progetto `gioia-processor` → **Settings** → **Variables**

Aggiungi queste **4 variabili**:

```env
SCHEMA_SCORE_TH=0.50
MIN_VALID_ROWS=0.50
HEADER_CONFIDENCE_TH=0.50
NORMALIZATION_POLICY=SAFE
```

**Opzionale** (per essere ancora più permissivi):

```env
LLM_STRICT_OVERRIDE_DELTA=0.05
```

---

## 📋 Variabili Esistenti (Verifica che ci siano)

Queste dovrebbero già essere configurate. **Verifica**:

```env
DATABASE_URL=postgresql://user:password@host:port/database
OPENAI_API_KEY=sk-your-openai-api-key-here
IA_TARGETED_ENABLED=true
LLM_FALLBACK_ENABLED=true
OCR_ENABLED=true
```

---

## 🔄 Dopo la Configurazione

1. **Railway rileva automaticamente** le modifiche e fa redeploy
2. **Attendi deploy completato** (2-3 minuti)
3. **Verifica** con health check: `GET /health`
4. **Testa** con un file pulito e verifica nei log che passi Stage 1

---

## 📊 Risultati Attesi

**Prima** (soglie rigide):
- 30-40% file vanno a Stage 2 (AI)
- Costo: €0.01-0.02 per file

**Dopo** (soglie permissive):
- 5-10% file vanno a Stage 2 (solo problematici)
- Costo: €0 per file puliti

**Risparmio**: ~90% costi AI per file puliti

---

## 📚 Documentazione Completa

- `VARIABILI_AMBIENTE_RAILWAY.md` - Tutte le variabili dettagliate
- `CONFIGURAZIONE_PERMISSIVA_BETA_TESTER.md` - Guida completa

---

**Versione**: 1.0  
**Data**: 2025-01-XX

