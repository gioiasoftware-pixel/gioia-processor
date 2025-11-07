FROM python:3.12-slim

# Install system dependencies required by the app (psycopg2, pdf2image, pytesseract)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN python -m pip install --upgrade pip --no-cache-dir \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

CMD ["python", "start_processor.py"]
