import datetime
from io import StringIO

import pyotp
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Korisnik, Zapisnik
from .sigurnost import SESIJA_DVA_KORAKA
from .tests_zgrade import DvijeZgrade


class DvaKorakaTest(DvijeZgrade):
    client_class = Client

    def lozinka(self, ime="admin_b", lozinka="lozinka-123"):
        return self.client.post("/prijava/", {"username": ime, "password": lozinka})

    def test_prvo_postavljanje_pa_prijava_kodom(self):
        self.assertRedirects(self.lozinka(), "/prijava/kod/")
        r = self.client.get("/prijava/kod/")
        self.assertContains(r, "Postavite Google Authenticator")
        self.assertContains(r, "<svg")
        tajna = r.context["tajna"]
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.totp_tajna, "")
        r = self.client.post("/prijava/kod/", {"kod": pyotp.TOTP(tajna).now()})
        self.assertEqual(len(r.context["kodovi"]), 10)
        rezervni = r.context["kodovi"][0]
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.totp_tajna, tajna)
        self.assertContains(self.client.get("/"), "Marija Babić")

        # Druga prijava: isti kod ne vrijedi dvaput, rezervni vrijedi jednom.
        self.client.logout()
        self.lozinka()
        r = self.client.post("/prijava/kod/", {"kod": pyotp.TOTP(tajna).now()})
        self.assertContains(r, "Kod nije ispravan")
        r = self.client.post("/prijava/kod/", {"kod": rezervni})
        self.assertRedirects(r, "/")
        self.client.logout()
        self.lozinka()
        self.assertContains(self.client.post("/prijava/kod/", {"kod": rezervni}), "Kod nije ispravan")

    def test_bez_koda_nema_pristupa(self):
        self.lozinka()
        self.assertRedirects(self.client.get("/"), "/prijava/?next=/")

    def test_sesija_bez_drugog_koraka_se_odjavljuje(self):
        self.client.force_login(self.admin_b)
        self.assertRedirects(self.client.get("/"), "/prijava/?next=/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_krivi_kod_vise_puta_blokira(self):
        self.admin_b.totp_tajna = pyotp.random_base32()
        self.admin_b.save()
        self.lozinka()
        for _ in range(5):
            self.client.post("/prijava/kod/", {"kod": "000000"})
        r = self.client.post("/prijava/kod/", {"kod": pyotp.TOTP(self.admin_b.totp_tajna).now()})
        self.assertContains(r, "Previše pogrešnih pokušaja")

    def test_naredba_ponistava_authenticator(self):
        self.admin_b.totp_tajna = pyotp.random_base32()
        self.admin_b.save()
        call_command("ponisti_dva_koraka", "admin_b", stdout=StringIO())
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.totp_tajna, "")


class BlokadaTest(DvijeZgrade):
    client_class = Client

    def test_web_blokira_nakon_pet_pogresnih(self):
        for _ in range(5):
            self.client.post("/prijava/", {"username": "admin_b", "password": "krivo"})
        r = self.client.post("/prijava/", {"username": "admin_b", "password": "lozinka-123"})
        self.assertContains(r, "Previše pogrešnih pokušaja")
        self.assertEqual(Zapisnik.objects.filter(radnja=Zapisnik.Radnja.NEUSPJELA_PRIJAVA).count(), 5)

    def test_blokada_istjece(self):
        for _ in range(5):
            self.client.post("/prijava/", {"username": "admin_b", "password": "krivo"})
        Zapisnik.objects.update(vrijeme=timezone.now() - datetime.timedelta(minutes=16))
        self.assertRedirects(self.client.post("/prijava/", {"username": "admin_b", "password": "lozinka-123"}), "/prijava/kod/")

    def test_aplikacija_blokira(self):
        api = APIClient()
        for _ in range(5):
            api.post("/api/prijava/", {"korisnicko_ime": "Ana", "lozinka": "krivo"})
        r = api.post("/api/prijava/", {"korisnicko_ime": "ana", "lozinka": "lozinka-123"})
        self.assertEqual(r.status_code, 429)

    @override_settings(BLOKADA_POKUSAJA_ADRESA=3)
    def test_blokada_po_adresi(self):
        for ime in ("a", "b", "c"):
            self.client.post("/prijava/", {"username": ime, "password": "krivo"}, HTTP_X_FORWARDED_FOR="9.9.9.9")
        r = self.client.post("/prijava/", {"username": "admin_b", "password": "lozinka-123"}, HTTP_X_FORWARDED_FOR="9.9.9.9")
        self.assertContains(r, "Previše pogrešnih pokušaja")
        r = self.client.post("/prijava/", {"username": "admin_b", "password": "lozinka-123"}, HTTP_X_FORWARDED_FOR="8.8.8.8")
        self.assertRedirects(r, "/prijava/kod/")


