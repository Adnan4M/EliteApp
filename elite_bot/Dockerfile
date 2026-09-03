FROM python:3.11-slim

# Tesseract OCR + Arabic language data
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY . .

# Railway injects PORT env var
CMD python migrate_verify.py && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
