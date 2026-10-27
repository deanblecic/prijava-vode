#!/usr/bin/env bash
# Preuzima APK iz zadnje uspješne izrade na grani main i stavlja ga na /aplikacija/.
# Traži prijavu u GitHub CLI (gh auth login).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=deanblecic/prijava-vode
RUN=$(gh run list -R "$REPO" -b main -w CI -s success -L 1 --json databaseId -q '.[0].databaseId')
if [ -z "$RUN" ]; then
    echo "Nema uspješne izrade na grani main." >&2
    exit 1
fi
PRIVREMENO=$(mktemp -d)
trap 'rm -rf "$PRIVREMENO"' EXIT
gh run download "$RUN" -R "$REPO" -n ocitanje-vode-apk -D "$PRIVREMENO"
APK=$(find "$PRIVREMENO" -name '*.apk' | head -1)
mkdir -p apk
# Docker stvara mapu kao root ako je još nema pri pokretanju; vrati je korisniku.
[ -w apk ] || sudo chown "$USER" apk
cp "$APK" apk/ocitanje-vode.apk.novo
mv apk/ocitanje-vode.apk.novo apk/ocitanje-vode.apk
echo "APK iz izrade $RUN je postavljen na /aplikacija/."
