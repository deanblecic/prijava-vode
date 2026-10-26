import datetime
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .models import Korisnik, KorisnikStan, Ocitanje, Stan, Vodomjer
from .servisi import GreskaOcitanja, predaj_ocitanje, promijeni_vlasnika

MEDIA = tempfile.mkdtemp()


def trenutak(godina, mjesec, dan=5):
    return timezone.make_aware(datetime.datetime(godina, mjesec, dan, 10, 0))


def slika():
    buf = BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "JPEG")
    return SimpleUploadedFile("vodomjer.jpg", buf.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class Osnova(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.ana = Korisnik.objects.create_user("ana", password="lozinka-123", first_name="Ana", last_name="Horvat")
        self.ivo = Korisnik.objects.create_user("ivo", password="lozinka-123", first_name="Ivo", last_name="Ivić")
        self.stan3 = Stan.objects.create(broj_stana="3")
        self.stan4 = Stan.objects.create(broj_stana="4")
        KorisnikStan.objects.create(korisnik=self.ana, stan=self.stan3, od_datuma=datetime.date(2020, 1, 1))
        KorisnikStan.objects.create(korisnik=self.ivo, stan=self.stan4, od_datuma=datetime.date(2020, 1, 1))
        self.v3 = Vodomjer.objects.create(stan=self.stan3, pocetno_stanje=Decimal("100.000"))
        self.v4 = Vodomjer.objects.create(stan=self.stan4, pocetno_stanje=Decimal("50.000"))


class PredajaTest(Osnova):
    def test_prvo_ocitanje_koristi_pocetno_stanje(self):
        o = predaj_ocitanje(self.ana, self.v3, "105.5", datum_ocitanja=trenutak(2026, 9))
        self.assertEqual(o.prethodno_stanje, Decimal("100"))
        self.assertEqual(o.razlika, Decimal("5.5"))
        self.assertEqual(o.razdoblje, datetime.date(2026, 9, 1))

    def test_drugo_ocitanje_koristi_prethodni_mjesec(self):
        predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 9))
        o = predaj_ocitanje(self.ana, self.v3, "112.25", datum_ocitanja=trenutak(2026, 10))
        self.assertEqual(o.prethodno_stanje, Decimal("105"))
        self.assertEqual(o.razlika, Decimal("7.25"))

    def test_ponovna_predaja_istog_mjeseca_ispravlja(self):
        predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 9, 3))
        predaj_ocitanje(self.ana, self.v3, "106", datum_ocitanja=trenutak(2026, 9, 4))
        self.assertEqual(Ocitanje.objects.count(), 1)
        self.assertEqual(Ocitanje.objects.get().novo_stanje, Decimal("106"))

    def test_potvrdeno_se_ne_moze_mijenjati(self):
        o = predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 9))
        o.status = Ocitanje.Status.POTVRDENO
        o.save()
        with self.assertRaises(GreskaOcitanja) as g:
            predaj_ocitanje(self.ana, self.v3, "106", datum_ocitanja=trenutak(2026, 9))
        self.assertEqual(g.exception.kod, "vec_potvrdeno")

    def test_manje_od_prethodnog_trazi_potvrdu(self):
        with self.assertRaises(GreskaOcitanja) as g:
            predaj_ocitanje(self.ana, self.v3, "99", datum_ocitanja=trenutak(2026, 9))
        self.assertEqual(g.exception.kod, "manje_od_prethodnog")
        o = predaj_ocitanje(self.ana, self.v3, "99", datum_ocitanja=trenutak(2026, 9), potvrdi_manje=True)
        self.assertTrue(o.za_provjeru)

    def test_odbijeno_se_preskace_za_prethodno_stanje(self):
        o = predaj_ocitanje(self.ana, self.v3, "500", datum_ocitanja=trenutak(2026, 9))
        o.status = Ocitanje.Status.ODBIJENO
        o.save()
        novo = predaj_ocitanje(self.ana, self.v3, "104", datum_ocitanja=trenutak(2026, 10))
        self.assertEqual(novo.prethodno_stanje, Decimal("100"))

    def test_velika_razlika_oznacena_za_provjeru(self):
        predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 8))
        predaj_ocitanje(self.ana, self.v3, "110", datum_ocitanja=trenutak(2026, 9))
        o = predaj_ocitanje(self.ana, self.v3, "140", datum_ocitanja=trenutak(2026, 10))
        self.assertTrue(o.za_provjeru)
        self.assertIn("prosjeka", o.razlog_provjere)

    def test_ocr_ispravak_se_biljezi(self):
        o = predaj_ocitanje(self.ana, self.v3, "105", ocr_vrijednost=Decimal("185"), datum_ocitanja=trenutak(2026, 9))
        self.assertTrue(o.rucno_ispravljeno)

    def test_tudji_vodomjer_zabranjen(self):
        with self.assertRaises(GreskaOcitanja) as g:
            predaj_ocitanje(self.ana, self.v4, "60")
        self.assertEqual(g.exception.kod, "nema_prava")

    def test_bivsi_suvlasnik_nema_pravo(self):
        KorisnikStan.objects.filter(korisnik=self.ana).update(do_datuma=datetime.date(2021, 1, 1))
        with self.assertRaises(GreskaOcitanja):
            predaj_ocitanje(self.ana, self.v3, "105")

    def test_jedan_aktivni_vodomjer_po_stanu(self):
        with self.assertRaises(IntegrityError):
            Vodomjer.objects.create(stan=self.stan3)


