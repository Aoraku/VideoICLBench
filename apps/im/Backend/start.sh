#!/bin/sh
set -eu
python3 manage.py migrate --noinput
exec uvicorn Backend.asgi:application --host 0.0.0.0 --port "${PORT:-80}"
