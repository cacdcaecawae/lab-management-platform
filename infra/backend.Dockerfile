# Build context: repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
RUN useradd --create-home --uid 1000 app && mkdir -p /app/var/static /data && chown -R app /app/var /data
USER app

EXPOSE 8000
# Single-instance deployment: apply migrations and collect static files on start.
CMD ["sh", "-c", "mkdir -p \"${FILE_UPLOAD_TEMP_DIR:-/data/tmp}\" && { [ -n \"${LAB_NAS_STORAGE_ID:-}\" ] || mkdir -p /data/files; } && python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 3 --threads 8 --timeout 120 --access-logfile -"]
