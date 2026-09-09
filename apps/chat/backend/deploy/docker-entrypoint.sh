#!/bin/sh
set -e
cd /app
python manage.py migrate --noinput
exec "$@"
