#!/bin/sh
set -eu
mkdir -p /app/media /app/backups
drop_privileges=0
if chown crm:crm /app/staticfiles /app/media /app/backups 2>/dev/null && setpriv --reuid=crm --regid=crm --init-groups -- true 2>/dev/null; then
  drop_privileges=1
fi
run_as_crm() {
  if [ "$drop_privileges" -eq 1 ]; then
    setpriv --reuid=crm --regid=crm --init-groups -- "$@"
  else
    "$@"
  fi
}
if [ "$#" -gt 0 ]; then
  if [ "$drop_privileges" -eq 1 ]; then
    exec setpriv --reuid=crm --regid=crm --init-groups -- "$@"
  fi
  exec "$@"
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
if [ "$drop_privileges" -eq 1 ]; then
  exec setpriv --reuid=crm --regid=crm --init-groups -- gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 --access-logfile - --error-logfile -
