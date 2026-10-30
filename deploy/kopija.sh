#!/usr/bin/env bash
# Dnevna kopija baze i fotografija; čuva zadnjih 30 dana u /var/backups/prijava-vode.
set -euo pipefail
MAPA="$(cd "$(dirname "$0")/.." && pwd)"
CILJ=/var/backups/prijava-vode
DATUM=$(date +%F)
mkdir -p "$CILJ"
cd "$MAPA"
# Uz lozinku iz ojacaj-server.sh kopije se šifriraju (vraćanje: gpg -d datoteka.gpg > datoteka).
LOZINKA=/root/.prijava-vode-kopija
spremi() {
    if [ -r "$LOZINKA" ]; then
        gpg --batch --yes --pinentry-mode loopback --passphrase-file "$LOZINKA" --symmetric --cipher-algo AES256 -o "$1.gpg"
        rm -f "$1"
    else
        cat > "$1"
    fi
}
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip | spremi "$CILJ/baza-$DATUM.sql.gz"
docker compose exec -T web tar -czf - -C /data media | spremi "$CILJ/fotografije-$DATUM.tar.gz"
find "$CILJ" -type f -mtime +30 -delete
echo "$(date -Is) kopija spremljena"