class LozinkaIZaglavljaTest(DvijeZgrade):
    def test_obavezna_promjena_lozinke_na_webu(self):
        self.admin_b.mora_promijeniti_lozinku = True
        self.admin_b.save()
        self.prijava("admin_b")
        self.assertRedirects(self.client.get("/"), "/lozinka/")
        r = self.client.post("/lozinka/", {"new_password1": "kratka-1", "new_password2": "kratka-1"})
        self.assertContains(r, "barem 12 znakova")
        r = self.client.post("/lozinka/", {"new_password1": "Plavi-vodomjer-2026", "new_password2": "Plavi-vodomjer-2026"})
        self.assertRedirects(r, "/")
        self.admin_b.refresh_from_db()
        self.assertFalse(self.admin_b.mora_promijeniti_lozinku)
        self.assertTrue(self.admin_b.password.startswith("argon2"))

    def test_promjena_lozinke_u_aplikaciji(self):
        self.ana.mora_promijeniti_lozinku = True
        self.ana.save()
        api = APIClient()
        r = api.post("/api/prijava/", {"korisnicko_ime": "ana", "lozinka": "lozinka-123"})
        self.assertTrue(r.json()["mora_promijeniti_lozinku"])
        api.credentials(HTTP_AUTHORIZATION=f"Token {r.json()['token']}")
        self.assertTrue(api.get("/api/ja/").json()["mora_promijeniti_lozinku"])
        self.assertEqual(api.post("/api/lozinka/", {"nova_lozinka": "123"}).status_code, 400)
        self.assertEqual(api.post("/api/lozinka/", {"nova_lozinka": "moja-voda-17"}).status_code, 204)
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password("moja-voda-17"))
        self.assertFalse(self.ana.mora_promijeniti_lozinku)
        # Bez obaveze treba i stara lozinka.
        self.assertEqual(api.post("/api/lozinka/", {"nova_lozinka": "druga-voda-18"}).status_code, 400)

    def test_prijava_u_aplikaciji_istjece(self):
        token = Token.objects.create(user=self.ana)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - datetime.timedelta(days=30))
        self.assertEqual(api.get("/api/ja/").status_code, 200)
        token.refresh_from_db()
        self.assertGreater(token.created, timezone.now() - datetime.timedelta(minutes=1))
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - datetime.timedelta(days=91))
        self.assertEqual(api.get("/api/ja/").status_code, 401)

    def test_sigurnosna_zaglavlja(self):
        r = self.client.get("/prijava/")
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")

    def test_django_administracija_vodi_na_zajednicku_prijavu(self):
        from django.urls import reverse

        url = reverse("admin:index")
        self.client.logout()
        r = self.client.get(url, follow=True)
        self.assertTrue(r.redirect_chain[-1][0].startswith("/prijava/"))
        self.assertContains(r, "Korisničko ime")

    def test_superadministrator_ponistava_authenticator(self):
        self.admin_b.totp_tajna = "ABC"
        self.admin_b.save()
        self.prijava("admin_b")
        self.client.post("/administratori/", {"akcija": "ponisti_kod", "korisnik": self.admin_b.pk})
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.totp_tajna, "ABC")
        Korisnik.objects.create_superuser("dean", password="lozinka-123")
        self.prijava("dean")
        self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada_b.pk})
        self.client.post("/administratori/", {"akcija": "ponisti_kod", "korisnik": self.admin_b.pk})
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.totp_tajna, "")
        self.assertTrue(self.client.session[SESIJA_DVA_KORAKA])
