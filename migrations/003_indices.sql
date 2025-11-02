-- Migrazione: Indici aggiuntivi per performance
-- Esegui con: psql $DATABASE_URL -f migrations/003_indices.sql

-- Verifica che indice su users.telegram_id esista (creato da SQLAlchemy ma verifichiamo)
CREATE INDEX IF NOT EXISTS idx_users_telegram 
  ON users (telegram_id);

-- Indici su processing_jobs (già creati in 001 ma verifichiamo)
CREATE INDEX IF NOT EXISTS idx_jobs_user_status_created
  ON processing_jobs (telegram_id, status, created_at DESC);


