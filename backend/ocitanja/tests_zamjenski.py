"""Zamjenski očitavači: osoba koja u aplikaciji očitava vodomjer umjesto vlasnika, za jedan ili više stanova."""
import datetime
from decimal import Decimal

from rest_framework.test import APIClient

from .models import Korisnik, KorisnikStan, Ocitanje, Stan, Vodomjer, ZamjenskiOcitavac, Zapisnik, Zgrada
from .obavijesti import neocitani_po_korisniku
from .racuni import korisnici_zgrade, samo_u_zgradi, ponisti_spajanje, spoji_racune
from .servisi import GreskaOcitanja, predaj_ocitanje
from .tests import Osnova


class ZamjenskiOsnova(Osnova):
    def setUp(self):
        super().setUp()
        # Marija (stan 7) i Ivo (stan 4) ne koriste mobitel; za njih očitava susjeda Dragana iz stana 3.
        self.marija = Korisnik.objects.create_user("marija.pajic", password="lozinka-123",
                                                   first_name="Marija", last_name="Pajić")
        self.stan7 = Stan.objects.create(zgrada=self.zgrada, broj_stana="07")
        KorisnikStan.objects.create(korisnik=self.marija, stan=self.stan7, od_datuma=datetime.date(2020, 1, 1))
        self.v7 = Vodomjer.objects.create(stan=self.stan7, pocetno_stanje=Decimal("10.000"))
        self.dragana = self.ana
        ZamjenskiOcitavac.objects.create(stan=self.stan7, korisnik=self.dragana)
        ZamjenskiOcitavac.objects.create(stan=self.stan4, korisnik=self.dragana)

    def api(self, korisnik):
        klijent = APIClient()
        klijent.force_authenticate(korisnik)
        return klijent


class ApiTest(ZamjenskiOsnova):
    def test_ja_vraca_vlastiti_stan_prvi_pa_zamjenske(self):
        r = self.api(self.dragana).get("/api/ja/")
        stanovi = [(s["broj_stana"], s["zamjena"], s["vlasnici"]) for s in r.data["stanovi"]]
        self.assertEqual(stanovi, [("3", False, "Ana Horvat"), ("4", True, "Ivo Ivić"), ("07", True, "Marija Pajić")])
        self.assertEqual(len(r.data["zgrade"]), 1)

    def test_vlasnik_i_dalje_vidi_svoj_stan(self):
        r = self.api(self.marija).get("/api/ja/")
        self.assertEqual([(s["broj_stana"], s["zamjena"]) for s in r.data["stanovi"]], [("07", False)])

    def test_zamjenski_predaje_za_stan_koji_ocitava(self):
        r = self.api(self.dragana).post("/api/ocitanja/", {"vodomjer": self.v7.pk, "novo_stanje": "12.5"})
        self.assertEqual(r.status_code, 201, r.data)
        ocitanje = Ocitanje.objects.get(vodomjer=self.v7)
        self.assertEqual(ocitanje.korisnik, self.dragana)
        self.assertEqual(ocitanje.razlika, Decimal("2.5"))

    def test_ne_moze_za_stan_koji_ne_ocitava(self):
        ZamjenskiOcitavac.objects.filter(stan=self.stan4).delete()
        r = self.api(self.dragana).post("/api/ocitanja/", {"vodomjer": self.v4.pk, "novo_stanje": "60"})
        self.assertEqual(r.status_code, 403)
        # Ni vlasnik ne može očitati stan za koji je samo susjed zamjenski očitavač.
        r = self.api(self.marija).post("/api/ocitanja/", {"vodomjer": self.v3.pk, "novo_stanje": "120"})
        self.assertEqual(r.status_code, 403)

    def test_povijest_ukljucuje_zamjenske_stanove(self):
        predaj_ocitanje(self.marija, self.v7, "11")
        r = self.api(self.dragana).get("/api/ocitanja/")
        self.assertEqual([o["broj_stana"] for o in r.data], ["07"])

    def test_nakon_uklanjanja_nema_prava(self):
        ZamjenskiOcitavac.objects.filter(stan=self.stan7, korisnik=self.dragana).delete()
        with self.assertRaises(GreskaOcitanja):
            predaj_ocitanje(self.dragana, self.v7, "12", samo_vlasnik=True)

    def test_zamjenski_bez_vlastitog_stana(self):
        kci = Korisnik.objects.create_user("kci", password="lozinka-123")
        ZamjenskiOcitavac.objects.create(stan=self.stan7, korisnik=kci)
        r = self.api(kci).get("/api/ja/")
        self.assertEqual([(s["broj_stana"], s["zamjena"]) for s in r.data["stanovi"]], [("07", True)])


