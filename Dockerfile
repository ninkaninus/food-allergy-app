FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# tesseract-ocr-dan er den danske sprogmodel. Uden den læser OCR'en
# danske deklarationer som forvrænget engelsk.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-dan tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY app /app/app
COPY data /app/data
COPY NOTICE.md LICENSE CHANGELOG.md /app/

ENV DATA_DIR=/data RULES_PATH=/app/data/allergens.yaml PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
