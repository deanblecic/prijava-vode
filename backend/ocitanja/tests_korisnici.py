import datetime
from decimal import Decimal

from rest_framework.authtoken.models import Token

from .models import AdministratorZgrade, Korisnik, KorisnikStan, Ocitanje, Stan, Zapisnik, Zgrada
from .servisi import predaj_ocitanje
from .tests_zgrade import DvijeZgrade


class SpajanjeTest(DvijeZgrade):
    def setUp(self):
        super().setUp()
        # Druga Ana Horvat u istoj zgradi, sa stanom 4 (kao Sanja Njirić sa stanovima 17 i 19).
        self.ana2 = Korisnik.objects.create_user("ana.horvat2", password="lozinka-123", first_name="Ana", last_name="Horvat")
        KorisnikStan.objects.filter(stan=self.stan4).update(korisnik=self.ana2)
        self.o4 = predaj_ocitanje(self.ana2, self.v4, "55")
        Token.objects.create(user=self.ana2)

    def test_popis_oznacava_isto_ime(self):
        self.prijava("admin_a")
        r = self.client.get("/korisnici/")
        self.assertContains(r, "Možda ista osoba")
        self.assertContains(r, f"?a={self.ana.pk}&amp;b={self.ana2.pk}")

    def test_administrator_spaja_u_svojoj_zgradi(self):
        self.prijava("admin_a")
        url = f"/korisnici/spoji/?a={self.ana.pk}&b={self.ana2.pk}"
        self.assertContains(self.client.get(url), "Spoji račune")
        r = self.client.post("/korisnici/spoji/", {"a": self.ana.pk, "b": self.ana2.pk, "ostaje": self.ana.pk, "potvrda": "1"})
        self.assertRedirects(r, "/korisnici/")
        self.assertEqual(sorted(s.broj_stana for s in self.ana.aktivni_stanovi()), ["3", "4"])
        self.o4.refresh_from_db()
        self.assertEqual(self.o4.korisnik, self.ana)
        self.ana2.refresh_from_db()
        self.assertFalse(self.ana2.is_active)
        self.assertFalse(Token.objects.filter(user=self.ana2).exists())
        zapis = Zapisnik.objects.get(radnja=Zapisnik.Radnja.SPAJANJE)
        self.assertEqual(zapis.zgrada, self.zgrada)

        # Superadministrator poništava spajanje.
        Korisnik.objects.create_superuser("dean", password="lozinka-123")
        self.prijava("dean")
        self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada.pk})
        self.client.post(f"/zapisnik/{zapis.pk}/ponisti/")
        self.ana2.refresh_from_db()
        self.assertTrue(self.ana2.is_active)
        self.assertEqual([s.broj_stana for s in self.ana2.aktivni_stanovi()], ["4"])
        self.o4.refresh_from_db()
        self.assertEqual(self.o4.korisnik, self.ana2)

    def test_samo_pregled_bez_potvrde_ne_spaja(self):
        self.prijava("admin_a")
        self.client.post("/korisnici/spoji/", {"a": self.ana.pk, "b": self.ana2.pk, "ostaje": self.ana2.pk})
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.is_active)

    def test_racun_s_drugom_zgradom_spaja_samo_superadministrator(self):
        KorisnikStan.objects.create(korisnik=self.ana2, stan=self.b3, od_datuma=datetime.date(2020, 1, 1))
        self.prijava("admin_a")
        r = self.client.post("/korisnici/spoji/", {"a": self.ana.pk, "b": self.ana2.pk, "ostaje": self.ana.pk, "potvrda": "1"})
        self.assertContains(r, "spaja superadministrator")
        self.ana2.refresh_from_db()
        self.assertTrue(self.ana2.is_active)

    def test_administrator_ne_vidi_korisnika_druge_zgrade(self):
        self.prijava("admin_a")
        r = self.client.get(f"/korisnici/spoji/?a={self.ana.pk}&b={self.marija.pk}")
        self.assertEqual(r.status_code, 404)
        self.assertNotContains(self.client.get("/korisnici/"), "Marija")

    def test_superadministrator_spaja_izmedju_zgrada(self):
        marija_a = Korisnik.objects.create_user("marija.babic2", first_name="Marija", last_name="Babić")
        KorisnikStan.objects.filter(korisnik=self.ana2).update(korisnik=marija_a)
        Korisnik.objects.create_superuser("dean", password="lozinka-123")
        self.prijava("dean")
        self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada.pk})
        r = self.client.get("/korisnici/")
        self.assertContains(r, "ZG-ILI-10/3")
        self.client.post("/korisnici/spoji/", {
            "a": self.marija.pk, "b": marija_a.pk, "ostaje": self.marija.pk, "potvrda": "1",
        })
        self.assertEqual(sorted(s.oznaka for s in self.marija.aktivni_stanovi()), ["RI-ALB-2/4", "ZG-ILI-10/3"])


