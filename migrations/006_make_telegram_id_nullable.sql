-- Migrazione: Rende telegram_id nullable in users per supportare utenti senza telegram
-- Esegui con: psql $DATABASE_URL -f migrations/006_make_telegram_id_nullable.sql

-- Rimuove NOT NULL constraint da telegram_id
ALTER TABLE users 
  ALTER COLUMN telegram_id DROP NOT NULL;

-- Rimuove unique constraint esistente (se esiste come constraint)
-- Nota: PostgreSQL crea un indice automatico per unique constraint
-- Dobbiamo droppare sia il constraint che l'indice se esiste
DO $$
BEGIN
    -- Prova a droppare il constraint unique se esiste
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'users_telegram_id_key'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT users_telegram_id_key;
    END IF;
    
    -- Prova a droppare l'indice unique se esiste (potrebbe essere chiamato diversamente)
    IF EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'users' 
        AND indexname LIKE '%telegram_id%unique%'
    ) THEN
        DROP INDEX IF EXISTS users_telegram_id_key;
    END IF;
END $$;

-- Crea unique index parziale: solo quando telegram_id IS NOT NULL
-- Questo permette più utenti con telegram_id NULL, ma mantiene unique per valori non-null
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id 
  ON users (telegram_id)
  WHERE telegram_id IS NOT NULL;

-- Verifica che l'indice normale esista ancora (per performance)
CREATE INDEX IF NOT EXISTS idx_users_telegram 
  ON users (telegram_id)
  WHERE telegram_id IS NOT NULL;
