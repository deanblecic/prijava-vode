"""Uvoz stanova, suvlasnika i početnih stanja vodomjera iz Excel tablice.

Tablica ima tri stupca bez zaglavlja: broj stana, "Prezime Ime" vlasnika i stanje
vodomjera u m³. Suvlasniku s više stanova stvara se jedan račun. Vlasnik bez
stanja (npr. Grad Rijeka) dobiva stan bez vodomjera i račun bez prijave.

Lozinke se stvaraju na serveru i spremaju samo u izlaznu tablicu pristupnih podataka.
"""
import secrets
import unicodedata
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import Workbook, load_workbook

from ocitanja.models import Korisnik, KorisnikStan, Stan, Vodomjer

SLOVA_LOZINKE = "abcdefghjkmnpqrstuvwxyz23456789"


def korisnicko_ime(puno_ime):
    ascii_ime = unicodedata.normalize("NFKD", puno_ime.replace("đ", "dj").replace("Đ", "Dj"))
    ascii_ime = ascii_ime.encode("ascii", "ignore").decode().lower()
    return ".".join(dio for dio in ascii_ime.replace("-", " ").split() if dio)


def razdvoji_ime(puno_ime):
    """'Prelić Gerdević Nataša' → ('Nataša', 'Prelić Gerdević'); jedna riječ je prezime."""
    dijelovi = puno_ime.split()
    if len(dijelovi) == 1:
        return "", dijelovi[0]
    return dijelovi[-1], " ".join(dijelovi[:-1])


def nova_lozinka():
    return "-".join("".join(secrets.choice(SLOVA_LOZINKE) for _ in range(4)) for _ in range(3))


class Command(BaseCommand):
    help = "Uvozi stanove, suvlasnike i početna stanja iz Excel tablice."

    def add_arguments(self, parser):
        parser.add_argument("tablica", help="Excel datoteka: broj stana, Prezime Ime, stanje (m³)")
        parser.add_argument(
            "--pristupni-podaci", default="pristupni-podaci.xlsx",
            help="Kamo spremiti korisnička imena i lozinke za podjelu suvlasnicima",
        )
        parser.add_argument("--suho", action="store_true", help="Samo prikaži što bi se uvezlo")

    def handle(self, tablica, pristupni_podaci, suho, **opcije):
        redovi = self.procitaj(tablica)
        if suho:
            for broj, vlasnik, stanje in redovi:
                self.stdout.write(f"Stan {broj}: {vlasnik}, {stanje if stanje is not None else 'bez vodomjera'}")
            return
        with transaction.atomic():
            podaci = self.uvezi(redovi)
        self.spremi_pristupne_podatke(podaci, pristupni_podaci)
        self.stdout.write(self.style.SUCCESS(
            f"Uvezeno {len(redovi)} stanova i {len(podaci)} korisnika. "
            f"Pristupni podaci: {pristupni_podaci}"
        ))

    def procitaj(self, tablica):
        redovi = []
        for red in load_workbook(tablica, read_only=True, data_only=True).active.iter_rows(values_only=True):
            if not red or red[0] is None:
                continue
            broj, vlasnik, stanje = (list(red) + [None, None, None])[:3]
            broj = str(broj).strip()
            if not vlasnik:
                raise CommandError(f"Stan {broj} nema upisanog vlasnika.")
            try:
                stanje = None if stanje in (None, "") else Decimal(str(stanje).replace(",", "."))
            except ArithmeticError:
                raise CommandError(f"Stan {broj}: stanje '{stanje}' nije broj.")
            redovi.append((broj, " ".join(str(vlasnik).split()), stanje))
        if not redovi:
            raise CommandError("Tablica je prazna.")
        brojevi = [r[0] for r in redovi]
        if len(set(brojevi)) != len(brojevi):
            raise CommandError("Isti broj stana pojavljuje se više puta.")
        postojeci = Stan.objects.filter(broj_stana__in=brojevi).values_list("broj_stana", flat=True)
        if postojeci:
            raise CommandError(f"Ovi stanovi već postoje u bazi: {', '.join(postojeci)}. Uvoz se ne ponavlja.")
        return redovi

    def uvezi(self, redovi):
        korisnici = {}
        podaci = []
        for broj, vlasnik, stanje in redovi:
            korisnik = korisnici.get(vlasnik)
            if korisnik is None:
                korisnik, lozinka = self.novi_korisnik(vlasnik, moze_prijavu=stanje is not None)
                korisnici[vlasnik] = korisnik
                podaci.append({"korisnik": korisnik, "lozinka": lozinka, "stanovi": []})
            elif stanje is not None and not korisnik.has_usable_password():
                lozinka = nova_lozinka()
                korisnik.set_password(lozinka)
                korisnik.is_active = True
                korisnik.save()
                next(p for p in podaci if p["korisnik"] == korisnik)["lozinka"] = lozinka
            stan = Stan.objects.create(broj_stana=broj)
            KorisnikStan.objects.create(korisnik=korisnik, stan=stan)
            if stanje is not None:
                Vodomjer.objects.create(stan=stan, pocetno_stanje=stanje)
            next(p for p in podaci if p["korisnik"] == korisnik)["stanovi"].append(broj)
        return podaci

    def novi_korisnik(self, puno_ime, moze_prijavu):
        # Ustanova bez vodomjera (npr. "Grad Rijeka") zadržava naziv kakav jest.
        ime, prezime = razdvoji_ime(puno_ime) if moze_prijavu else ("", puno_ime)
        osnova = korisnicko_ime(puno_ime) or "suvlasnik"
        username, n = osnova, 2
        while Korisnik.objects.filter(username=username).exists():
            username, n = f"{osnova}{n}", n + 1
        if not moze_prijavu:
            # Vlasnik bez vodomjera (npr. Grad Rijeka) vidi se u izvještaju, ali se ne prijavljuje.
            korisnik = Korisnik.objects.create_user(username, first_name=ime, last_name=prezime, is_active=False)
            korisnik.set_unusable_password()
            korisnik.save()
            return korisnik, None
        lozinka = nova_lozinka()
        korisnik = Korisnik.objects.create_user(username, password=lozinka, first_name=ime, last_name=prezime)
        return korisnik, lozinka

    def spremi_pristupne_podatke(self, podaci, putanja):
        knjiga = Workbook()
        list_ = knjiga.active
        list_.title = "Pristupni podaci"
        list_.append(["Stan", "Ime i prezime", "Korisničko ime", "Lozinka"])
        for p in sorted(podaci, key=lambda p: p["stanovi"][0]):
            k = p["korisnik"]
            list_.append([
                ", ".join(p["stanovi"]),
                f"{k.first_name} {k.last_name}".strip(),
                k.username,
                p["lozinka"] or "bez prijave (nema vodomjera)",
            ])
        for stupac, sirina in zip("ABCD", [10, 28, 26, 30]):
            list_.column_dimensions[stupac].width = sirina
        knjiga.save(putanja)