class LozinkaTest(DvijeZgrade):
    def test_nova_lozinka(self):
        Token.objects.create(user=self.ivo)
        self.prijava("admin_a")
        r = self.client.post(f"/korisnici/{self.ivo.pk}/nova-lozinka/")
        lozinka = r.context["lozinka"]
        self.ivo.refresh_from_db()
        self.assertTrue(self.ivo.check_password(lozinka))
        self.assertTrue(self.ivo.mora_promijeniti_lozinku)
        self.assertFalse(Token.objects.filter(user=self.ivo).exists())

    def test_ne_za_racun_s_drugom_zgradom(self):
        KorisnikStan.objects.create(korisnik=self.ivo, stan=self.b3, od_datuma=datetime.date(2020, 1, 1))
        self.prijava("admin_a")
        self.assertEqual(self.client.post(f"/korisnici/{self.ivo.pk}/nova-lozinka/").status_code, 403)
        self.assertEqual(self.client.post(f"/korisnici/{self.marija.pk}/nova-lozinka/").status_code, 404)
        self.ivo.refresh_from_db()
        self.assertTrue(self.ivo.check_password("lozinka-123"))


class AdministratoriTest(DvijeZgrade):
    def test_dodaje_suvlasnika_i_novu_osobu(self):
        self.prijava("admin_a")
        r = self.client.get("/administratori/")
        self.assertEqual(
            sorted(r.context["forma"].fields["postojeci"].queryset.values_list("username", flat=True)), ["ana", "ivo"]
        )
        self.client.post("/administratori/", {"postojeci": self.ivo.pk})
        self.assertTrue(AdministratorZgrade.objects.filter(korisnik=self.ivo, zgrada=self.zgrada).exists())
        r = self.client.post("/administratori/", {"ime": "Petra", "prezime": "Kos", "korisnicko_ime": "petra.kos"})
        petra = Korisnik.objects.get(username="petra.kos")
        self.assertTrue(petra.check_password(r.context["lozinka"]))
        self.assertTrue(petra.mora_promijeniti_lozinku)
        self.assertEqual(list(petra.zgrade_za_upravljanje()), [self.zgrada])
        self.assertFalse(petra.is_staff)

    def test_ne_dodaje_korisnika_druge_zgrade(self):
        self.prijava("admin_a")
        r = self.client.post("/administratori/", {"postojeci": self.marija.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AdministratorZgrade.objects.filter(korisnik=self.marija, zgrada=self.zgrada).exists())

    def test_posljednji_se_ne_uklanja(self):
        self.prijava("admin_a")
        self.client.post("/administratori/", {"akcija": "ukloni", "korisnik": self.admin_a.pk})
        self.assertTrue(AdministratorZgrade.objects.filter(korisnik=self.admin_a).exists())
        self.client.post("/administratori/", {"postojeci": self.ivo.pk})
        r = self.client.post("/administratori/", {"akcija": "ukloni", "korisnik": self.admin_a.pk})
        self.assertRedirects(r, "/prijava/", fetch_redirect_response=False)
        self.assertFalse(AdministratorZgrade.objects.filter(korisnik=self.admin_a).exists())

    def test_ne_uklanja_administratora_druge_zgrade(self):
        self.prijava("admin_a")
        self.administrator("admin_a2")
        r = self.client.post("/administratori/", {"akcija": "ukloni", "korisnik": self.admin_b.pk})
        self.assertEqual(r.status_code, 404)


class StanoviTest(DvijeZgrade):
    def test_dodaje_stan_s_vodomjerom(self):
        self.prijava("admin_b")
        self.client.post("/stanovi/", {"broj_stana": "4", "pocetno_stanje": "12.5"})
        stan = Stan.objects.get(zgrada=self.zgrada_b, broj_stana="4")
        self.assertEqual(stan.vodomjeri.get().pocetno_stanje, Decimal("12.5"))
        r = self.client.post("/stanovi/", {"broj_stana": "4"})
        self.assertContains(r, "već postoji")

    def test_zamjena_vodomjera(self):
        self.prijava("admin_b")
        self.client.post(f"/stan/{self.b3.pk}/vodomjer/", {"serijski_broj": "N1", "pocetno_stanje": "0"})
        self.assertEqual(list(self.b3.vodomjeri.filter(aktivan=True).values_list("serijski_broj", flat=True)), ["N1"])
        self.assertEqual(self.client.post(f"/stan/{self.stan3.pk}/vodomjer/", {"pocetno_stanje": "0"}).status_code, 404)


class NovaZgradaTest(DvijeZgrade):
    def test_samo_superadministrator(self):
        self.prijava("admin_a")
        self.assertEqual(self.client.get("/zgrade/nova/").status_code, 403)
        Korisnik.objects.create_superuser("dean", password="lozinka-123")
        self.prijava("dean")
        r = self.client.post("/zgrade/nova/", {
            "ulica": "Riva", "kucni_broj": "1", "postanski_broj": "21000", "grad": "Split", "oznaka": "st-riv-1",
        })
        self.assertRedirects(r, "/administratori/")
        self.assertTrue(Zgrada.objects.filter(oznaka="ST-RIV-1").exists())
        r = self.client.post("/zgrade/nova/", {
            "ulica": "riva", "kucni_broj": "1", "postanski_broj": "21000", "grad": "SPLIT", "oznaka": "X",
        })
        self.assertContains(r, "već postoji")


class ZapisnikTest(DvijeZgrade):
    def test_potvrda_upisana_samo_u_svoju_zgradu(self):
        self.prijava("admin_a")
        self.client.post(f"/ocitanje/{self.o_a.pk}/", {"akcija": "potvrdi"})
        self.assertContains(self.client.get("/zapisnik/"), "potvrđeno")
        self.prijava("admin_b")
        self.assertNotContains(self.client.get("/zapisnik/"), "potvrđeno")
        self.assertEqual(Ocitanje.objects.get(pk=self.o_a.pk).status, "potvrdeno")
