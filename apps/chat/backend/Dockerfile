FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

COPY backend/ .

EXPOSE 80

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn backend_app.asgi:application --host 0.0.0.0 --port ${PORT:-80}"]
