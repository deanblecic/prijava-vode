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

`createsuperuser` stvara superadministratora. Kod prve prijave na web postavlja Google Authenticator.

## 4. Zgrade, administratori i stanovi

Sve se radi na webu:

1. Superadministrator na stranici **Zgrade** klikne **Nova zgrada** (ulica, kućni broj, poštanski broj, grad, oznaka).
2. Na stranici **Administratori** doda administratora zgrade. Aplikacija mu stvara privremenu lozinku;
   kod prve prijave on postavlja svoju lozinku i Google Authenticator.
3. Stanove upisuje na stranici **Stanovi** ili ih uvozi iz Excela (dolje).

## 5. Ojačavanje servera

```bash
cd /opt/prijava-vode && bash deploy/ojacaj-server.sh
```

Uključuje automatske sigurnosne nadogradnje, fail2ban za SSH, vatrozid i šifriranje noćnih kopija.
Lozinku za kopije koju skripta ispiše spremite uz ostale pristupne podatke.

Preporuka: prijava na server SSH ključem umjesto lozinke. Na svom računalu `ssh-keygen`, pa
`ssh-copy-id dean@65.108.144.242`; tek kad prijava ključem radi, na serveru u
`/etc/ssh/sshd_config` postavite `PasswordAuthentication no` i pokrenite `sudo systemctl restart ssh`.

## Sigurnost aplikacije

- Administratori se na web prijavljuju lozinkom (barem 12 znakova) i kodom iz Google Authenticatora.
  Suvlasnici web ne mogu koristiti, samo aplikaciju.
- Nakon 5 pogrešnih pokušaja za isto korisničko ime (ili 20 s iste adrese) prijava je blokirana 15 minuta.
- Web sesija istječe nakon 30 minuta neaktivnosti; prijava u aplikaciji nakon 90 dana nekorištenja.
- Django administracija nije na `/admin/` nego na skrivenoj adresi; superadministrator je otvara
  poveznicom **Sustav** u zaglavlju.
- Superadministrator koji izgubi mobitel i rezervne kodove na serveru pokreće
  `sudo docker compose exec web python manage.py ponisti_dva_koraka KORISNICKO_IME`.

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
| Vraćanje baze | `sudo gpg --batch --pinentry-mode loopback --passphrase-file /root/.prijava-vode-kopija -d /var/backups/prijava-vode/baza-DATUM.sql.gz.gpg \| gunzip \| sudo docker compose exec -T db psql -U voda voda` |

Kopije se čuvaju 30 dana u `/var/backups/prijava-vode`, šifrirane lozinkom iz `/root/.prijava-vode-kopija`
(naredba ispod je koristi). Prije `ojacaj-server.sh` kopije nisu šifrirane (`.sql.gz` bez `.gpg`).
`azuriraj.sh` napravi kopiju i prije svakog ažuriranja. Preporuka je povremeno ih
kopirati i izvan servera.

## E-pošta, rokovi i podsjetnici

Server šalje e-poštu za tri stvari: link za zaboravljenu lozinku administratora, podsjetnike
suvlasnicima koji još nisu očitali i popis neočitanih stanova administratoru zgrade. Za to u `.env`
dopišite podatke SMTP poslužitelja, npr. za Gmail (lozinka aplikacije: Google račun → Sigurnost →
Potvrda u dva koraka → Lozinke aplikacija):

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=vas.racun@gmail.com
EMAIL_HOST_PASSWORD=lozinka-aplikacije
DEFAULT_FROM_EMAIL=Očitanja vodomjera <vas.racun@gmail.com>
```

Brevo (besplatno do 300 poruka dnevno): `EMAIL_HOST=smtp-relay.brevo.com`, `EMAIL_PORT=587`, a korisnik i
lozinka su login i SMTP ključ iz Brevo postavki (SMTP & API). Zatim `sudo docker compose up -d`.

**Svaki administrator mora imati upisan e-mail** (u webu: klik na svoje ime gore desno → Moj račun;
na stranici Administratori vidi se tko ga nema). Bez e-maila ne može sam postaviti novu lozinku.

### Zaboravljena lozinka

Na prijavi je link **Zaboravljena lozinka?**. Administrator (glavni ili zgrade) upiše svoj e-mail i dobije
jednokratni link koji vrijedi sat vremena. Odgovor na ekranu je uvijek isti, postoji li adresa ili ne.
Najviše 3 zahtjeva na sat za istu adresu i 10 s iste IP adrese. Nakon promjene vlasnik dobiva obavijest
e-mailom, a prijava i dalje traži kod iz Google Authenticatora. Tko nema pristup e-mailu, glavni
administrator mu na stranici Administratori postavi privremenu lozinku (mijenja je kod prve prijave).
Glavnom administratoru bez e-maila lozinku postavlja `sudo docker compose exec web python manage.py changepassword IME`.

### Rokovi i podsjetnici

U web sučelju, pod **Rokovi i podsjetnici**, administrator zgrade postavlja:

- **krajnji rok** (1.–28. ili zadnji dan u mjesecu) i što nakon roka: očitanje se i dalje prima, ali je
  označeno kao zakašnjelo, ili je predaja u aplikaciji zatvorena (administrator ga tada unosi na webu);
- **podsjetnike suvlasnicima** koji nisu očitali: raspored (samo prvi dan, prvi dan i dan roka, svaki dan,
  od odabranog dana do roka, zadnjih N dana, ili odabrani dani) i sat. Podsjetnik stiže na mobitel, a
  suvlasnicima s upisanim e-mailom i e-poštom;
- **obavijest administratoru** s popisom neočitanih: isti izbor rasporeda, sat i adrese primatelja.

`deploy/zakazi.sh` (pokreće ga i `azuriraj.sh`) upisuje u cron naredbu `posalji_obavijesti` svakih 15 minuta.
Ona šalje kad je dan slanja i sat prošao, po hrvatskom vremenu, a u bazi bilježi što je poslano, pa nitko
ne dobije istu poruku dvaput. Probno slanje svega odmah (ne bilježi se):
`sudo docker compose exec web python manage.py posalji_obavijesti --odmah --zgrada RI-ALB-2`.

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
