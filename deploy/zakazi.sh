#!/usr/bin/env bash
# Upisuje redovite poslove u root crontab: noćnu kopiju te podsjetnike i obavijesti o neočitanim vodomjerima.
set -euo pipefail
MAPA="$(cd "$(dirname "$0")/.." && pwd)"
(
    sudo crontab -l 2>/dev/null | grep -v -e kopija.sh -e obavijest_neocitani -e posalji_obavijesti || true
    echo "15 3 * * * $MAPA/deploy/kopija.sh >> /var/log/prijava-vode-kopija.log 2>&1"
    # Svakih 15 minuta; naredba sama šalje samo u dane i sate koje je administrator zgrade odabrao (hrvatsko vrijeme).
    echo "*/15 * * * * cd $MAPA && docker compose exec -T web python manage.py posalji_obavijesti >> /var/log/prijava-vode-obavijest.log 2>&1"
) | sudo crontab -
