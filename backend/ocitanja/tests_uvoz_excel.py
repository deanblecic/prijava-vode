from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import load_workbook

from .models import AdministratorZgrade, Korisnik, Stan, Vodomjer, Zapisnik, ZamjenskiOcitavac, Zgrada
from .predlozak_uvoza import napravi_predlozak
from .tests import Klijent


def datoteka(knjiga, ime="zgrada.xlsx"):
    izlaz = BytesIO()
    knjiga.save(izlaz)
    return SimpleUploadedFile(ime, izlaz.getvalue())


class UvozIzExcelaTest(TestCase):
    client_class = Klijent

    def setUp(self):
        Korisnik.objects.create_superuser("dean", password="lozinka-123")
        self.client.login(username="dean", password="lozinka-123")

    def ucitaj(self, knjiga):
        return self.client.post("/zgrade/uvoz/", {"tablica": datoteka(knjiga)})

    def potvrdi(self):
        return self.client.post("/zgrade/uvoz/", {"akcija": "potvrdi"})

    def test_primjer_se_uvozi(self):
        r = self.ucitaj(napravi_predlozak(primjer=True))
        self.assertContains(r, "Provjera je prošla")
        self.assertContains(r, "Potvrdi i uvezi")
        self.assertFalse(Zgrada.objects.exists(), "prije potvrde ništa se ne upisuje")

        r = self.potvrdi()
        self.assertRedirects(r, "/zgrade/uvoz/gotovo/")
        zgrada = Zgrada.objects.get(oznaka="RI-ALB-2")
        self.assertEqual(zgrada.adresa, "Moše Albaharija 2, 51000 Rijeka")
        self.assertEqual((zgrada.postavke.rok_dan, zgrada.postavke.referentni_dan), (0, 26))
        self.assertEqual(zgrada.stanovi.count(), 5)
        self.assertEqual(Vodomjer.objects.filter(stan__zgrada=zgrada).count(), 4)
        v = Vodomjer.objects.get(stan__broj_stana="03")
        self.assertEqual((v.pocetno_stanje, v.serijski_broj, v.oznaka), (Decimal("1574.25"), "ZR-2019-00433", "kuhinja"))
        self.assertEqual(Stan.objects.get(broj_stana="04").napomena, "Ključ kod susjeda u stanu 03")

        sanja = Korisnik.objects.get(email="sanja.kljukic@primjer.hr")
        self.assertEqual(sorted(s.broj_stana for s in sanja.stanovi.all()), ["03", "05"])
        self.assertEqual(str(sanja.vlasnistva.get(stan__broj_stana="03").od_datuma), "2015-03-01")
        self.assertTrue(ZamjenskiOcitavac.objects.filter(korisnik=sanja, stan__broj_stana="04").exists())
        self.assertEqual(Stan.objects.get(broj_stana="03").korisnici.count(), 2)

        grad = Korisnik.objects.get(last_name="Grad Rijeka")
        self.assertFalse(grad.is_active)
        self.assertFalse(grad.has_usable_password())

        ivana = Korisnik.objects.get(email="ivana.horvat@primjer.hr")
        self.assertTrue(AdministratorZgrade.objects.filter(korisnik=ivana, zgrada=zgrada).exists())
        self.assertTrue(Zapisnik.objects.filter(zgrada=zgrada, opis__startswith="Uvoz iz Excela").exists())

        r = self.client.get("/zgrade/uvoz/gotovo/")
        self.assertContains(r, "kljukic.sanja")
        r = self.client.get("/zgrade/uvoz/gotovo/?preuzmi=1")
        redovi = list(load_workbook(BytesIO(r.content)).active.iter_rows(min_row=5, values_only=True))
        self.assertEqual(len(redovi), 6)  # Ivana, Marko, Grad, Sanja, Petar, Željko
        self.assertEqual(redovi[0][1], "Ivana Horvat")
        marko = next(red for red in redovi if red[2] == "kovacevic.marko")
        self.assertEqual(marko[0], "01")
        self.client.logout()
        self.assertTrue(self.client.login(username="kovacevic.marko", password=marko[3]))
        self.assertTrue(Korisnik.objects.get(username="kovacevic.marko").mora_promijeniti_lozinku)

    def test_greske_po_retku_i_nista_se_ne_upisuje(self):
        knjiga = napravi_predlozak(primjer=True)
        knjiga["Stanovi"]["D2"] = None  # stan 01 ima vodomjer bez stanja
        knjiga["Stanovi"].append(["03", 1, "DA", 5])  # stan 03 dvaput
        knjiga["Suvlasnici"].append(["99", "Ana", "Anić", "", "", None, "DA"])
        r = self.ucitaj(knjiga)
        self.assertContains(r, "Tablica nije uvezena")
        self.assertContains(r, "Stan 01 ima vodomjer, ali nema upisano početno stanje.")
        self.assertContains(r, "Stan 03 je već upisan u retku 4.")
        self.assertContains(r, "Stan 99 nije upisan na listu Stanovi.")
        self.assertEqual(self.potvrdi().status_code, 302)
        self.assertFalse(Zgrada.objects.exists())
        self.assertEqual(Korisnik.objects.count(), 1)

    def test_neispravne_vrijednosti(self):
        knjiga = napravi_predlozak(primjer=True)
        knjiga["Suvlasnici"]["D2"] = "nije-email"
        knjiga["Stanovi"]["D3"] = "puno"
        knjiga["Suvlasnici"]["G3"] = "možda"
        r = self.ucitaj(knjiga)
        self.assertContains(r, "„nije-email” nije ispravna e-mail adresa.")
        self.assertContains(r, "„puno” nije broj.")
        self.assertContains(r, "upišite DA ili NE.")

    def test_prazni_predlozak(self):
        r = self.ucitaj(napravi_predlozak())
        self.assertContains(r, "List Zgrada mora imati točno jedan popunjeni redak")

    def test_nije_excel(self):
        r = self.client.post("/zgrade/uvoz/", {"tablica": SimpleUploadedFile("a.xlsx", b"nije excel")})
        self.assertContains(r, "Datoteka nije Excel tablica")

    def test_stan_bez_suvlasnika(self):
        knjiga = napravi_predlozak(primjer=True)
        knjiga["Stanovi"].append(["06", 2, "NE"])
        r = self.ucitaj(knjiga)
        self.assertContains(r, "Stan 06 nema nijednog suvlasnika")

    def test_postojeci_email_zadrzava_racun(self):
        marko = Korisnik.objects.create_user("marko", password="njegova-lozinka", email="Marko.Kovacevic@primjer.hr",
                                             first_name="Marko", last_name="Kovačević")
        self.ucitaj(napravi_predlozak(primjer=True))
        self.potvrdi()
        self.assertEqual([s.broj_stana for s in marko.stanovi.all()], ["01"])
        self.assertFalse(Korisnik.objects.filter(username="kovacevic.marko").exists())
        marko.refresh_from_db()
        self.assertTrue(marko.check_password("njegova-lozinka"))
        self.assertContains(self.client.get("/zgrade/uvoz/gotovo/"), "postojeći račun")

    def test_isto_ime_u_drugoj_zgradi_je_upozorenje(self):
        Korisnik.objects.create_user("zhustek", first_name="Željko", last_name="Hustek")
        r = self.ucitaj(napravi_predlozak(primjer=True))
        self.assertContains(r, "isto ime već postoji u aplikaciji")
        self.potvrdi()
        self.assertEqual(Korisnik.objects.filter(last_name="Hustek").count(), 2)

    def test_postojeca_zgrada_dobiva_nove_stanove(self):
        zgrada = Zgrada.objects.create(oznaka="RI-ALB-2", ulica="Moše Albaharija", kucni_broj="2",
                                       postanski_broj="51000", grad="Rijeka")
        r = self.ucitaj(napravi_predlozak(primjer=True))
        self.assertContains(r, "već postoji: dodaju se samo stanovi")
        self.potvrdi()
        self.assertEqual(zgrada.stanovi.count(), 5)
        self.assertEqual(Zgrada.objects.count(), 1)
        r = self.ucitaj(napravi_predlozak(primjer=True))
        self.assertContains(r, "Stan 01 već postoji u zgradi.")

    def test_oznaka_druge_zgrade(self):
        Zgrada.objects.create(oznaka="RI-ALB-2", ulica="Korzo", kucni_broj="1", postanski_broj="51000", grad="Rijeka")
        r = self.ucitaj(napravi_predlozak(primjer=True))
        self.assertContains(r, "već pripada drugoj zgradi")

    def test_brojevi_iz_excela(self):
        """Excel često sprema broj stana kao broj, a stanje s decimalnim zarezom kao tekst."""
        knjiga = napravi_predlozak(primjer=True)
        knjiga["Stanovi"]["A2"] = 1.0
        knjiga["Stanovi"]["D2"] = "1.314,5"
        knjiga["Suvlasnici"]["A2"] = 1
        self.ucitaj(knjiga)
        self.potvrdi()
        self.assertEqual(Vodomjer.objects.get(stan__broj_stana="1").pocetno_stanje, Decimal("1314.5"))

    def test_samo_superadministrator(self):
        zgrada = Zgrada.objects.create(oznaka="X", ulica="Korzo", kucni_broj="1", postanski_broj="51000", grad="Rijeka")
        admin = Korisnik.objects.create_user("admin", password="lozinka-123")
        AdministratorZgrade.objects.create(korisnik=admin, zgrada=zgrada)
        self.client.logout()
        self.client.login(username="admin", password="lozinka-123")
        self.assertEqual(self.client.get("/zgrade/uvoz/").status_code, 403)
        self.assertEqual(self.client.get("/zgrade/uvoz/predlozak/").status_code, 403)
        self.assertEqual(self.ucitaj(napravi_predlozak(primjer=True)).status_code, 403)

    def test_preuzimanje_predloska(self):
        r = self.client.get("/zgrade/uvoz/predlozak/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(load_workbook(BytesIO(r.content)).sheetnames,
                         ["Upute", "Zgrada", "Stanovi", "Suvlasnici", "Zamjenski očitavači"])
        self.assertContains(self.client.get("/zgrade/"), "Uvezi iz Excela")
