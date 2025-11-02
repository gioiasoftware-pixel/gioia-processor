-- Migrazione: Crea tabella rate_limit_logs per rate limiting
-- Esegui con: psql $DATABASE_URL -f migrations/002_rate_limit.sql

CREATE TABLE IF NOT EXISTS rate_limit_logs (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indice per lookup veloce e cleanup
CREATE INDEX IF NOT EXISTS idx_rate_limit_key_time 
  ON rate_limit_logs (key, created_at DESC);

-- Indice per cleanup vecchie entries
CREATE INDEX IF NOT EXISTS idx_rate_limit_cleanup
  ON rate_limit_logs (created_at);

-- Commento sulla tabella
COMMENT ON TABLE rate_limit_logs IS 'Rate limit logs per utente/azione (sliding window)';


