#!/usr/bin/env bash
# Prva instalacija na Ubuntu server. Pokrenuti kao korisnik sa sudo pravima:
#   bash deploy/postavi-server.sh prijava-vode.duckdns.org vas@email.hr
# Bez domene (samo IP): bash deploy/postavi-server.sh 65.108.144.242
set -euo pipefail

DOMENA="${1:?Navedite domenu ili IP adresu servera}"
EMAIL="${2:-}"
MAPA="$(cd "$(dirname "$0")/.." && pwd)"

echo "== Paketi (Docker, Nginx, Certbot, vatrozid)"
sudo apt-get update -q
sudo apt-get install -y -q ca-certificates curl nginx certbot python3-certbot-nginx ufw
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true

echo "== Vatrozid: SSH, HTTP, HTTPS"
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

echo "== Postavke (.env)"
cd "$MAPA"
if [ ! -f .env ]; then
    TAJNA=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
    LOZINKA_BAZE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
    if [[ "$DOMENA" =~ ^[0-9.]+$ ]]; then SHEMA=http; SIGURNI=0; else SHEMA=https; SIGURNI=1; fi
    cat > .env <<KRAJ
DJANGO_SECRET_KEY=$TAJNA
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=$DOMENA,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=$SHEMA://$DOMENA
DJANGO_SECURE_COOKIES=$SIGURNI
POSTGRES_DB=voda
POSTGRES_USER=voda
POSTGRES_PASSWORD=$LOZINKA_BAZE
PRAG_SUMNJIVE_RAZLIKE=3
KRAJ
    chmod 600 .env
    echo "Stvoren .env s nasumičnim lozinkama."
fi

echo "== Android aplikacija za preuzimanje"
mkdir -p apk
bash deploy/preuzmi-apk.sh || echo "APK nije preuzet; pokrenite kasnije: bash deploy/preuzmi-apk.sh"

echo "== Pokretanje aplikacije"
sudo docker compose up -d --build

echo "== Nginx"
sed "s/DOMENA/$DOMENA/" deploy/nginx-prijava-vode.conf | sudo tee /etc/nginx/sites-available/prijava-vode >/dev/null
sudo ln -sf /etc/nginx/sites-available/prijava-vode /etc/nginx/sites-enabled/prijava-vode
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

if [[ ! "$DOMENA" =~ ^[0-9.]+$ ]]; then
    echo "== HTTPS certifikat (Let's Encrypt)"
    if [ -n "$EMAIL" ]; then
        sudo certbot --nginx -d "$DOMENA" --non-interactive --agree-tos -m "$EMAIL" --redirect
    else
        sudo certbot --nginx -d "$DOMENA" --non-interactive --agree-tos --register-unsafely-without-email --redirect
    fi
fi

echo "== Noćna sigurnosna kopija u 3:15"
( sudo crontab -l 2>/dev/null | grep -v kopija.sh; echo "15 3 * * * $MAPA/deploy/kopija.sh >> /var/log/prijava-vode-kopija.log 2>&1" ) | sudo crontab -

echo
echo "Gotovo. Stvorite administratora:"
echo "  sudo docker compose exec web python manage.py createsuperuser"
echo "Web sučelje: $( [[ "$DOMENA" =~ ^[0-9.]+$ ]] && echo http || echo https )://$DOMENA/"
