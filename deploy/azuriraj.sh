#!/usr/bin/env bash
# Preuzima zadnju verziju s GitHuba i ponovno pokreće aplikaciju.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
sudo docker compose up -d --build
sudo docker compose ps
