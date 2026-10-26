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

## API za Android aplikaciju

Sve osim prijave traži zaglavlje `Authorization: Token <token>`.

| Metoda | Putanja | Opis |
| --- | --- | --- |
| POST | `/api/prijava/` | `korisnicko_ime`, `lozinka` → `token` |
| POST | `/api/odjava/` | poništava token |
| GET | `/api/ja/` | korisnik, njegovi stanovi, vodomjer, prethodno stanje i očitanje ovog mjeseca |
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