class WebTest(ZamjenskiOsnova):
    def setUp(self):
        super().setUp()
        self.dean = self.administrator()
        self.client.login(username="dean", password="lozinka-123")

    def test_stranica_stana_pokazuje_ocitavace(self):
        r = self.client.get(f"/stan/{self.stan7.pk}/")
        self.assertContains(r, "Zamjenski očitavači")
        self.assertContains(r, "Ana Horvat")

    def test_dodaje_postojeceg_korisnika(self):
        r = self.client.post(f"/stan/{self.stan3.pk}/zamjenski/", {"postojeci": self.ivo.pk})
        self.assertRedirects(r, f"/stan/{self.stan3.pk}/#zamjenski", fetch_redirect_response=False)
        self.assertTrue(ZamjenskiOcitavac.objects.filter(stan=self.stan3, korisnik=self.ivo).exists())
        self.assertTrue(Zapisnik.objects.filter(radnja=Zapisnik.Radnja.STAN, opis__contains="očitava stan").exists())

    def test_vlasnik_nije_ponudjen(self):
        r = self.client.post(f"/stan/{self.stan7.pk}/zamjenski/", {"postojeci": self.marija.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ZamjenskiOcitavac.objects.filter(stan=self.stan7, korisnik=self.marija).exists())

    def test_dodaje_novog_korisnika(self):
        self.client.post(f"/stan/{self.stan7.pk}/zamjenski/", {
            "ime": "Petra", "prezime": "Pajić", "korisnicko_ime": "petra.pajic", "lozinka": "Dobra-lozinka-77",
        })
        petra = Korisnik.objects.get(username="petra.pajic")
        self.assertTrue(petra.mora_promijeniti_lozinku)
        self.assertTrue(ZamjenskiOcitavac.objects.filter(stan=self.stan7, korisnik=petra).exists())
        self.assertIn(petra, korisnici_zgrade(self.zgrada))

    def test_greska_ostaje_na_stranici_stana(self):
        r = self.client.post(f"/stan/{self.stan7.pk}/zamjenski/", {"ime": "Petra"})
        self.assertContains(r, "Obavezno za novog korisnika.")
        self.assertEqual(ZamjenskiOcitavac.objects.filter(stan=self.stan7).count(), 1)

    def test_uklanja(self):
        self.client.post(f"/stan/{self.stan7.pk}/zamjenski/{self.dragana.pk}/ukloni/")
        self.assertFalse(ZamjenskiOcitavac.objects.filter(stan=self.stan7).exists())

    def test_tudja_zgrada(self):
        druga = Zgrada.objects.create(oznaka="ZG-1", ulica="Ilica", kucni_broj="1", postanski_broj="10000", grad="Zagreb")
        tudji = Stan.objects.create(zgrada=druga, broj_stana="1")
        self.assertEqual(self.client.post(f"/stan/{tudji.pk}/zamjenski/", {"postojeci": self.ivo.pk}).status_code, 404)
        # Ni korisnik druge zgrade nije ponuđen.
        stranac = Korisnik.objects.create_user("stranac")
        KorisnikStan.objects.create(korisnik=stranac, stan=tudji)
        self.client.post(f"/stan/{self.stan7.pk}/zamjenski/", {"postojeci": stranac.pk})
        self.assertFalse(ZamjenskiOcitavac.objects.filter(korisnik=stranac).exists())

    def test_popis_korisnika_i_stanova(self):
        self.assertContains(self.client.get("/korisnici/"), "očitava i: 4, 07")
        self.assertContains(self.client.get("/stanovi/"), "Ana Horvat")


class RacuniIObavijestiTest(ZamjenskiOsnova):
    def test_podsjetnik_stize_i_zamjenskom(self):
        po_korisniku = neocitani_po_korisniku(self.zgrada, datetime.date.today().replace(day=1))
        self.assertEqual(po_korisniku[self.dragana], ["3", "4", "07"])
        self.assertEqual(po_korisniku[self.marija], ["07"])

    def test_zamjena_u_drugoj_zgradi(self):
        druga = Zgrada.objects.create(oznaka="ZG-1", ulica="Ilica", kucni_broj="1", postanski_broj="10000", grad="Zagreb")
        self.assertTrue(samo_u_zgradi(self.dragana, self.zgrada))
        ZamjenskiOcitavac.objects.create(stan=Stan.objects.create(zgrada=druga, broj_stana="1"), korisnik=self.dragana)
        self.assertFalse(samo_u_zgradi(self.dragana, self.zgrada))

    def test_spajanje_prenosi_i_ponistava_zamjene(self):
        ana2 = Korisnik.objects.create_user("ana2", first_name="Ana", last_name="Horvat")
        ZamjenskiOcitavac.objects.create(stan=self.stan7, korisnik=ana2)
        ZamjenskiOcitavac.objects.create(stan=self.stan3, korisnik=ana2)
        podaci = spoji_racune(self.dragana, ana2)
        self.assertEqual(
            sorted(self.dragana.zamjenska_ocitanja.values_list("stan__broj_stana", flat=True)), ["07", "3", "4"]
        )
        ponisti_spajanje(podaci)
        self.assertEqual(sorted(ana2.zamjenska_ocitanja.values_list("stan__broj_stana", flat=True)), ["07", "3"])
