FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies (compile wheels, then remove build tools)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && python -m pip install --upgrade pip --no-cache-dir \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY . .

CMD ["python", "start_processor.py"]
