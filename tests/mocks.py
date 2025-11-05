"""
Mock utilities per test Phase 9.
Comprehensive mocks per OpenAI, OCR, Database, e Timeout.
"""
import json
from unittest.mock import AsyncMock, MagicMock, Mock
from typing import Dict, Any, Optional, List
import asyncio


# ============================================================================
# OpenAI Mocks
# ============================================================================

class MockOpenAIClient:
    """Mock client OpenAI completo per test."""
    
    def __init__(self):
        self.chat = Mock()
        self.chat.completions = Mock()
        self._response_mode = "success"  # success, error, timeout, rate_limit, malformed
        self._response_data = None
    
    def set_response_mode(self, mode: str, data: Optional[Dict[str, Any]] = None):
        """
        Imposta modalità risposta mock.
        
        Modes:
        - "success": Risposta JSON corretta
        - "malformed": Risposta JSON malformata
        - "error": Errore API
        - "timeout": Timeout asyncio
        - "rate_limit": Rate limit error
        """
        self._response_mode = mode
        self._response_data = data
        
        # Configura chat.completions.create per usare il mock
        if mode == "success":
            response_data = data or {
                "wines": [
                    {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12}
                ]
            }
            self.chat.completions.create = Mock(return_value=MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content=json.dumps(response_data))
                )]
            ))
        elif mode == "malformed":
            self.chat.completions.create = Mock(return_value=MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content="This is not valid JSON {")
                )]
            ))
        elif mode == "error":
            self.chat.completions.create = Mock(side_effect=Exception("OpenAI API Error"))
        elif mode == "timeout":
            self.chat.completions.create = Mock(side_effect=asyncio.TimeoutError("Request timeout"))
        elif mode == "rate_limit":
            error = Exception("Rate limit exceeded")
            error.__class__.__name__ = "RateLimitError"
            self.chat.completions.create = Mock(side_effect=error)
    
    def create(self, **kwargs):
        """Crea completion mock."""
        if self._response_mode == "success":
            response_data = self._response_data or {
                "wines": [
                    {"name": "Chianti", "winery": "Barone", "vintage": 2020, "qty": 12}
                ]
            }
            return MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content=json.dumps(response_data))
                )]
            )
        elif self._response_mode == "malformed":
            return MagicMock(
                choices=[MagicMock(
                    message=MagicMock(content="This is not valid JSON {")
                )]
            )
        elif self._response_mode == "error":
            raise Exception("OpenAI API Error")
        elif self._response_mode == "timeout":
            raise asyncio.TimeoutError("Request timeout")
        elif self._response_mode == "rate_limit":
            # RateLimitError senza import diretto (evita warning linter)
            error = Exception("Rate limit exceeded")
            error.__class__.__name__ = "RateLimitError"
            raise error
        else:
            raise Exception(f"Unknown response mode: {self._response_mode}")


def create_mock_openai_client(response_mode: str = "success", response_data: Optional[Dict] = None):
    """
    Crea mock client OpenAI per test.
    
    Args:
        response_mode: "success", "malformed", "error", "timeout", "rate_limit"
        response_data: Dati da ritornare in caso di success
    """
    mock_client = MockOpenAIClient()
    mock_client.set_response_mode(response_mode, response_data)
    return mock_client


# ============================================================================
# OCR Mocks
# ============================================================================

class MockOCR:
    """Mock per pytesseract e pdf2image."""
    
    def __init__(self):
        self._text_mode = "success"  # success, error, empty
        self._text_data = "Chianti Classico 2020 12 bottiglie 18.50 euro"
        self._pdf_pages = 1
    
    def set_text_mode(self, mode: str, text: Optional[str] = None, pages: int = 1):
        """
        Imposta modalità OCR.
        
        Modes:
        - "success": Testo estratto correttamente
        - "error": Errore OCR
        - "empty": Testo vuoto
        """
        self._text_mode = mode
        if text:
            self._text_data = text
        self._pdf_pages = pages
    
    def image_to_string(self, image, **kwargs):
        """Mock pytesseract.image_to_string."""
        if self._text_mode == "success":
            return self._text_data
        elif self._text_mode == "error":
            raise Exception("OCR Error: Tesseract not found")
        elif self._text_mode == "empty":
            return ""
        else:
            return ""
    
    def convert_from_path(self, pdf_path, **kwargs):
        """Mock pdf2image.convert_from_path."""
        if self._text_mode == "success":
            # Ritorna lista di immagini mock
            images = []
            for i in range(self._pdf_pages):
                img = MagicMock()
                img.size = (100, 100)
                images.append(img)
            return images
        elif self._text_mode == "error":
            raise Exception("PDF conversion error")
        else:
            return []


