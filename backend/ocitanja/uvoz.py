"""Uvoz zgrade iz Excel predloška (predlozak_uvoza.py): zgrada, stanovi, vodomjeri, suvlasnici i zamjenski očitavači.

Tri koraka, da se ništa ne upiše napola:
1. procitaj() pretvara tablicu u obične podatke (spremaju se u sesiju do potvrde),
2. provjeri() ih uspoređuje s bazom i slaže plan ili popis grešaka po listu i retku,
3. uvezi() upisuje plan u jednoj transakciji i vraća korisnička imena i lozinke za podjelu.
"""
import datetime
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from .models import (
    AdministratorZgrade,
    Korisnik,
    KorisnikStan,
    Postavke,
    Stan,
    Vodomjer,
    ZamjenskiOcitavac,
    Zapisnik,
    Zgrada,
    kljuc_adrese,
)
from .predlozak_uvoza import LISTOVI
from .racuni import postavi_novu_lozinku


def ascii_malo(tekst):
    tekst = tekst.replace("đ", "dj").replace("Đ", "Dj")
    return unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower()


def kljuc_osobe(ime, prezime):
    """Isto ime bez obzira na kvačice, velika slova i redoslijed riječi."""
    return " ".join(sorted(ascii_malo(f"{ime} {prezime}").replace("-", " ").split()))


def korisnicko_ime(prezime, ime):
    return ".".join(d for d in ascii_malo(f"{prezime} {ime}").replace("-", " ").split() if d) or "suvlasnik"


def kljuc_stana(broj):
    znamenke = "".join(c for c in broj if c.isdigit())
    return (int(znamenke) if znamenke else 0, broj)


class Greske(list):
    def dodaj(self, list_, red, poruka):
        self.append({"list": list_, "red": red, "poruka": poruka})


# 1. Čitanje tablice ----------------------------------------------------------------------------------------------

def normaliziraj_naslov(tekst):
    return " ".join(str(tekst or "").replace("*", " ").split()).lower()


