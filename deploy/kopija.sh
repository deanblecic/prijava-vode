#!/usr/bin/env bash
# Dnevna kopija baze i fotografija; čuva zadnjih 30 dana u /var/backups/prijava-vode.
set -euo pipefail
MAPA="$(cd "$(dirname "$0")/.." && pwd)"
CILJ=/var/backups/prijava-vode
DATUM=$(date +%F)
mkdir -p "$CILJ"
cd "$MAPA"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$CILJ/baza-$DATUM.sql.gz"
docker compose exec -T web tar -czf - -C /data media > "$CILJ/fotografije-$DATUM.tar.gz"
find "$CILJ" -type f -mtime +30 -delete
echo "$(date -Is) kopija spremljena"