class PromjenaVlasnikaTest(Osnova):
    def test_prodaja_stana(self):
        predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 9))
        marko = Korisnik.objects.create_user("marko", password="lozinka-123")
        promijeni_vlasnika(self.stan3, [marko], timezone.localdate())
        self.assertFalse(self.ana.aktivni_stanovi().exists())
        self.assertEqual(list(marko.aktivni_stanovi()), [self.stan3])
        with self.assertRaises(GreskaOcitanja):
            predaj_ocitanje(self.ana, self.v3, "110")
        o = predaj_ocitanje(marko, self.v3, "110")
        self.assertEqual(o.prethodno_stanje, Decimal("105"))


class ApiTest(Osnova):
    def setUp(self):
        super().setUp()
        self.klijent = APIClient()

    def prijavi(self, ime="ana"):
        r = self.klijent.post("/api/prijava/", {"korisnicko_ime": ime, "lozinka": "lozinka-123"})
        self.assertEqual(r.status_code, 200)
        self.klijent.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])

    def test_pogresna_lozinka(self):
        r = self.klijent.post("/api/prijava/", {"korisnicko_ime": "ana", "lozinka": "kriva"})
        self.assertEqual(r.status_code, 400)

    def test_bez_prijave_nema_pristupa(self):
        self.assertEqual(self.klijent.get("/api/ja/").status_code, 401)

    def test_ja_vraca_samo_svoj_stan(self):
        self.prijavi()
        r = self.klijent.get("/api/ja/")
        self.assertEqual([s["broj_stana"] for s in r.data["stanovi"]], ["3"])
        self.assertEqual(r.data["stanovi"][0]["vodomjeri"][0]["prethodno_stanje"], "100.000")

    def test_predaja_s_fotografijom(self):
        self.prijavi()
        r = self.klijent.post(
            "/api/ocitanja/",
            {"vodomjer": self.v3.id, "novo_stanje": "107.125", "ocr_vrijednost": "107.125", "fotografija": slika()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["razlika"], "7.125")
        self.assertEqual(r.data["ime_prezime"], "Ana Horvat")
        self.assertEqual(r.data["broj_stana"], "3")
        self.assertIn("stan-3", Ocitanje.objects.get().fotografija.name)

    def test_predaja_za_tudji_stan(self):
        self.prijavi()
        r = self.klijent.post("/api/ocitanja/", {"vodomjer": self.v4.id, "novo_stanje": "60"})
        self.assertEqual(r.status_code, 403)

    def test_manje_od_prethodnog_vraca_409(self):
        self.prijavi()
        r = self.klijent.post("/api/ocitanja/", {"vodomjer": self.v3.id, "novo_stanje": "90"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["kod"], "manje_od_prethodnog")

    def test_popis_samo_svojih_ocitanja(self):
        predaj_ocitanje(self.ana, self.v3, "105")
        predaj_ocitanje(self.ivo, self.v4, "55")
        self.prijavi("ivo")
        r = self.klijent.get("/api/ocitanja/")
        self.assertEqual([o["broj_stana"] for o in r.data], ["4"])
