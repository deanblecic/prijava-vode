import datetime
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from rest_framework.test import APIClient

from .models import Ocitanje, PoslanaObavijest, Postavke, Zapisnik
from .rokovi import dani_slanja, datum_roka
from .servisi import GreskaOcitanja, predaj_ocitanje
from .tests import Osnova, trenutak


def podaci_postavki(**izmjene):
    """Cijela forma Rokovi i podsjetnici sa zadanim vrijednostima."""
    podaci = {
        "rok_dan": 0, "nakon_roka": "oznaci",
        "podsjetnik_raspored": "od_dana", "dan_ocitanja": 26, "podsjetnik_broj_dana": 3, "sat_podsjetnika": 9,
        "email_stanarima": "on",
        "obavijest_raspored": "rok", "obavijest_od_dana": 25, "obavijest_broj_dana": 3, "sat_obavijesti": 20,
        "email_obavijesti": "",
    }
    podaci.update(izmjene)
    return {k: v for k, v in podaci.items() if v is not None}


def postavi(zgrada, **polja):
    Postavke.objects.update_or_create(zgrada=zgrada, defaults=polja)


class RasporedTest(Osnova):
    def test_gotovi_rasporedi(self):
        self.assertEqual(dani_slanja("prvi", 20), [1])
        self.assertEqual(dani_slanja("prvi_rok", 20), [1, 20])
        self.assertEqual(dani_slanja("rok", 31), [31])
        self.assertEqual(dani_slanja("predzadnji_rok", 30), [29, 30])
        self.assertEqual(dani_slanja("svaki_dan", 5), [1, 2, 3, 4, 5])
        self.assertEqual(dani_slanja("od_dana", 20, od_dana=18), [18, 19, 20])
        self.assertEqual(dani_slanja("prije_roka", 20, broj_dana=3), [18, 19, 20])

    def test_odabrani_dani_i_dani_prije_roka(self):
        self.assertEqual(dani_slanja("prilagodeno", 20, dani=[1, 10, -1, 0, 25]), [1, 10, 19, 20])

    def test_rok_zadnji_dan_u_mjesecu(self):
        postavke = Postavke.ucitaj(self.zgrada)
        self.assertEqual(datum_roka(postavke, datetime.date(2026, 2, 1)), datetime.date(2026, 2, 28))
        postavke.rok_dan = 15
        self.assertEqual(datum_roka(postavke, datetime.date(2026, 2, 1)), datetime.date(2026, 2, 15))


class ObavijestiTest(Osnova):
    def setUp(self):
        super().setUp()
        self.administrator(email="dean@example.com")
        self.ivo.email = "ivo@example.com"
        self.ivo.save()
        predaj_ocitanje(self.ana, self.v3, Decimal("110"), datum_ocitanja=trenutak(2026, 10, 15))

    def pokreni(self, dan, sat=20, minuta=5, **opcije):
        trenutak_ = datetime.datetime.combine(dan, datetime.time(sat, minuta))
        with mock.patch("django.utils.timezone.localtime", return_value=trenutak_):
            call_command("posalji_obavijesti", **opcije)

    def poruke(self, kome):
        return [p for p in mail.outbox if kome in p.to]

    def test_zadano_kao_prije_zadnji_dan_u_20_h(self):
        self.pokreni(datetime.date(2026, 10, 31))
        admin = self.poruke("dean@example.com")
        self.assertEqual(len(admin), 1)
        self.assertIn("stan 4: Ivo Ivić", admin[0].body)
        self.assertNotIn("stan 3", admin[0].body)

    def test_ostalim_danima_i_prije_sata_ne_salje(self):
        self.pokreni(datetime.date(2026, 10, 30))
        self.pokreni(datetime.date(2026, 10, 31), sat=19)
        self.assertEqual(self.poruke("dean@example.com"), [])

    def test_ista_poruka_samo_jednom_dnevno(self):
        for minuta in (0, 15, 30):
            self.pokreni(datetime.date(2026, 10, 31), sat=20, minuta=minuta)
        self.pokreni(datetime.date(2026, 10, 31), sat=22)
        self.assertEqual(len(self.poruke("dean@example.com")), 1)
        self.assertEqual(len(self.poruke("ivo@example.com")), 1)
        self.assertTrue(PoslanaObavijest.objects.filter(vrsta="neocitani", datum=datetime.date(2026, 10, 31)).exists())

    def test_kasniji_pokret_nadoknadi_propusteni_termin(self):
        # Cron nije radio u 20 h; poruka ide prvi sljedeći put istog dana.
        self.pokreni(datetime.date(2026, 10, 31), sat=23, minuta=45)
        self.assertEqual(len(self.poruke("dean@example.com")), 1)

    def test_rok_i_rasporedi_po_zgradi(self):
        postavi(self.zgrada, rok_dan=20, podsjetnik_raspored="prvi_rok", sat_podsjetnika=8,
                obavijest_raspored="predzadnji_rok", sat_obavijesti=18)
        self.pokreni(datetime.date(2026, 10, 1), sat=8)
        self.assertEqual(len(self.poruke("ivo@example.com")), 1)
        self.assertIn("20.10.2026.", self.poruke("ivo@example.com")[0].subject)
        self.pokreni(datetime.date(2026, 10, 19), sat=18)
        self.pokreni(datetime.date(2026, 10, 20), sat=18)
        self.assertEqual(len(self.poruke("dean@example.com")), 2)
        self.assertEqual(len(self.poruke("ivo@example.com")), 2)
        # Iza roka više ništa.
        self.pokreni(datetime.date(2026, 10, 31), sat=21)
        self.assertEqual(len(mail.outbox), 4)

    def test_podsjetnik_samo_onima_koji_nisu_ocitali(self):
        self.ana.email = "ana@example.com"
        self.ana.save()
        postavi(self.zgrada, podsjetnik_raspored="svaki_dan")
        self.pokreni(datetime.date(2026, 10, 20), sat=10)
        self.assertEqual(self.poruke("ana@example.com"), [])
        self.assertIn("stana 4", self.poruke("ivo@example.com")[0].body)

    def test_podsjetnik_bez_emaila_suvlasnicima(self):
        postavi(self.zgrada, podsjetnik_raspored="svaki_dan", email_stanarima=False)
        self.pokreni(datetime.date(2026, 10, 20), sat=10)
        self.assertEqual(self.poruke("ivo@example.com"), [])

    def test_ne_salje_kad_su_svi_ocitani(self):
        predaj_ocitanje(self.ivo, self.v4, Decimal("60"), datum_ocitanja=trenutak(2026, 10, 27))
        self.pokreni(datetime.date(2026, 10, 31))
        self.assertEqual(mail.outbox, [])

    def test_neuspjelo_slanje_pokusava_ponovno(self):
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=OSError("smtp")):
            self.pokreni(datetime.date(2026, 10, 31))
        self.assertFalse(PoslanaObavijest.objects.exists())
        self.pokreni(datetime.date(2026, 10, 31), minuta=20)
        self.assertEqual(len(self.poruke("dean@example.com")), 1)

    def test_postavljeni_primatelj_i_odmah(self):
        postavi(self.zgrada, email_obavijesti="upravitelj@example.com")
        self.pokreni(datetime.date(2026, 10, 15), odmah=True)
        self.assertEqual(len(self.poruke("upravitelj@example.com")), 1)
        # Proba ne zauzima današnji termin.
        self.assertFalse(PoslanaObavijest.objects.exists())

    def test_staro_ime_naredbe_radi(self):
        trenutak_ = datetime.datetime(2026, 10, 31, 20, 5)
        with mock.patch("django.utils.timezone.localtime", return_value=trenutak_):
            call_command("obavijest_neocitani")
        self.assertEqual(len(self.poruke("dean@example.com")), 1)