def vrijednost(stupac, v, list_, red, greske):
    """Vrijednost ćelije u obliku za sesiju (str, int, None); neispravna dodaje grešku i vraća None."""
    if isinstance(v, str):
        v = " ".join(v.split())
    if v in (None, ""):
        if stupac.obavezno:
            greske.dodaj(list_, red, f"„{stupac.naslov}” je obavezno.")
        return "" if stupac.vrsta in ("tekst", "stan") else None

    if stupac.vrsta in ("tekst", "stan"):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, (datetime.date, datetime.datetime)):
            greske.dodaj(list_, red, f"„{stupac.naslov}”: Excel je vrijednost pretvorio u datum; upišite je kao tekst.")
            return ""
        v = str(v).strip()
        if stupac.kljuc.endswith("email"):
            v = v.lower()
            try:
                validate_email(v)
            except ValidationError:
                greske.dodaj(list_, red, f"„{v}” nije ispravna e-mail adresa.")
                return ""
        if stupac.najvise and len(v) > stupac.najvise:
            greske.dodaj(list_, red, f"„{stupac.naslov}” smije imati najviše {stupac.najvise} znakova.")
            return ""
        return v

    if stupac.vrsta == "cijeli":
        try:
            broj = Decimal(str(v).strip().replace(",", "."))
            if broj != broj.to_integral_value():
                raise InvalidOperation
            broj = int(broj)
        except (InvalidOperation, ValueError):
            greske.dodaj(list_, red, f"„{stupac.naslov}”: „{v}” nije cijeli broj.")
            return None
        if not stupac.najmanje <= broj <= stupac.najvise:
            greske.dodaj(list_, red, f"„{stupac.naslov}” mora biti od {stupac.najmanje} do {stupac.najvise}.")
            return None
        return broj

    if stupac.vrsta == "decimalni":
        tekst = str(v).strip().replace(" ", "").replace("m³", "").replace("m3", "")
        if "," in tekst:
            tekst = tekst.replace(".", "").replace(",", ".")
        try:
            broj = Decimal(tekst)
            if not broj.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            greske.dodaj(list_, red, f"„{stupac.naslov}”: „{v}” nije broj.")
            return None
        if broj < 0 or broj >= 10**7:
            greske.dodaj(list_, red, f"„{stupac.naslov}” mora biti između 0 i 9.999.999,999.")
            return None
        if broj != broj.quantize(Decimal("0.001")):
            greske.dodaj(list_, red, f"„{stupac.naslov}” smije imati najviše 3 decimale.")
            return None
        return str(broj.quantize(Decimal("0.001")))

    if stupac.vrsta == "datum":
        if isinstance(v, datetime.datetime):
            datum = v.date()
        elif isinstance(v, datetime.date):
            datum = v
        else:
            datum = None
            for oblik in ("%d.%m.%Y.", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    datum = datetime.datetime.strptime(str(v).strip().replace(" ", ""), oblik).date()
                    break
                except ValueError:
                    pass
            if datum is None:
                greske.dodaj(list_, red, f"„{stupac.naslov}”: „{v}” nije datum (npr. 01.03.2015.).")
                return None
        if datum > timezone.localdate():
            greske.dodaj(list_, red, f"„{stupac.naslov}” ne može biti u budućnosti.")
            return None
        return datum.isoformat()

    # dane
    if v is True or str(v).strip().upper() == "DA":
        return True
    if v is False or str(v).strip().upper() == "NE":
        return False
    greske.dodaj(list_, red, f"„{stupac.naslov}”: upišite DA ili NE.")
    return None


def procitaj(datoteka):
    """Excel → {"Zgrada": [ {kljuc: vrijednost, "_red": n}, ...], ...} i popis grešaka."""
    greske = Greske()
    try:
        knjiga = load_workbook(datoteka, read_only=True, data_only=True)
    except Exception:
        greske.dodaj("Datoteka", None, "Datoteka nije Excel tablica (.xlsx). Spremite je kao .xlsx i pokušajte ponovno.")
        return None, greske
    podaci = {}
    for ime, stupci, obavezan in LISTOVI:
        if ime not in knjiga.sheetnames:
            if obavezan:
                greske.dodaj(ime, None, f"Nema lista „{ime}”. Koristite predložak i ne mijenjajte nazive listova.")
            podaci[ime] = []
            continue
        redovi = knjiga[ime].iter_rows(values_only=True)
        zaglavlje = [normaliziraj_naslov(n) for n in next(redovi, ())]
        polozaj = {}
        for s in stupci:
            if normaliziraj_naslov(s.naslov) in zaglavlje:
                polozaj[s.kljuc] = zaglavlje.index(normaliziraj_naslov(s.naslov))
            elif s.obavezno:
                greske.dodaj(ime, 1, f"Nema stupca „{s.naslov}”. Ne mijenjajte nazive stupaca.")
        podaci[ime] = []
        for broj_retka, red in enumerate(redovi, 2):
            celije = list(red or ())
            if all(c is None or str(c).strip() == "" for c in celije):
                continue
            zapis = {"_red": broj_retka}
            for s in stupci:
                i = polozaj.get(s.kljuc)
                zapis[s.kljuc] = vrijednost(s, celije[i] if i is not None and i < len(celije) else None,
                                            ime, broj_retka, greske)
            podaci[ime].append(zapis)
    knjiga.close()
    return podaci, greske


# 2. Provjera i plan ----------------------------------------------------------------------------------------------

@dataclass
class Osoba:
    ime: str
    prezime: str
    email: str = ""
    telefon: str = ""
    prijava: bool = False
    administrator: bool = False
    postojeci: Korisnik = None
    stanovi: list = field(default_factory=list)
    zamjene: list = field(default_factory=list)

    @property
    def puno_ime(self):
        return f"{self.ime} {self.prezime}".strip()


@dataclass
class Plan:
    zgrada: dict
    postojeca_zgrada: Zgrada
    stanovi: list
    osobe: list
    vlasnistva: list  # (broj_stana, Osoba, od_datuma)
    zamjene: list  # (broj_stana, Osoba)
    upozorenja: list


class Imenik:
    """Osobe iz tablice: ista osoba se prepoznaje po e-mailu, a bez njega po imenu i prezimenu."""

    def __init__(self):
        self.osobe = []

    def nadji_ili_dodaj(self, ime, prezime, email, list_, red, greske):
        kljuc = kljuc_osobe(ime, prezime)
        if email:
            osoba = next((o for o in self.osobe if o.email == email), None)
            if osoba:
                if kljuc_osobe(osoba.ime, osoba.prezime) != kljuc:
                    greske.dodaj(list_, red, f"E-mail {email} već pripada osobi {osoba.puno_ime}. "
                                             "Svaka osoba mora imati svoj e-mail.")
                return osoba
            bez_emaila = [o for o in self.osobe if not o.email and kljuc_osobe(o.ime, o.prezime) == kljuc]
            if len(bez_emaila) == 1:
                bez_emaila[0].email = email
                return bez_emaila[0]
        else:
            isti = [o for o in self.osobe if kljuc_osobe(o.ime, o.prezime) == kljuc]
            if len(isti) == 1:
                return isti[0]
            if len(isti) > 1:
                greske.dodaj(list_, red, f"Više osoba se zove {ime} {prezime}; upišite e-mail da se zna koja je.")
                return isti[0]
        osoba = Osoba(ime=ime, prezime=prezime, email=email)
        self.osobe.append(osoba)
        return osoba


def nadji_zgradu(z, greske):
    po_oznaci = Zgrada.objects.filter(oznaka=z["oznaka"].upper()).first()
    po_adresi = Zgrada.objects.filter(kljuc_adrese=kljuc_adrese(z["ulica"], z["kucni_broj"], z["grad"])).first()
    if po_oznaci and po_adresi and po_oznaci != po_adresi:
        greske.dodaj("Zgrada", z["_red"], f"Oznaka {z['oznaka']} pripada zgradi {po_oznaci.adresa}, "
                                          f"a adresa zgradi {po_adresi.oznaka}.")
    elif po_oznaci and not po_adresi:
        greske.dodaj("Zgrada", z["_red"], f"Oznaka {po_oznaci.oznaka} već pripada drugoj zgradi ({po_oznaci.adresa}).")
    elif po_adresi and not po_oznaci:
        greske.dodaj("Zgrada", z["_red"], f"Zgrada na toj adresi već postoji pod oznakom {po_adresi.oznaka}. "
                                          "Upišite tu oznaku ako želite dodati stanove u nju.")
    return po_oznaci if po_oznaci == po_adresi else None


def provjeri(podaci):
    """Plan uvoza ili None, uz greške (po listu i retku) i upozorenja koja ne sprječavaju uvoz."""
    greske = Greske()
    upozorenja = []

    # Zgrada
    zgrade = podaci.get("Zgrada", [])
    if len(zgrade) != 1:
        greske.dodaj("Zgrada", None, "List Zgrada mora imati točno jedan popunjeni redak (jedna tablica = jedna zgrada).")
        return None, greske
    z = zgrade[0]
    postojeca = nadji_zgradu(z, greske) if z["oznaka"] and z["ulica"] and z["kucni_broj"] and z["grad"] else None
    if postojeca:
        upozorenja.append(f"Zgrada {postojeca.adresa} ({postojeca.oznaka}) već postoji: dodaju se samo stanovi iz tablice.")
        if z["rok_dan"] or z["referentni_dan"]:
            upozorenja.append("Krajnji rok i referentni dan postojeće zgrade se ne mijenjaju; "
                              "promijenite ih na stranici Rokovi i podsjetnici.")
    elif z["rok_dan"] and z["referentni_dan"] and z["referentni_dan"] > z["rok_dan"]:
        greske.dodaj("Zgrada", z["_red"], f"Referentni dan ne može biti iza krajnjeg roka ({z['rok_dan']}.).")

    # Stanovi
    stanovi = {}
    for s in podaci.get("Stanovi", []):
        broj = s["broj_stana"]
        if not broj:
            continue
        if broj in stanovi:
            greske.dodaj("Stanovi", s["_red"], f"Stan {broj} je već upisan u retku {stanovi[broj]['_red']}.")
            continue
        stanovi[broj] = s
        if s["ima_vodomjer"] and s["pocetno_stanje"] is None:
            greske.dodaj("Stanovi", s["_red"], f"Stan {broj} ima vodomjer, ali nema upisano početno stanje.")
        if s["ima_vodomjer"] is False and s["pocetno_stanje"] is not None:
            greske.dodaj("Stanovi", s["_red"], f"Stan {broj}: upisano je stanje vodomjera, a „Ima vodomjer” je NE.")
    if not stanovi:
        greske.dodaj("Stanovi", None, "Nema nijednog stana.")
    if postojeca:
        vec_ima = sorted(postojeca.stanovi.filter(broj_stana__in=stanovi).values_list("broj_stana", flat=True),
                         key=kljuc_stana)
        for broj in vec_ima:
            greske.dodaj("Stanovi", stanovi[broj]["_red"], f"Stan {broj} već postoji u zgradi.")

    # Suvlasnici
    imenik = Imenik()
    vlasnistva = []
    for r in podaci.get("Suvlasnici", []):
        broj = r["broj_stana"]
        if broj and broj not in stanovi:
            greske.dodaj("Suvlasnici", r["_red"], f"Stan {broj} nije upisan na listu Stanovi.")
            continue
        if not broj or not r["prezime"]:
            continue
        osoba = imenik.nadji_ili_dodaj(r["ime"], r["prezime"], r["email"], "Suvlasnici", r["_red"], greske)
        if broj in osoba.stanovi:
            greske.dodaj("Suvlasnici", r["_red"], f"{osoba.puno_ime} je već upisan kao suvlasnik stana {broj}.")
            continue
        osoba.stanovi.append(broj)
        osoba.prijava = osoba.prijava or bool(r["prijava"])
        osoba.telefon = osoba.telefon or r["telefon"]
        vlasnistva.append((broj, osoba, r["od_datuma"]))
    for broj, s in stanovi.items():
        if not any(v[0] == broj for v in vlasnistva):
            greske.dodaj("Stanovi", s["_red"], f"Stan {broj} nema nijednog suvlasnika na listu Suvlasnici.")

    # Zamjenski očitavači
    zamjene = []
    for r in podaci.get("Zamjenski očitavači", []):
        broj = r["broj_stana"]
        if broj and broj not in stanovi:
            greske.dodaj("Zamjenski očitavači", r["_red"], f"Stan {broj} nije upisan na listu Stanovi.")
            continue
        if not broj or not r["ime"] or not r["prezime"]:
            continue
        osoba = imenik.nadji_ili_dodaj(r["ime"], r["prezime"], r["email"], "Zamjenski očitavači", r["_red"], greske)
        if broj in osoba.stanovi:
            greske.dodaj("Zamjenski očitavači", r["_red"], f"{osoba.puno_ime} je suvlasnik stana {broj}, "
                                                           "pa ga ionako može očitati.")
            continue
        if broj in osoba.zamjene:
            greske.dodaj("Zamjenski očitavači", r["_red"], f"{osoba.puno_ime} je već upisan za stan {broj}.")
            continue
        if osoba.stanovi and not osoba.prijava:
            upozorenja.append(f"{osoba.puno_ime} je kod suvlasništva označen bez prijave, ali kao zamjenski "
                              "očitavač dobiva korisničko ime i lozinku.")
        osoba.prijava = True
        osoba.telefon = osoba.telefon or r["telefon"]
        osoba.zamjene.append(broj)
        zamjene.append((broj, osoba))

    # Administrator
    if z["admin_ime"] and z["admin_prezime"] and z["admin_email"]:
        admin = imenik.nadji_ili_dodaj(z["admin_ime"], z["admin_prezime"], z["admin_email"], "Zgrada", z["_red"], greske)
        admin.administrator = True
        admin.prijava = True
        admin.telefon = admin.telefon or z["admin_telefon"]

    if greske:
        return None, greske

    # Postojeći računi: ista osoba se prepoznaje samo po e-mailu; isto ime je samo upozorenje.
    for osoba in imenik.osobe:
        if osoba.email:
            racuni = list(Korisnik.objects.filter(email__iexact=osoba.email))
            aktivni = [k for k in racuni if k.is_active] or racuni
            if len(aktivni) == 1:
                osoba.postojeci = aktivni[0]
                continue
            if len(aktivni) > 1:
                upozorenja.append(f"E-mail {osoba.email} ima više računa; za {osoba.puno_ime} se stvara novi.")
        if osoba.prijava and osoba.ime:
            isti = Korisnik.objects.filter(
                is_active=True, first_name__iexact=osoba.ime, last_name__iexact=osoba.prezime)
            if isti.exists():
                zgrade = sorted(set(
                    Stan.objects.filter(vlasnistva__korisnik__in=isti).values_list("zgrada__oznaka", flat=True)))
                gdje = f" (zgrade {', '.join(zgrade)})" if zgrade else ""
                upozorenja.append(f"{osoba.puno_ime}: isto ime već postoji u aplikaciji{gdje}. Dobiva novi račun; "
                                  "ako je to ista osoba, račune možete spojiti na stranici Korisnici.")

    return Plan(
        zgrada=z, postojeca_zgrada=postojeca,
        stanovi=sorted(stanovi.values(), key=lambda s: kljuc_stana(s["broj_stana"])),
        osobe=imenik.osobe, vlasnistva=vlasnistva, zamjene=zamjene, upozorenja=upozorenja,
    ), greske


# 3. Upis ---------------------------------------------------------------------------------------------------------

def slobodno_korisnicko_ime(osnova):
    ime, n = osnova, 2
    while Korisnik.objects.filter(username__iexact=ime).exists():
        ime, n = f"{osnova}{n}", n + 1
    return ime


@transaction.atomic
def uvezi(plan, request):
    z = plan.zgrada
    zgrada = plan.postojeca_zgrada
    if zgrada is None:
        zgrada = Zgrada(oznaka=z["oznaka"], ulica=z["ulica"], kucni_broj=z["kucni_broj"],
                        postanski_broj=z["postanski_broj"], grad=z["grad"])
        zgrada.full_clean()
        zgrada.save()
        postavke = Postavke.ucitaj(zgrada)
        postavke.rok_dan = z["rok_dan"] or 0
        postavke.referentni_dan = z["referentni_dan"]
        postavke.save()
        Zapisnik.upisi(Zapisnik.Radnja.ZGRADA, f"Dodana zgrada {zgrada.adresa} ({zgrada.oznaka}) uvozom iz Excela",
                       request=request, zgrada=zgrada, uid=str(zgrada.uid))

    pristup = []
    for osoba in plan.osobe:
        lozinka = None
        korisnik = osoba.postojeci
        if korisnik is None:
            korisnik = Korisnik.objects.create_user(
                slobodno_korisnicko_ime(korisnicko_ime(osoba.prezime, osoba.ime)),
                email=osoba.email, first_name=osoba.ime, last_name=osoba.prezime, telefon=osoba.telefon,
            )
            if osoba.prijava:
                lozinka = postavi_novu_lozinku(korisnik)
            else:
                korisnik.set_unusable_password()
                korisnik.is_active = False
                korisnik.save()
        elif osoba.prijava and (not korisnik.is_active or not korisnik.has_usable_password()):
            lozinka = postavi_novu_lozinku(korisnik)
        osoba.korisnik = korisnik
        if osoba.administrator:
            AdministratorZgrade.objects.get_or_create(korisnik=korisnik, zgrada=zgrada)
        uloge = []
        if osoba.stanovi:
            uloge.append("suvlasnik")
        if osoba.zamjene:
            uloge.append("zamjenski očitavač za " + ", ".join(osoba.zamjene))
        if osoba.administrator:
            uloge.append("administrator zgrade")
        pristup.append({
            "stanovi": ", ".join(sorted(osoba.stanovi, key=kljuc_stana)),
            "ime": korisnik.get_full_name() or osoba.puno_ime,
            "korisnicko_ime": korisnik.username,
            "lozinka": lozinka or ("postojeći račun, lozinka se ne mijenja" if osoba.postojeci
                                   else "bez prijave"),
            "nova_lozinka": bool(lozinka),
            "uloga": ", ".join(uloge),
            "administrator": osoba.administrator,
        })

    stanovi = {}
    for s in plan.stanovi:
        stan = Stan.objects.create(zgrada=zgrada, broj_stana=s["broj_stana"], kat=s["kat"], napomena=s["napomena"])
        if s["ima_vodomjer"]:
            Vodomjer.objects.create(stan=stan, serijski_broj=s["serijski_broj"], oznaka=s["mjesto_vodomjera"],
                                    pocetno_stanje=Decimal(s["pocetno_stanje"]))
        stanovi[s["broj_stana"]] = stan
    danas = timezone.localdate()
    for broj, osoba, od in plan.vlasnistva:
        KorisnikStan.objects.create(korisnik=osoba.korisnik, stan=stanovi[broj],
                                    od_datuma=datetime.date.fromisoformat(od) if od else danas)
    for broj, osoba in plan.zamjene:
        ZamjenskiOcitavac.objects.create(stan=stanovi[broj], korisnik=osoba.korisnik)

    novi = sum(1 for o in plan.osobe if o.postojeci is None)
    Zapisnik.upisi(
        Zapisnik.Radnja.STAN,
        f"Uvoz iz Excela: {len(stanovi)} stanova, {novi} novih korisnika",
        request=request, zgrada=zgrada, stanovi=list(stanovi),
    )
    pristup.sort(key=lambda p: (not p["administrator"], not p["stanovi"],
                                kljuc_stana(p["stanovi"].split(",")[0]) if p["stanovi"] else (0, ""), p["ime"]))
    return zgrada, pristup


def tablica_pristupa(zgrada, pristup):
    knjiga = Workbook()
    ws = knjiga.active
    ws.title = "Pristupni podaci"
    ws.append([f"{zgrada.adresa} ({zgrada.oznaka})"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Lozinka je privremena: kod prve prijave korisnik upisuje svoju. Predajte je osobno."])
    ws.append([])
    ws.append(["Stan", "Ime i prezime", "Korisničko ime", "Privremena lozinka", "Uloga"])
    for c in ws[4]:
        c.font = Font(bold=True)
    for p in pristup:
        ws.append([p["stanovi"], p["ime"], p["korisnicko_ime"], p["lozinka"], p["uloga"]])
    for stupac, sirina in zip("ABCDE", [12, 28, 26, 34, 34]):
        ws.column_dimensions[stupac].width = sirina
    return knjiga
