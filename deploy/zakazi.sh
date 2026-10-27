#!/usr/bin/env bash
# Upisuje redovite poslove u root crontab: noćnu kopiju i obavijest o neočitanim vodomjerima.
set -euo pipefail
MAPA="$(cd "$(dirname "$0")/.." && pwd)"
(
    sudo crontab -l 2>/dev/null | grep -v -e kopija.sh -e obavijest_neocitani || true
    echo "15 3 * * * $MAPA/deploy/kopija.sh >> /var/log/prijava-vode-kopija.log 2>&1"
    # Svaki sat; naredba sama šalje samo zadnji dan u mjesecu u 20 h po hrvatskom vremenu.
    echo "5 * * * * cd $MAPA && docker compose exec -T web python manage.py obavijest_neocitani >> /var/log/prijava-vode-obavijest.log 2>&1"
) | sudo crontab -
