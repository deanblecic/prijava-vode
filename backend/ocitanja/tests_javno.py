from django.contrib.staticfiles import finders

from .javno import UPUTE
from .tests import Osnova


class PocetnaStranicaTest(Osnova):
    def test_neprijavljen_vidi_javnu_stranicu(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "javno/pocetna.html")
        self.assertContains(r, "Prijava za administratore")
        self.assertContains(r, 'href="/prijava/"')
        self.assertContains(r, 'href="/aplikacija/"')
        # Javna stranica ne otkriva podatke zgrade.
        self.assertNotContains(r, "Ana Horvat")

    def test_sve_upute_postoje_u_oba_formata(self):
        r = self.client.get("/")
        for u in UPUTE:
            for nastavak in ("pdf", "docx"):
                putanja = f"javno/upute/{u['datoteka']}.{nastavak}"
                self.assertTrue(finders.find(putanja), putanja)
                self.assertContains(r, f"/static/{putanja}")

    def test_slike_ekrana_postoje(self):
        for ime in ("aplikacija-prijava", "aplikacija-pocetna", "aplikacija-provjera", "web-pregled", "web-ocitanje"):
            self.assertTrue(finders.find(f"javno/slike/{ime}.png"), ime)

    def test_pristupni_podaci_nisu_javni(self):
        self.assertIsNone(finders.find("javno/upute/prijava-vode-pristupni-podaci.docx"))
        self.assertIsNone(finders.find("javno/upute/prijava-vode-pristupni-podaci.pdf"))

    def test_administrator_i_dalje_dobiva_mjesecni_pregled(self):
        self.administrator()
        self.client.login(username="dean", password="lozinka-123")
        r = self.client.get("/")
        self.assertTemplateUsed(r, "upravljanje/pregled.html")
        self.assertContains(r, "Ana Horvat")

    def test_suvlasnik_ne_vidi_upravljanje(self):
        self.client.login(username="ana", password="lozinka-123")
        self.assertEqual(self.client.get("/").status_code, 403)