def create_mock_ocr(text_mode: str = "success", text: Optional[str] = None, pages: int = 1):
    """Crea mock OCR per test."""
    mock_ocr = MockOCR()
    mock_ocr.set_text_mode(text_mode, text, pages)
    return mock_ocr


# ============================================================================
# Database Mocks
# ============================================================================

class MockDatabase:
    """Mock database per test."""
    
    def __init__(self):
        self._insert_mode = "success"  # success, partial_error, error
        self._batch_size = 500
        self._data = []
    
    def set_insert_mode(self, mode: str):
        """
        Imposta modalità insert.
        
        Modes:
        - "success": Insert completo
        - "partial_error": Errore parziale (alcune righe falliscono)
        - "error": Errore completo
        """
        self._insert_mode = mode
    
    async def execute(self, query, *args, **kwargs):
        """Mock execute."""
        if self._insert_mode == "success":
            return MagicMock(scalar_one_or_none=lambda: None, scalar_one=lambda: MagicMock())
        elif self._insert_mode == "partial_error":
            # Simula errore parziale
            raise Exception("Partial insert error: Some rows failed")
        elif self._insert_mode == "error":
            raise Exception("Database error")
        return MagicMock()
    
    async def commit(self):
        """Mock commit."""
        pass
    
    async def rollback(self):
        """Mock rollback."""
        pass
    
    def add(self, obj):
        """Mock add."""
        self._data.append(obj)
    
    def __aiter__(self):
        """Mock async iterator."""
        return self
    
    async def __anext__(self):
        """Mock async next."""
        if not hasattr(self, '_iterated'):
            self._iterated = True
            return self
        raise StopAsyncIteration


def create_mock_db(insert_mode: str = "success"):
    """Crea mock database per test."""
    mock_db = MockDatabase()
    mock_db.set_insert_mode(insert_mode)
    return mock_db


# ============================================================================
# Timeout Mocks
# ============================================================================

class MockTimeout:
    """Mock per timeout asyncio."""
    
    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self._timeout_mode = "success"  # success, timeout
    
    def set_timeout_mode(self, mode: str, delay: float = 0.1):
        """Imposta modalità timeout."""
        self._timeout_mode = mode
        self.delay = delay
    
    async def call_with_timeout(self, coro, timeout: float = 5.0):
        """Simula chiamata con timeout."""
        if self._timeout_mode == "timeout":
            await asyncio.sleep(timeout + 0.1)  # Simula timeout
            raise asyncio.TimeoutError("Operation timeout")
        else:
            await asyncio.sleep(self.delay)
            return await coro


# ============================================================================
# Feature Flags Mock
# ============================================================================

def create_mock_config_with_flags(
    ia_targeted_enabled: bool = True,
    llm_fallback_enabled: bool = True,
    ocr_enabled: bool = True,
    **kwargs
):
    """Crea mock config con feature flags specifici."""
    config = MagicMock()
    config.ia_targeted_enabled = ia_targeted_enabled
    config.llm_fallback_enabled = llm_fallback_enabled
    config.ocr_enabled = ocr_enabled
    config.schema_score_th = kwargs.get("schema_score_th", 0.7)
    config.min_valid_rows = kwargs.get("min_valid_rows", 0.6)
    config.header_confidence_th = kwargs.get("header_confidence_th", 0.75)
    config.batch_size_ambiguous_rows = kwargs.get("batch_size_ambiguous_rows", 20)
    config.max_llm_tokens = kwargs.get("max_llm_tokens", 300)
    config.llm_model_targeted = kwargs.get("llm_model_targeted", "gpt-4o-mini")
    config.llm_model_extract = kwargs.get("llm_model_extract", "gpt-4o")
    config.ocr_extensions = kwargs.get("ocr_extensions", "pdf,jpg,jpeg,png")
    config.db_insert_batch_size = kwargs.get("db_insert_batch_size", 500)
    return config

