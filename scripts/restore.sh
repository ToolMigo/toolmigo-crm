#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Gebruik: $0 /volledig/pad/naar/back-upmap" >&2
  exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir=$(CDPATH= cd -- "$1" 2>/dev/null && pwd) || { echo "Back-upmap bestaat niet." >&2; exit 1; }

for required in database.dump media.tar.gz manifest.txt SHA256SUMS; do
  [ -f "$backup_dir/$required" ] || { echo "Ontbrekend back-upbestand: $required" >&2; exit 1; }
done

(cd "$backup_dir" && sha256sum -c SHA256SUMS)

printf 'Dit vervangt de huidige database en mediabestanden. Typ exact HERSTEL TOOLMIGO: '
read -r confirmation
[ "$confirmation" = 'HERSTEL TOOLMIGO' ] || { echo "Herstel geannuleerd."; exit 1; }

cd "$project_dir"
BACKUP_ROOT="$project_dir/backups/pre-restore" BACKUP_RETENTION_DAYS=3650 "$project_dir/scripts/backup.sh"

docker compose stop app
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --clean --if-exists' < "$backup_dir/database.dump"
docker compose run --rm -T --entrypoint sh app -c 'find /app/media -mindepth 1 -delete && tar -xzf - -C /app/media' < "$backup_dir/media.tar.gz"
docker compose up -d app

echo "Herstel voltooid. Controleer de gezondheidsstatus en voer een functionele controle uit."
