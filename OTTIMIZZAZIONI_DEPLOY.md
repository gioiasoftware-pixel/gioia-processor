# ⚡ Ottimizzazioni Deploy Processor

## Analisi Attuale

### Tempi Deploy
- **Build**: ~1-2 minuti (Nixpacks)
- **Push immagine**: ~3-5 minuti (1 GB)
- **Totale**: ~4-7 minuti

### Dipendenze Pesanti
1. **pandas** (~200 MB) - Necessario per CSV/Excel parsing
2. **numpy** (~150 MB) - Necessario per pandas
3. **scipy** (~100 MB) - Usato solo per `linear_sum_assignment`
4. **tesseract** (~50 MB) - Necessario per OCR
5. **poppler** (~30 MB) - Necessario per PDF
6. **postgresql_16.dev** (~100 MB) - Client database

## 🚀 Ottimizzazioni Possibili

### 1. Sostituire scipy con algoritmo custom (ALTA PRIORITÀ)
**Risparmio**: ~100 MB + tempo compilazione scipy

`scipy.optimize.linear_sum_assignment` è usato solo per matching header. Possiamo sostituirlo con algoritmo greedy più semplice.

**Impatto**: Riduce dimensione immagine di ~100 MB e tempo build di ~30-60 secondi.

### 2. Usare versioni specifiche invece di >=
**Risparmio**: Cache migliore, build più veloce

Railway può cacheare meglio le dipendenze se usiamo versioni specifiche.

### 3. Rimuovere postgresql_16.dev se non necessario
**Risparmio**: ~100 MB

Verificare se è realmente necessario o se possiamo usare solo psycopg2-binary.

### 4. Usare build cache di Railway
Railway supporta cache tra build se usiamo versioni specifiche.

### 5. Pre-installare dipendenze comuni
Railway può cacheare layer base con dipendenze comuni.

## 📊 Stima Risparmio

| Ottimizzazione | Risparmio Tempo | Risparmio Spazio |
|----------------|-----------------|------------------|
| Rimuovere scipy | ~30-60s | ~100 MB |
| Versioni specifiche | ~10-20s | - |
| Rimuovere postgresql_16.dev | ~20-30s | ~100 MB |
| **TOTALE** | **~60-110s** | **~200 MB** |

**Tempo deploy stimato dopo ottimizzazioni**: ~3-5 minuti (invece di 4-7)

