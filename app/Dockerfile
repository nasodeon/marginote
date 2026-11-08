FROM python:3.12-slim

# OMP_THREAD_LIMIT=1: Tesseract is fastest on one thread for a single page and leaves other cores free.
# MALLOC_ARENA_MAX=2 and MALLOC_MMAP_THRESHOLD_: memory used to read a page is handed back afterwards
# (measured: back to ~100 MB after each page instead of staying above 200 MB).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    OMP_THREAD_LIMIT=1 \
    MALLOC_ARENA_MAX=2 \
    MALLOC_MMAP_THRESHOLD_=131072

# Tesseract with the French and English language packs; tzdata so TZ sets the backup hour correctly
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY marginote ./marginote
RUN python -m compileall -q marginote

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Listens only inside the Tailscale container's network: not reachable from your LAN or the internet.
# No access log: request lines would otherwise record your searches, book ids and shared passages in the Docker logs.
# A passage shared from Android arrives in the address itself: allowed up to 1 MB (the default, 16 KB, cut long ones off).
CMD ["uvicorn", "--factory", "marginote.main:create_app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1", "--h11-max-incomplete-event-size", "1048576"]
