#!/bin/sh
set -eu
chown crm:crm /app/media /app/backups
run_as_crm() {
  setpriv --reuid=crm --regid=crm --init-groups -- "$@"
}
if [ "$#" -gt 0 ]; then
  exec setpriv --reuid=crm --regid=crm --init-groups -- "$@"
fi
attempt=1
until run_as_crm python manage.py migrate --noinput; do
  if [ "$attempt" -ge 30 ]; then
    echo "Databaseverbinding niet beschikbaar na 30 pogingen." >&2
    exit 1
  fi
  echo "Database nog niet bereikbaar; nieuwe poging over 2 seconden ($attempt/30)." >&2
  attempt=$((attempt + 1))
  sleep 2
done
run_as_crm python manage.py collectstatic --noinput
run_as_crm python manage.py bootstrap
exec setpriv --reuid=crm --regid=crm --init-groups -- gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
