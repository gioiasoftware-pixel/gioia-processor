FROM python:3.12-slim AS builder

WORKDIR /build

# Dipendenze di sistema necessarie per compilare le wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN python -m pip install --upgrade pip --no-cache-dir \
    && python -m pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


FROM python:3.12-slim

# Install runtime dependencies (senza tool di build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Installa le wheel precompilate
COPY --from=builder /build/wheels /wheels
RUN python -m pip install --upgrade pip --no-cache-dir \
    && python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copia il sorgente dell'applicazione
COPY . .

CMD ["python", "start_processor.py"]
