-- Migrazione: Aggiungi client_msg_id e update_id a processing_jobs per idempotenza
-- Esegui con: psql $DATABASE_URL -f migrations/001_add_client_msg_id.sql

-- Aggiungi colonne per idempotenza
ALTER TABLE processing_jobs
  ADD COLUMN IF NOT EXISTS client_msg_id TEXT,
  ADD COLUMN IF NOT EXISTS update_id INTEGER;

-- Indice per lookup veloce
CREATE INDEX IF NOT EXISTS idx_jobs_user_client 
  ON processing_jobs (telegram_id, client_msg_id)
  WHERE client_msg_id IS NOT NULL;

-- Vincolo UNIQUE parziale per idempotenza (solo se client_msg_id IS NOT NULL)
-- NOTA: PostgreSQL non supporta UNIQUE constraint parziale direttamente,
-- quindi usiamo UNIQUE index parziale
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_user_client 
  ON processing_jobs (telegram_id, client_msg_id)
  WHERE client_msg_id IS NOT NULL;

-- Indici aggiuntivi per performance
CREATE INDEX IF NOT EXISTS idx_jobs_user_status_created
  ON processing_jobs (telegram_id, status, created_at DESC);

