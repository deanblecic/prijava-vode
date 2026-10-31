import re

from django.core import mail
from django.test import Client, override_settings
from rest_framework.authtoken.models import Token

from .models import Korisnik, Zapisnik
from .tests_zgrade import DvijeZgrade

NOVA = "Plavi-vodomjer-2026"


class ZaboravljenaLozinkaTest(DvijeZgrade):
    client_class = Client

    def setUp(self):
        super().setUp()
        self.admin_b.email = "admin.b@example.com"
        self.admin_b.save()

    def zatrazi(self, email="admin.b@example.com", **zaglavlja):
        return self.client.post("/prijava/zaboravljena-lozinka/", {"email": email}, **zaglavlja)

    def link(self):
        return re.search(r"https?://[^/]+(/prijava/nova-lozinka/\S+)", mail.outbox[-1].body).group(1)

    def test_prijava_nudi_link(self):
        self.assertContains(self.client.get("/prijava/"), "/prijava/zaboravljena-lozinka/")

    def test_link_postavlja_lozinku_jednom(self):
        self.assertRedirects(self.zatrazi("ADMIN.B@example.com"), "/prijava/zaboravljena-lozinka/poslano/")
        self.assertEqual(mail.outbox[0].to, ["admin.b@example.com"])
        link = self.link()
        forma = self.client.get(link, follow=True)
        self.assertContains(forma, "Spremi lozinku")
        adresa = forma.redirect_chain[-1][0]
        Token.objects.create(user=self.admin_b)
        r = self.client.post(adresa, {"new_password1": NOVA, "new_password2": NOVA})
        self.assertRedirects(r, "/prijava/nova-lozinka/gotovo/")
        self.admin_b.refresh_from_db()
        self.assertTrue(self.admin_b.check_password(NOVA))
        self.assertFalse(Token.objects.filter(user=self.admin_b).exists())
        # Vlasnik računa dobiva obavijest o promjeni.
        self.assertIn("promijenjena", mail.outbox[-1].subject)
        self.assertEqual(mail.outbox[-1].to, ["admin.b@example.com"])
        # Isti link više ne vrijedi.
        self.assertContains(self.client.get(link, follow=True), "nije ispravan ili je istekao")
        # Nova lozinka ne zaobilazi Google Authenticator.
        r = self.client.post("/prijava/", {"username": "admin_b", "password": NOVA})
        self.assertRedirects(r, "/prijava/kod/", fetch_redirect_response=False)

    def test_kratka_lozinka_administratora_odbijena(self):
        self.zatrazi()
        adresa = self.client.get(self.link(), follow=True).redirect_chain[-1][0]
        r = self.client.post(adresa, {"new_password1": "kratka-12", "new_password2": "kratka-12"})
        self.assertEqual(r.status_code, 200)
        self.admin_b.refresh_from_db()
        self.assertTrue(self.admin_b.check_password("lozinka-123"))

    def test_isti_odgovor_za_nepoznatu_adresu_i_suvlasnika(self):
        self.ana.email = "ana@example.com"
        self.ana.save()
        for adresa in ("nitko@example.com", "ana@example.com"):
            self.assertRedirects(self.zatrazi(adresa), "/prijava/zaboravljena-lozinka/poslano/")
        self.assertEqual(mail.outbox, [])

    def test_neaktivni_administrator_ne_dobiva_link(self):
        self.admin_b.is_active = False
        self.admin_b.save()
        self.zatrazi()
        self.assertEqual(mail.outbox, [])

    def test_glavni_administrator_moze(self):
        Korisnik.objects.create_superuser("glavni", email="glavni@example.com", password="lozinka-123")
        self.zatrazi("glavni@example.com")
        self.assertEqual(mail.outbox[0].to, ["glavni@example.com"])

    @override_settings(RESET_LOZINKE_PO_ADRESI=3, RESET_LOZINKE_PO_IP=5)
    def test_ogranicen_broj_zahtjeva(self):
        for _ in range(5):
            self.assertRedirects(self.zatrazi(), "/prijava/zaboravljena-lozinka/poslano/")
        self.assertEqual(len(mail.outbox), 3)
        # S iste adrese ni za druge račune.
        for i in range(3):
            self.zatrazi(f"netko{i}@example.com")
        Korisnik.objects.filter(pk=self.admin_a.pk).update(email="admin.a@example.com")
        self.zatrazi("admin.a@example.com")
        self.assertEqual(len(mail.outbox), 3)
        # S druge IP adrese stiže.
        self.zatrazi("admin.a@example.com", HTTP_X_FORWARDED_FOR="8.8.8.8")
        self.assertEqual(len(mail.outbox), 4)
        self.assertFalse(Zapisnik.objects.filter(opis__contains="example.com").exists())

    def test_promjena_emaila_ponistava_link(self):
        self.zatrazi()
        link = self.link()
        self.admin_b.email = "novi@example.com"
        self.admin_b.save()
        self.assertContains(self.client.get(link, follow=True), "nije ispravan ili je istekao")


class MojRacunTest(DvijeZgrade):
    def setUp(self):
        super().setUp()
        self.admin_b.email = "stari@example.com"
        self.admin_b.save()
        self.prijava("admin_b")

    def test_promjena_emaila_trazi_lozinku_i_javlja_staroj_adresi(self):
        r = self.client.post("/racun/", {"email": "novi@example.com", "lozinka": "krivo"})
        self.assertEqual(r.status_code, 200)
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.email, "stari@example.com")
        self.assertRedirects(self.client.post("/racun/", {"email": "novi@example.com", "lozinka": "lozinka-123"}), "/racun/")
        self.admin_b.refresh_from_db()
        self.assertEqual(self.admin_b.email, "novi@example.com")
        self.assertEqual(mail.outbox[-1].to, ["stari@example.com"])

    def test_promjena_lozinke_salje_obavijest(self):
        self.client.post("/lozinka/", {"new_password1": NOVA, "new_password2": NOVA})
        self.assertEqual(mail.outbox[-1].to, ["stari@example.com"])
        self.assertIn("promijenjena", mail.outbox[-1].subject)

    def test_administratori_vide_tko_nema_email(self):
        r = self.client.get("/administratori/")
        self.assertContains(r, "stari@example.com")


class PrivremenaLozinkaTest(DvijeZgrade):
    def test_glavni_administrator_postavlja_privremenu_lozinku_administratoru_zgrade(self):
        Korisnik.objects.create_superuser("glavni", password="lozinka-123")
        self.client.login(username="glavni", password="lozinka-123")
        self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada_b.pk})
        self.assertContains(self.client.get("/administratori/"), "Privremena lozinka")
        r = self.client.post(f"/korisnici/{self.admin_b.pk}/nova-lozinka/")
        self.admin_b.refresh_from_db()
        self.assertTrue(self.admin_b.check_password(r.context["lozinka"]))
        self.assertTrue(self.admin_b.mora_promijeniti_lozinku)
