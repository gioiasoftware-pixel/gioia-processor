"""
CSV Parser per Stage 1.

Parsing CSV senza IA (encoding detection, delimiter sniff, parsing pandas).
"""
import pandas as pd
import io
import csv
import logging
import chardet
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)


def detect_encoding(file_content: bytes) -> Tuple[str, float]:
    """
    Rileva encoding file provando: utf-8-sig → utf-8 → latin-1.
    
    Conforme a "Update processor.md" - Stage 1: Encoding detection.
    
    Args:
        file_content: Contenuto file (bytes)
    
    Returns:
        Tuple (encoding, confidence)
    """
    # Prova charset-normalizer (chardet)
    encoding_result = chardet.detect(file_content[:10000])  # Prime 10KB
    detected_encoding = encoding_result.get('encoding', 'utf-8')
    confidence = encoding_result.get('confidence', 0.0)
    
    # Prova encoding in ordine: utf-8-sig → utf-8 → latin-1
    for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
        try:
            file_content.decode(enc)
            logger.debug(f"[CSV_PARSER] Encoding detection: {enc} (confidence={confidence:.2f})")
            return enc, confidence
        except (UnicodeDecodeError, LookupError):
            continue
    
    # Fallback: utf-8 con errors='ignore'
    logger.warning(f"[CSV_PARSER] Encoding detection failed, using utf-8 with errors='ignore'")
    return 'utf-8', 0.0


def detect_delimiter(file_content: bytes, encoding: str, sample_lines: int = 10) -> str:
    """
    Rileva separatore CSV usando csv.Sniffer + fallback.
    
    Conforme a "Update processor.md" - Stage 1: Delimiter sniff.
    
    Args:
        file_content: Contenuto file (bytes)
        encoding: Encoding file
        sample_lines: Numero righe da analizzare
    
    Returns:
        Separatore CSV (',', ';', '\t', '|')
    """
    try:
        # Decodifica prime righe
        text = file_content.decode(encoding, errors='ignore')
        lines = text.split('\n')[:sample_lines]
        non_empty_lines = [l for l in lines if l.strip()]
        
        if not non_empty_lines:
            return ','
        
        # Prova csv.Sniffer
        try:
            sniffer = csv.Sniffer()
            sample = '\n'.join(non_empty_lines[:3])  # Prime 3 righe per sniff
            delimiter = sniffer.sniff(sample).delimiter
            logger.debug(f"[CSV_PARSER] CSV Sniffer detected delimiter: '{delimiter}'")
            return delimiter
        except (csv.Error, Exception):
            pass
        
        # Fallback: analizza separatori comuni
        separators = [',', ';', '\t', '|']
        separator_scores = {}
        
        for sep in separators:
            score = 0
            consistent = True
            
            for line in non_empty_lines:
                parts = line.split(sep)
                if len(parts) >= 2:  # Almeno 2 colonne
                    score += len(parts)
                else:
                    consistent = False
            
            # Bonus se consistente (stesso numero colonne per tutte le righe)
            if consistent:
                column_counts = [len(line.split(sep)) for line in non_empty_lines]
                if len(set(column_counts)) == 1:  # Tutte le righe hanno stesso numero colonne
                    score *= 2
            
            separator_scores[sep] = score
        
        # Trova separatore con score più alto
        best_sep = max(separator_scores.items(), key=lambda x: x[1])[0] if separator_scores else ','
        logger.debug(f"[CSV_PARSER] Fallback delimiter detection: '{best_sep}'")
        return best_sep
        
    except Exception as e:
        logger.warning(f"[CSV_PARSER] Error detecting delimiter: {e}, using ','")
        return ','


def parse_csv(
    file_content: bytes,
    separator: Optional[str] = None,
    encoding: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Parse file CSV con pandas.
    
    Conforme a "Update processor.md" - Stage 1: Parser CSV.
    
    Args:
        file_content: Contenuto file (bytes)
        separator: Separatore CSV (se None, auto-rileva)
        encoding: Encoding file (se None, auto-rileva)
    
    Returns:
        Tuple (DataFrame, detection_info):
        - DataFrame: Dati CSV parsati
        - detection_info: Dict con encoding, separator, confidence
    """
    # Rileva encoding se non fornito
    if encoding is None:
        encoding, enc_confidence = detect_encoding(file_content)
    else:
        enc_confidence = 1.0
    
    # Rileva separator se non fornito
    if separator is None:
        separator = detect_delimiter(file_content, encoding)
    
    # Parse con pandas
    try:
        df = pd.read_csv(
            io.BytesIO(file_content),
            sep=separator,
            encoding=encoding,
            on_bad_lines='skip',
            engine='python',
            skipinitialspace=True,
            dtype=str  # Leggi tutto come string per normalizzazione successiva
        )
        
        logger.info(
            f"[CSV_PARSER] CSV parsed: {len(df)} rows, {len(df.columns)} columns, "
            f"encoding={encoding}, separator='{separator}'"
        )
        
        detection_info = {
            'encoding': encoding,
            'encoding_confidence': enc_confidence,
            'separator': separator,
            'rows': len(df),
            'columns': len(df.columns),
            'method': 'auto-detected' if separator is None else 'provided'
        }
        
        return df, detection_info
        
    except Exception as e:
        logger.error(f"[CSV_PARSER] Error parsing CSV: {e}")
        raise ValueError(f"Errore parsing CSV: {str(e)}")

