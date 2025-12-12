"""
Script per pulire CSV inventario secondo le regole della guida.
Corregge formati comuni prima dell'inserimento.
"""
import csv
import re
import sys
from pathlib import Path


def clean_annata(value: str) -> str:
    """Pulisce colonna Annata: --- o vuoto -> vuoto, estrae anno da date"""
    if not value or value.strip() == "" or value.strip().upper() == "---" or value.strip() == "N/A":
        return ""
    
    value = value.strip()
    
    # Estrai anno da date (es: "15/01/2018" -> "2018")
    date_match = re.search(r'(\d{4})', value)
    if date_match:
        year = int(date_match.group(1))
        if 1900 <= year <= 2099:
            return str(year)
    
    # Se è già un anno valido
    if value.isdigit():
        year = int(value)
        if 1900 <= year <= 2099:
            return str(year)
        # Se è 2 cifre, prova a convertire (es: "18" -> "2018")
        if len(value) == 2:
            year = 2000 + int(value)
            if 1900 <= year <= 2099:
                return str(year)
    
    return ""


def clean_quantita(value: str) -> str:
    """Pulisce colonna Quantità: converte a intero >= 0"""
    if not value or value.strip() == "" or value.strip().upper() == "---" or value.strip() == "N/A":
        return "0"
    
    value = value.strip()
    
    # Rimuovi testo e estrai numero
    number_match = re.search(r'(\d+)', value)
    if number_match:
        return number_match.group(1)
    
    return "0"


def clean_prezzo(value: str) -> str:
    """Pulisce colonna Prezzo: converte virgola a punto, rimuovi simboli"""
    if not value or value.strip() == "" or value.strip().upper() == "---" or value.strip() == "N/A":
        return ""
    
    value = value.strip()
    
    # Rimuovi virgolette
    value = value.strip('"\'')
    
    # Rimuovi simboli valuta
    value = re.sub(r'[€$EUR]', '', value, flags=re.IGNORECASE)
    value = value.strip()
    
    # Gestisci separatori: virgola decimale -> punto
    # Es: "9,95" -> "9.95", "1.234,56" -> "1234.56"
    if ',' in value and '.' in value:
        # Se ci sono entrambi, la virgola è decimale se viene dopo il punto
        if value.rindex(',') > value.rindex('.'):
            # Virgola è decimale: "1.234,56" -> "1234.56"
            value = value.replace('.', '').replace(',', '.')
        else:
            # Punto è decimale: "1,234.56" -> "1234.56"
            value = value.replace(',', '')
    elif ',' in value:
        # Solo virgola: potrebbe essere decimale o migliaia
        # Se ci sono più di 3 cifre dopo la virgola, è migliaia
        parts = value.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Decimale: "9,95" -> "9.95"
            value = value.replace(',', '.')
        else:
            # Migliaia: "1,234" -> "1234"
            value = value.replace(',', '')
    
    # Verifica che sia un numero valido
    try:
        float_val = float(value)
        if float_val < 0:
            return ""
        return str(float_val)
    except ValueError:
        return ""


def clean_csv(input_file: str, output_file: str):
    """Pulisce CSV secondo le regole della guida"""
    with open(input_file, 'r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        
        # Verifica header
        if 'Nome' not in reader.fieldnames:
            raise ValueError("Header 'Nome' non trovato nel CSV")
        
        # Prepara output
        fieldnames = reader.fieldnames
        rows_cleaned = []
        
        for row_num, row in enumerate(reader, start=2):  # Start=2 perché header è riga 1
            # Pulisci Annata
            if 'Annata' in row:
                row['Annata'] = clean_annata(row.get('Annata', ''))
            
            # Pulisci Quantità
            if 'Quantità' in row:
                row['Quantità'] = clean_quantita(row.get('Quantità', ''))
            
            # Pulisci Prezzo
            if 'Prezzo' in row:
                row['Prezzo'] = clean_prezzo(row.get('Prezzo', ''))
            
            # Pulisci Costo
            if 'Costo' in row:
                row['Costo'] = clean_prezzo(row.get('Costo', ''))
            
            # Salta righe senza nome
            if not row.get('Nome', '').strip():
                print(f"WARNING: Riga {row_num}: Nome vuoto, saltata")
                continue
            
            rows_cleaned.append(row)
        
        # Scrivi CSV pulito
        with open(output_file, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_cleaned)
        
        print(f"OK: CSV pulito salvato: {output_file}")
        print(f"Righe processate: {len(rows_cleaned)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python clean_csv_for_insert.py <file_input.csv> [file_output.csv]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.csv', '_PULITO.csv')
    
    if not Path(input_file).exists():
        print(f"❌ File non trovato: {input_file}")
        sys.exit(1)
    
    try:
        clean_csv(input_file, output_file)
        print(f"\nOK: Pulizia completata!")
        print(f"File pulito: {output_file}")
    except Exception as e:
        print(f"ERRORE: Errore durante la pulizia: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

