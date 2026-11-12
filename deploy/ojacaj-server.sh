#!/usr/bin/env bash
# Jednokratno ojačavanje servera; smije se pokrenuti i više puta:
#   cd /opt/prijava-vode && bash deploy/ojacaj-server.sh
# - automatske sigurnosne nadogradnje Ubuntua
# - fail2ban: blokira adrese koje pogađaju SSH lozinku
# - vatrozid samo za SSH, HTTP i HTTPS
# - nginx ne odaje svoju verziju
# - lozinka za šifriranje noćnih kopija baze i fotografija
set -euo pipefail

echo "== Paketi"
sudo apt-get update -q
sudo apt-get install -y -q unattended-upgrades fail2ban gnupg ufw

echo "== Automatske sigurnosne nadogradnje"
sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'KRAJ'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
KRAJ

echo "== fail2ban za SSH (5 pogrešaka u 10 minuta = 1 sat blokade)"
sudo tee /etc/fail2ban/jail.d/prijava-vode.conf >/dev/null <<'KRAJ'
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
KRAJ
sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban

echo "== Vatrozid: samo SSH, HTTP i HTTPS"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

echo "== Nginx bez oznake verzije"
# Ako je server_tokens već uključen u glavnoj datoteci (npr. nakon ažuriranja
# Nginxa), ne smije se ponoviti jer se Nginx tada ne pokreće.
SIGURNOST_CONF=/etc/nginx/conf.d/prijava-vode-sigurnost.conf
if grep -qE '^[[:space:]]*server_tokens[[:space:]]' /etc/nginx/nginx.conf; then
    sudo rm -f "$SIGURNOST_CONF"
else
    echo "server_tokens off;" | sudo tee "$SIGURNOST_CONF" >/dev/null
fi
if ! sudo nginx -t; then
    sudo rm -f "$SIGURNOST_CONF"
    sudo nginx -t
fi
sudo systemctl reload nginx

echo "== Lozinka za šifriranje kopija"
LOZINKA_KOPIJA=/root/.prijava-vode-kopija
if ! sudo test -f "$LOZINKA_KOPIJA"; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' | sudo tee "$LOZINKA_KOPIJA" >/dev/null
    sudo chmod 600 "$LOZINKA_KOPIJA"
    echo
    echo "Kopije se od sada šifriraju. Ovu lozinku zapišite u dokument s pristupnim podacima,"
    echo "jer bez nje se kopija ne može vratiti:"
    echo
    sudo cat "$LOZINKA_KOPIJA"
    echo
fi

echo "Gotovo."
