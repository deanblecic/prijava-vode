# Prijava vode

Sustav za mjesečna očitanja vodomjera u zgradi: Android aplikacija za suvlasnike
(fotografija + OCR), Django server s PostgreSQL bazom i web sučelje za administratora.

## Struktura

- `backend/` – Django projekt (`config`) i aplikacija `ocitanja` (modeli, API, administracija)
- `docker-compose.yml` – PostgreSQL + Django (gunicorn) za server
- `.env.example` – predložak postavki

## Lokalni razvoj

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py createsuperuser
../.venv/bin/python manage.py runserver
```

Bez varijable `POSTGRES_DB` koristi se SQLite. Testovi: `../.venv/bin/python manage.py test ocitanja`.

## Web sučelje za administratora

Aplikacija podržava više zgrada. Zgrada se prepoznaje po ulici, kućnom broju i gradu, a zgrada i stan
imaju jedinstveni ID (`uid`) koji se ne mijenja; sve veze idu preko ID-ja.

- **Superadministrator** (`is_superuser`) vidi sve zgrade i bira ih na `/zgrade/` ili u zaglavlju.
- **Administrator zgrade** (`AdministratorZgrade`) vidi samo svoje zgrade; tuđi stanovi, očitanja i fotografije vraćaju 404.
- **Suvlasnik** se prijavljuje samo u Android aplikaciju; web ga ne pušta dalje od prijave.

Prijava na `/prijava/`. Za isprobavanje na praznoj bazi `manage.py primjer_podataka` stvara zgradu
od 21 stana, suvlasnike i tri mjeseca očitanja (admin / probna-lozinka).

- `/zgrade/` – popis zgrada s brojem neočitanih vodomjera
- `/` – neprijavljenima javna početna stranica (opis, slike ekrana, upute, preuzimanje uputa, prijava za administratore);
  prijavljenom administratoru mjesečni pregled stanova odabrane zgrade, s oznakom tko nije predao i što treba provjeriti
- `/ocitanje/<id>/` – fotografija, potvrda, odbijanje i ispravak očitanja
- `/stan/<id>/` – vlasnici, povijest očitanja i ručni unos
- `/stan/<id>/promjena-vlasnika/` – prodaja stana
- `/izvoz/?mjesec=2026-10` – Excel tablica za mjesec
- Django administracija (skrivena adresa, poveznica Sustav) – samo superadministrator
- `/stanovi/`, `/korisnici/`, `/administratori/`, `/zapisnik/` – stanovi, računi, spajanje istoimenih računa, administratori zgrade i trag radnji
- `/prijava/` → `/prijava/kod/` – lozinka pa kod iz Google Authenticatora (prvi put postavljanje)

## API za Android aplikaciju

Sve osim prijave traži zaglavlje `Authorization: Token <token>`.

| Metoda | Putanja | Opis |
| --- | --- | --- |
| POST | `/api/prijava/` | `korisnicko_ime`, `lozinka` → `token` |
| POST | `/api/odjava/` | poništava token |
| GET | `/api/ja/` | korisnik, njegove zgrade (s podsjetnikom svake), stanovi u svim zgradama, vodomjer, prethodno stanje i očitanje ovog mjeseca |
| GET | `/api/ocitanja/` | povijest očitanja korisnikovih stanova |
| POST | `/api/ocitanja/` | multipart: `vodomjer`, `novo_stanje`, `ocr_vrijednost`, `fotografija`, `datum_ocitanja`, `napomena`, `potvrdi_manje` |

Greške predaje vraćaju `{"kod", "poruka"}`: `nema_prava` (403), `vec_potvrdeno`,
`manje_od_prethodnog`, `vodomjer_neaktivan` (409). Kod `manje_od_prethodnog` aplikacija
pita korisnika i šalje ponovno s `potvrdi_manje=true`.

## Pravila

- Jedno očitanje po vodomjeru mjesečno; ponovna predaja ispravlja ga dok ga administrator ne potvrdi.
- Prethodno stanje je zadnje neodbijeno očitanje, ili početno stanje vodomjera.
- Razlika veća od `PRAG_SUMNJIVE_RAZLIKE` × prosjek zadnjih 12 mjeseci označava se za provjeru.
- Jedan aktivni vodomjer po stanu; zamijenjeni ostaju neaktivni radi povijesti.
- Promjena vlasnika (`servisi.promijeni_vlasnika`) zatvara stara suvlasništva, povijest ostaje.

## Android aplikacija

`android/` – Kotlin, Jetpack Compose, CameraX i ML Kit (OCR na mobitelu).

1. Prijava korisničkim imenom i lozinkom (token se pamti na mobitelu).
2. Početni zaslon: stan, prethodno stanje i je li očitanje za ovaj mjesec predano.
3. Kamera s okvirom za brojilo i svjetlom; OCR predlaže broj (`ocr/CitacBrojila.kt`).
4. Potvrda: slika, prijedlog broja, drugi mogući brojevi i izračunata potrošnja.
5. Povijest očitanja.

APK gradi GitHub Actions (artefakt `ocitanje-vode-apk` na svakoj izradi). Adresa servera
(`https://prijava-vode.duckdns.org`) zadaje se svojstvom `serverUrl` u `android/gradle.properties`.