class RokPredajeTest(Osnova):
    def predaj(self, dan):
        with mock.patch("django.utils.timezone.localdate", return_value=dan):
            return predaj_ocitanje(self.ana, self.v3, Decimal("110"), samo_vlasnik=True,
                                   datum_ocitanja=trenutak(dan.year, dan.month, dan.day))

    def test_nakon_roka_oznaceno_kao_zakasnjelo(self):
        postavi(self.zgrada, rok_dan=20)
        self.assertFalse(self.predaj(datetime.date(2026, 10, 20)).zakasnjelo)
        self.assertTrue(self.predaj(datetime.date(2026, 10, 21)).zakasnjelo)

    def test_nakon_roka_zatvoreno(self):
        postavi(self.zgrada, rok_dan=20, nakon_roka="zatvori")
        with self.assertRaises(GreskaOcitanja) as greska:
            self.predaj(datetime.date(2026, 10, 21))
        self.assertEqual(greska.exception.kod, "rok_istekao")
        self.assertIn("20.10.2026.", greska.exception.poruka)
        self.assertFalse(Ocitanje.objects.exists())

    def test_administrator_na_webu_unosi_i_nakon_roka(self):
        postavi(self.zgrada, rok_dan=20, nakon_roka="zatvori")
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2026, 10, 25)):
            ocitanje = predaj_ocitanje(self.administrator(), self.v3, Decimal("110"),
                                       datum_ocitanja=trenutak(2026, 10, 25))
        self.assertFalse(ocitanje.zakasnjelo)


class PostavkeTest(Osnova):
    def setUp(self):
        super().setUp()
        self.administrator()
        self.client.login(username="dean", password="lozinka-123")

    def test_administrator_mijenja_postavke_a_api_ih_vraca(self):
        odgovor = self.client.post("/postavke/", podaci_postavki(
            rok_dan=20, podsjetnik_raspored="prilagodeno", podsjetnik_dani=["1", "10", "-1"], sat_podsjetnika=11,
            obavijest_raspored="predzadnji_rok", sat_obavijesti=7, email_obavijesti="a@example.com, b@example.com",
        ))
        self.assertEqual(odgovor.status_code, 302)
        postavke = Postavke.ucitaj(self.zgrada)
        self.assertEqual((postavke.rok_dan, postavke.podsjetnik_dani, postavke.sat_obavijesti), (20, [1, 10, -1], 7))
        self.assertTrue(Zapisnik.objects.filter(radnja=Zapisnik.Radnja.POSTAVKE, zgrada=self.zgrada).exists())

        api = APIClient()
        api.force_authenticate(self.ana)
        podsjetnik = api.get("/api/ja/").json()["podsjetnik"]
        self.assertEqual(podsjetnik["dani"], [1, 10, 19])
        self.assertEqual((podsjetnik["dan"], podsjetnik["sat"]), (1, 11))
        self.assertTrue(podsjetnik["rok"].endswith("-20"))

        stranica = self.client.get("/postavke/")
        self.assertContains(stranica, "Krajnji rok")

    def test_neispravne_vrijednosti(self):
        odgovor = self.client.post("/postavke/", podaci_postavki(
            sat_podsjetnika=24, email_obavijesti="nije", rok_dan=15, dan_ocitanja=20,
            obavijest_raspored="prilagodeno",
        ))
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(set(odgovor.context["forma"].errors),
                         {"sat_podsjetnika", "email_obavijesti", "dan_ocitanja", "obavijest_dani"})

    def test_suvlasnik_ne_vidi_postavke(self):
        self.client.logout()
        self.client.login(username="ana", password="lozinka-123")
        self.assertEqual(self.client.get("/postavke/").status_code, 403)
