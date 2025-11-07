"""
Excel Parser per Stage 1.

Parsing Excel senza IA (selezione sheet, parsing pandas).
"""
import pandas as pd
import io
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)


def parse_excel(file_content: bytes) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Parse file Excel con pandas.
    
    Conforme a "Update processor.md" - Stage 1: Parser Excel.
    Sceglie sheet con più righe non vuote.
    
    Args:
        file_content: Contenuto file (bytes)
    
    Returns:
        Tuple (DataFrame, sheet_info):
        - DataFrame: Dati Excel parsati
        - sheet_info: Dict con sheet_name, sheet_index, rows, columns
    """
    try:
        # Leggi tutti i sheet
        excel_file = pd.ExcelFile(io.BytesIO(file_content))
        sheet_names = excel_file.sheet_names
        
        logger.info(f"[EXCEL_PARSER] Excel file has {len(sheet_names)} sheets: {sheet_names}")
        
        # Trova sheet con più righe non vuote
        best_sheet = None
        best_sheet_name = None
        max_rows = 0
        
        for sheet_idx, sheet_name in enumerate(sheet_names):
            try:
                df_test = pd.read_excel(excel_file, sheet_name=sheet_name)
                # Conta righe non vuote (almeno una colonna non vuota)
                non_empty_rows = df_test.dropna(how='all').shape[0]
                
                if non_empty_rows > max_rows:
                    max_rows = non_empty_rows
                    best_sheet = sheet_idx
                    best_sheet_name = sheet_name
                    logger.debug(
                        f"[EXCEL_PARSER] Sheet '{sheet_name}' has {non_empty_rows} non-empty rows"
                    )
            except Exception as e:
                logger.warning(f"[EXCEL_PARSER] Error reading sheet '{sheet_name}': {e}")
                continue
        
        if best_sheet is None:
            raise ValueError("Nessun sheet valido trovato nel file Excel")
        
        # Leggi sheet migliore
        df = pd.read_excel(
            excel_file,
            sheet_name=best_sheet_name,
            dtype=str  # Leggi tutto come string per normalizzazione successiva
        )
        
        logger.info(
            f"[EXCEL_PARSER] Excel parsed: sheet='{best_sheet_name}', "
            f"{len(df)} rows, {len(df.columns)} columns"
        )
        
        sheet_info = {
            'sheet_name': best_sheet_name,
            'sheet_index': best_sheet,
            'total_sheets': len(sheet_names),
            'rows': len(df),
            'columns': len(df.columns),
            'non_empty_rows': max_rows
        }
        
        return df, sheet_info
        
    except Exception as e:
        logger.error(f"[EXCEL_PARSER] Error parsing Excel: {e}")
        raise ValueError(f"Errore parsing Excel: {str(e)}")





