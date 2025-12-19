# Istruzioni Migrazione 006: telegram_id nullable

## 📋 Panoramica
Questa migrazione rende il campo `telegram_id` nella tabella `users` nullable, permettendo la creazione di utenti senza telegram_id (solo con business_name).

## 🚀 Opzione 1: Esecuzione Manuale con psql (Consigliata)

### Prerequisiti
- Accesso al database PostgreSQL
- `psql` installato sulla macchina
- Variabile d'ambiente `DATABASE_URL` configurata OPPURE credenziali database

### Esecuzione

#### Con variabile DATABASE_URL:
```bash
cd gioia-processor
psql $DATABASE_URL -f migrations/006_make_telegram_id_nullable.sql
```

#### Con credenziali esplicite:
```bash
cd gioia-processor
psql -h localhost -U username -d database_name -f migrations/006_make_telegram_id_nullable.sql
```

#### Con connessione string completa:
```bash
cd gioia-processor
psql "postgresql://user:password@host:5432/dbname" -f migrations/006_make_telegram_id_nullable.sql
```

### Verifica Migrazione
Dopo l'esecuzione, verifica che la migrazione sia stata applicata:

```sql
-- Verifica che telegram_id sia nullable
SELECT column_name, is_nullable, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'telegram_id';

-- Verifica che l'indice unique parziale esista
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'users' AND indexname = 'uq_users_telegram_id';

-- Test: prova a creare un utente senza telegram_id
INSERT INTO users (business_name, onboarding_completed) 
VALUES ('Test Business', true) 
RETURNING id, telegram_id, business_name;
```

---

## 🐍 Opzione 2: Esecuzione Automatica con Script Python

### Prerequisiti
- Python 3.8+
- Dipendenze progetto installate (`pip install -r requirements.txt`)
- Variabile d'ambiente `DATABASE_URL` configurata

### Esecuzione

```bash
cd gioia-processor
python scripts/run_migration_006.py
```

Lo script:
- ✅ Legge automaticamente `DATABASE_URL` da variabili d'ambiente o `.env`
- ✅ Esegue tutti gli statement SQL del file migrazione
- ✅ Gestisce transazioni e rollback in caso di errore
- ✅ Fornisce logging dettagliato

### Output Atteso
```
INFO:__main__:Eseguendo migrazione 006: 006_make_telegram_id_nullable.sql
INFO:__main__:Database URL: postgresql+asyncpg://...
INFO:__main__:Eseguendo statement 1/5...
INFO:__main__:Eseguendo blocco DO (statement 2)...
INFO:__main__:Eseguendo statement 3/5...
...
INFO:__main__:✅ Migrazione 006 completata con successo!
```

---

## ⚠️ Note Importanti

1. **Backup**: Prima di eseguire la migrazione su produzione, fai un backup del database:
   ```bash
   pg_dump $DATABASE_URL > backup_pre_migration_006.sql
   ```

2. **Downtime**: La migrazione è veloce (< 1 secondo) ma blocca brevemente la tabella `users`. Esegui durante una finestra di manutenzione se possibile.

3. **Rollback**: Se necessario, puoi rollbackare la migrazione con:
   ```sql
   -- Rimuovi indice unique parziale
   DROP INDEX IF EXISTS uq_users_telegram_id;
   DROP INDEX IF EXISTS idx_users_telegram;
   
   -- Ripristina unique constraint
   ALTER TABLE users ADD CONSTRAINT users_telegram_id_key UNIQUE (telegram_id);
   
   -- Ripristina NOT NULL
   ALTER TABLE users ALTER COLUMN telegram_id SET NOT NULL;
   ```

4. **Compatibilità**: La migrazione è retrocompatibile:
   - Utenti esistenti con `telegram_id` continuano a funzionare normalmente
   - Il nuovo codice supporta sia utenti con che senza `telegram_id`

---

## ✅ Checklist Post-Migrazione

- [ ] Migrazione eseguita senza errori
- [ ] Verificato che `telegram_id` sia nullable
- [ ] Verificato che l'indice unique parziale esista
- [ ] Testato creazione utente senza `telegram_id` (opzionale)
- [ ] Verificato che il processor funzioni correttamente dopo la migrazione

---

## 🆘 Troubleshooting

### Errore: "constraint does not exist"
**Causa**: Il constraint unique potrebbe avere un nome diverso.

**Soluzione**: Verifica il nome del constraint:
```sql
SELECT conname FROM pg_constraint 
WHERE conrelid = 'users'::regclass 
AND contype = 'u';
```

Poi modifica il file SQL con il nome corretto.

### Errore: "index already exists"
**Causa**: L'indice potrebbe essere già stato creato.

**Soluzione**: Non è un problema, gli statement usano `IF NOT EXISTS`. Puoi ignorare il warning.

### Errore: "permission denied"
**Causa**: L'utente database non ha i permessi necessari.

**Soluzione**: Esegui come superuser o con un utente con privilegi `ALTER TABLE`:
```bash
psql $DATABASE_URL -U postgres -f migrations/006_make_telegram_id_nullable.sql
```
