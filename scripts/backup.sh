#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_root=${BACKUP_ROOT:-"$project_dir/backups"}
retention_days=${BACKUP_RETENTION_DAYS:-30}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$backup_root/$timestamp"

case "$retention_days" in
  ''|*[!0-9]*) echo "BACKUP_RETENTION_DAYS moet een positief geheel getal zijn." >&2; exit 1 ;;
esac

mkdir -p "$backup_dir"
cd "$project_dir"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$backup_dir/database.dump"
docker compose exec -T app sh -c 'cd /app/media && tar -czf - .' > "$backup_dir/media.tar.gz"

cat > "$backup_dir/manifest.txt" <<EOF
created_utc=$timestamp
database_format=postgresql_custom
media_format=tar_gzip
EOF

(cd "$backup_dir" && sha256sum database.dump media.tar.gz manifest.txt > SHA256SUMS)
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' -mtime "+$retention_days" -exec rm -rf -- {} +

echo "Back-up gereed: $backup_dir"
