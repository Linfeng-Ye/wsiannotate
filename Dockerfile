FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --disabled-password --gecos '' appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build static assets with a throwaway secret key; the real key and
# DATABASE_URL are injected at runtime. collectstatic does not touch the DB.
RUN DJANGO_SECRET_KEY=build-time-dummy DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

RUN chown -R appuser /app
USER appuser

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
