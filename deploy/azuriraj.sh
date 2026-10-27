#!/usr/bin/env bash
# Preuzima zadnju verziju s GitHuba i ponovno pokreće aplikaciju.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
bash deploy/preuzmi-apk.sh || echo "APK nije preuzet; web radi i bez njega."
sudo docker compose up -d --build
sudo docker compose ps
