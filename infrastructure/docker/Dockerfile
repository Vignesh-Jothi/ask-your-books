# Ask Your Books — multi-tenant receivables & expenses intelligence
#
# Dev/test image. For production, mount config/ + a provisioned SQLite volume
# (or swap DATABASE_URL for the Postgres schema in infrastructure/postgres/).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build the deterministic demo database at image build time so containers
# start with data matching the documented numbers.
RUN python seed.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]