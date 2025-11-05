"""
Configurazione per gioia-processor usando pydantic-settings.

Gestisce tutte le variabili d'ambiente e feature flags per la pipeline.
"""
import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Carica .env
load_dotenv()


class ProcessorConfig(BaseSettings):
    """Configurazione completa del processor."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Database
    database_url: str = Field(..., description="URL connessione PostgreSQL")
    
    # Server
    port: int = Field(default=8001, description="Porta server FastAPI")
    
    # OpenAI
    openai_api_key: str = Field(default="", description="API key OpenAI")
    openai_model: str = Field(default="gpt-4o-mini", description="Modello OpenAI default")
    
    # Feature flags
    ia_targeted_enabled: bool = Field(default=True, description="Abilita Stage 2 (IA mirata)")
    llm_fallback_enabled: bool = Field(default=True, description="Abilita Stage 3 (LLM mode)")
    ocr_enabled: bool = Field(default=True, description="Abilita Stage 4 (OCR)")
    
    # Tentativi / soglie
    csv_max_attempts: int = Field(default=3, description="Max tentativi parsing CSV")
    schema_score_th: float = Field(default=0.7, ge=0.0, le=1.0, description="Soglia schema_score per Stage 1")
    min_valid_rows: float = Field(default=0.6, ge=0.0, le=1.0, description="Soglia valid_rows per Stage 1")
    header_confidence_th: float = Field(default=0.75, ge=0.0, le=1.0, description="Confidence threshold per header mapping")
    
    # IA mirata (Stage 2)
    batch_size_ambiguous_rows: int = Field(default=20, ge=1, le=100, description="Batch size per righe ambigue")
    max_llm_tokens: int = Field(default=300, ge=1, le=4000, description="Max token per chiamate IA mirata")
    llm_model_targeted: str = Field(default="gpt-4o-mini", description="Modello LLM per Stage 2 (economico)")
    
    # LLM mode (Stage 3)
    llm_model_extract: str = Field(default="gpt-4o", description="Modello LLM per Stage 3 (robusto)")
    
    # OCR (Stage 4)
    ocr_extensions: str = Field(default="pdf,jpg,jpeg,png", description="Estensioni supportate per OCR")
    
    # Batch DB
    db_insert_batch_size: int = Field(default=500, ge=1, le=10000, description="Batch size per insert DB")
    
    # Processor info
    processor_name: str = Field(default="Gioia Processor", description="Nome processor")
    processor_version: str = Field(default="1.0.0", description="Versione processor")
    
    def get_ocr_extensions_list(self) -> List[str]:
        """Ritorna lista estensioni OCR."""
        return [ext.strip().lower() for ext in self.ocr_extensions.split(",")]
    
    def validate_config(self) -> bool:
        """Valida configurazione critica."""
        errors = []
        
        if not self.database_url:
            errors.append("DATABASE_URL non configurato")
        
        if not self.openai_api_key:
            # Warning, non errore (AI features disabilitate)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("OPENAI_API_KEY non configurato - AI features disabilitate")
        
        if errors:
            error_msg = "❌ Configurazione processor mancante:\n" + "\n".join(f"  - {error}" for error in errors)
            import logging
            logger = logging.getLogger(__name__)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info("✅ Configurazione processor validata con successo")
        return True


# Istanza globale configurazione
_config: ProcessorConfig | None = None


def get_config() -> ProcessorConfig:
    """Ottiene istanza configurazione (singleton)."""
    global _config
    if _config is None:
        _config = ProcessorConfig()
        _config.validate_config()
    return _config


def validate_config() -> bool:
    """Valida configurazione critica (funzione standalone per compatibilità)."""
    config = get_config()
    return config.validate_config()


# Backward compatibility: esporta variabili per codice esistente
def get_legacy_config():
    """Ritorna dict con variabili per backward compatibility."""
    config = get_config()
    return {
        "DATABASE_URL": config.database_url,
        "PORT": config.port,
        "OPENAI_API_KEY": config.openai_api_key,
        "OPENAI_MODEL": config.openai_model,
        "PROCESSOR_NAME": config.processor_name,
        "PROCESSOR_VERSION": config.processor_version,
    }

