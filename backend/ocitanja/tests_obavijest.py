import datetime
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from rest_framework.test import APIClient

from .models import Postavke
from .servisi import predaj_ocitanje
from .tests import Osnova, trenutak


class ObavijestNeocitaniTest(Osnova):
    def setUp(self):
        super().setUp()
        self.administrator(email="dean@example.com")
        predaj_ocitanje(self.ana, self.v3, Decimal("110"), datum_ocitanja=trenutak(2026, 10, 26))

    def pokreni(self, dan, sat=20, **opcije):
        trenutak = datetime.datetime.combine(dan, datetime.time(sat, 5))
        with mock.patch("django.utils.timezone.localtime", return_value=trenutak):
            call_command("obavijest_neocitani", **opcije)

    def test_zadnji_dan_salje_popis_neocitanih(self):
        self.pokreni(datetime.date(2026, 10, 31))
        self.assertEqual(len(mail.outbox), 1)
        poruka = mail.outbox[0]
        self.assertEqual(poruka.to, ["dean@example.com"])
        self.assertIn("stan 4: Ivo Ivić", poruka.body)
        self.assertNotIn("stan 3", poruka.body)

    def test_ostalim_danima_i_satima_ne_salje(self):
        self.pokreni(datetime.date(2026, 10, 30))
        self.pokreni(datetime.date(2026, 10, 31), sat=19)
        self.assertEqual(mail.outbox, [])

    def test_ne_salje_kad_su_svi_ocitani(self):
        predaj_ocitanje(self.ivo, self.v4, Decimal("60"), datum_ocitanja=trenutak(2026, 10, 27))
        self.pokreni(datetime.date(2026, 10, 31))
        self.assertEqual(mail.outbox, [])

    def test_postavljeni_primatelj_i_odmah(self):
        Postavke.objects.update_or_create(zgrada=self.zgrada, defaults={"email_obavijesti": "upravitelj@example.com"})
        self.pokreni(datetime.date(2026, 10, 15), odmah=True)
        self.assertEqual(mail.outbox[0].to, ["upravitelj@example.com"])


class PostavkeTest(Osnova):
    def test_administrator_mijenja_sat_a_api_ga_vraca(self):
        self.administrator()
        self.client.login(username="dean", password="lozinka-123")
        odgovor = self.client.post("/postavke/", {
            "dan_ocitanja": 25, "sat_podsjetnika": 11, "email_obavijesti": "a@example.com, b@example.com",
        })
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(Postavke.ucitaj(self.zgrada).sat_podsjetnika, 11)

        api = APIClient()
        api.force_authenticate(self.ana)
        self.assertEqual(api.get("/api/ja/").json()["podsjetnik"], {"dan": 25, "sat": 11})

    def test_neispravan_sat_i_email(self):
        self.administrator()
        self.client.login(username="dean", password="lozinka-123")
        odgovor = self.client.post("/postavke/", {"dan_ocitanja": 31, "sat_podsjetnika": 24, "email_obavijesti": "nije"})
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(set(odgovor.context["forma"].errors), {"dan_ocitanja", "sat_podsjetnika", "email_obavijesti"})

    def test_suvlasnik_ne_vidi_postavke(self):
        self.client.login(username="ana", password="lozinka-123")
        self.assertEqual(self.client.get("/postavke/").status_code, 403)
