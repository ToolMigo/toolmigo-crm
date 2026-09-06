#!/bin/sh
set -eu
attempt=1
until python manage.py migrate --noinput; do
  if [ "$attempt" -ge 30 ]; then
    echo "Databaseverbinding niet beschikbaar na 30 pogingen." >&2
    exit 1
  fi
  echo "Database nog niet bereikbaar; nieuwe poging over 2 seconden ($attempt/30)." >&2
  attempt=$((attempt + 1))
  sleep 2
done
python manage.py collectstatic --noinput
python manage.py bootstrap
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
