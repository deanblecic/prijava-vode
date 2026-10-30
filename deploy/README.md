# Postavljanje na Ubuntu server

Aplikacija radi u Dockeru (PostgreSQL + Django), a ispred nje je Nginx s HTTPS certifikatom
(Let's Encrypt). Fotografije vodomjera vidi samo administrator.

## 1. Domena

Usmjerite domenu (npr. `prijava-vode.duckdns.org`) na IP adresu servera `65.108.144.242`.
Kod DuckDNS-a: prijavite se na duckdns.org, upišite poddomenu `prijava-vode`, u polje
"current ip" upišite `65.108.144.242` i kliknite "update ip".

## 2. Preuzimanje koda na server

```bash
ssh dean@65.108.144.242
sudo apt-get install -y git gh
gh auth login            # repozitorij je privatan; odaberite GitHub.com, HTTPS, prijava preko preglednika
sudo mkdir -p /opt/prijava-vode && sudo chown "$USER" /opt/prijava-vode
gh repo clone deanblecic/prijava-vode /opt/prijava-vode
cd /opt/prijava-vode
```

## 3. Instalacija

```bash
bash deploy/postavi-server.sh prijava-vode.duckdns.org vas@email.hr
sudo docker compose exec web python manage.py createsuperuser
```

Skripta instalira Docker, Nginx i Certbot, otvara samo portove 22, 80 i 443, stvara `.env`
s nasumičnim lozinkama, pokreće aplikaciju, dohvaća HTTPS certifikat i postavlja noćnu
sigurnosnu kopiju. Bez domene umjesto nje navedite IP adresu; tada nema HTTPS-a.

Administratoru u `/admin/` → Korisnici postavite ulogu **administrator**, pa se može
prijaviti i na glavno web sučelje.

## 4. Unos stanova i suvlasnika

U `/admin/`:

1. **Stanovi**: dodajte 21 stan i svakome vodomjer s početnim stanjem (zadnje stanje iz Excela).
2. **Korisnici**: za svakog suvlasnika korisničko ime, lozinka, ime i prezime, a u dnu stan.

## Aplikacija za suvlasnike

Suvlasnicima pošaljite link `https://prijava-vode.duckdns.org/aplikacija/`. Na toj stranici
preuzimaju APK i vide upute za instalaciju. APK se preuzima iz zadnje uspješne izrade na GitHubu.

## Održavanje

| Što | Naredba |
| --- | --- |
| Nova verzija s GitHuba (server i APK) | `bash deploy/azuriraj.sh` |
| Samo nova verzija APK-a | `bash deploy/preuzmi-apk.sh` |
| Zapisi aplikacije | `sudo docker compose logs -f web` |
| Ručna kopija | `sudo deploy/kopija.sh` |
| Vraćanje baze | `gunzip -c /var/backups/prijava-vode/baza-DATUM.sql.gz \| sudo docker compose exec -T db psql -U voda voda` |

Kopije se čuvaju 30 dana u `/var/backups/prijava-vode`. Preporuka je povremeno ih
kopirati i izvan servera.

## Podsjetnici i e-mail o neočitanim vodomjerima

U web sučelju, pod **Podsjetnici**, administrator postavlja dan očitanja (zadano 26.), sat
podsjetnika (zadano 9) i e-mail za obavijest. Od dana očitanja do kraja mjeseca aplikacija
svaki dan u taj sat podsjeti suvlasnike čiji vodomjer još nije očitan. Zadnji dan u mjesecu u
20 h server pošalje popis neočitanih stanova na upisani e-mail (ako je prazan, administratorima).

Za slanje e-maila u `.env` dopišite podatke SMTP poslužitelja, npr. za Gmail
(lozinka aplikacije: Google račun → Sigurnost → Potvrda u dva koraka → Lozinke aplikacija):

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=vas.racun@gmail.com
EMAIL_HOST_PASSWORD=lozinka-aplikacije
```

Zatim `sudo docker compose up -d` i probno slanje:
`sudo docker compose exec web python manage.py obavijest_neocitani --odmah`.

## Uvoz stanova i suvlasnika iz Excela

Tablica ima tri stupca bez zaglavlja: broj stana, "Prezime Ime" i zadnje stanje vodomjera (m³).
Ta stanja postaju početna stanja vodomjera; prvo očitanje u aplikaciji računa razliku od njih.
Vlasnik bez stanja (npr. Grad Rijeka) dobiva stan bez vodomjera i račun bez prijave.
Stanovi se uvoze u jednu zgradu: `--zgrada` je njezina oznaka (npr. RI-ALB-2) ili jedinstveni ID.
Zgradu prvo dodaje superadministrator u administraciji (Zgrade).

```bash
# na svom računalu:
scp "Voda početno.xlsx" dean@65.108.144.242:/opt/prijava-vode/voda.xlsx
# na serveru:
cd /opt/prijava-vode
sudo docker compose cp voda.xlsx web:/tmp/voda.xlsx
sudo docker compose exec web python manage.py uvoz_stanova /tmp/voda.xlsx --zgrada RI-ALB-2 --suho   # provjera
sudo docker compose exec web python manage.py uvoz_stanova /tmp/voda.xlsx --zgrada RI-ALB-2 --pristupni-podaci /tmp/pristupni-podaci.xlsx
sudo docker compose cp web:/tmp/pristupni-podaci.xlsx .
sudo docker compose exec web rm /tmp/voda.xlsx /tmp/pristupni-podaci.xlsx
# na svom računalu:
scp dean@65.108.144.242:/opt/prijava-vode/pristupni-podaci.xlsx .
```

`pristupni-podaci.xlsx` sadrži korisnička imena i lozinke za podjelu suvlasnicima. Nakon
podjele obrišite ga sa servera (`rm pristupni-podaci.xlsx voda.xlsx`).
