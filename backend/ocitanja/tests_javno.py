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


class KontaktTest(Osnova):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def test_pocetna_vodi_na_kontakt(self):
        self.assertContains(self.client.get("/"), 'href="/kontakt/"')
        r = self.client.get("/kontakt/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Kontaktirajte nas")

    def test_poruka_se_salje_na_kontakt_adresu(self):
        from django.core import mail
        r = self.client.post("/kontakt/", {"ime": "Ivana Horvat", "email": "ivana@example.com",
                                           "poruka": "Kako dodati drugu zgradu?"})
        self.assertContains(r, "Vaša poruka je poslana")
        self.assertEqual(len(mail.outbox), 1)
        poruka = mail.outbox[0]
        self.assertEqual(poruka.to, ["ocitanje-vode@gmail.com"])
        self.assertEqual(poruka.reply_to, ["ivana@example.com"])
        self.assertIn("Kako dodati drugu zgradu?", poruka.body)
        self.assertIn("Ivana Horvat", poruka.subject)

    def test_prazna_poruka_se_ne_salje(self):
        from django.core import mail
        r = self.client.post("/kontakt/", {"ime": "", "email": "", "poruka": "   "})
        self.assertContains(r, "Upišite poruku.")
        r = self.client.post("/kontakt/", {"email": "nije-adresa", "poruka": "Bok"})
        self.assertContains(r, "Upišite ispravnu e-mail adresu.")
        self.assertEqual(len(mail.outbox), 0)

    def test_skriveno_polje_zaustavlja_automatske_programe(self):
        from django.core import mail
        r = self.client.post("/kontakt/", {"poruka": "Reklama", "web_stranica": "http://spam.example"})
        self.assertContains(r, "Vaša poruka je poslana")
        self.assertEqual(len(mail.outbox), 0)

    def test_ogranicenje_broja_poruka(self):
        from django.core import mail
        for _ in range(5):
            self.client.post("/kontakt/", {"poruka": "Pitanje"})
        r = self.client.post("/kontakt/", {"poruka": "Pitanje"})
        self.assertContains(r, "Poslali ste previše poruka")
        self.assertEqual(len(mail.outbox), 5)

    def test_greska_slanja_se_javlja(self):
        from unittest import mock
        with mock.patch("ocitanja.javno.EmailMessage.send", side_effect=OSError("smtp")), \
                self.assertLogs("ocitanja.javno", "ERROR"):
            r = self.client.post("/kontakt/", {"poruka": "Pitanje"})
        self.assertContains(r, "Poruku trenutno nije moguće poslati")
