import datetime
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .models import AdministratorZgrade, Korisnik, KorisnikStan, Ocitanje, Stan, Vodomjer, Zgrada
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
        self.zgrada = Zgrada.objects.create(
            oznaka="RI-ALB-2", ulica="Moše Albaharija", kucni_broj="2", postanski_broj="51000", grad="Rijeka"
        )
        self.ana = Korisnik.objects.create_user("ana", password="lozinka-123", first_name="Ana", last_name="Horvat")
        self.ivo = Korisnik.objects.create_user("ivo", password="lozinka-123", first_name="Ivo", last_name="Ivić")
        self.stan3 = Stan.objects.create(zgrada=self.zgrada, broj_stana="3")
        self.stan4 = Stan.objects.create(zgrada=self.zgrada, broj_stana="4")
        KorisnikStan.objects.create(korisnik=self.ana, stan=self.stan3, od_datuma=datetime.date(2020, 1, 1))
        KorisnikStan.objects.create(korisnik=self.ivo, stan=self.stan4, od_datuma=datetime.date(2020, 1, 1))
        self.v3 = Vodomjer.objects.create(stan=self.stan3, pocetno_stanje=Decimal("100.000"))
        self.v4 = Vodomjer.objects.create(stan=self.stan4, pocetno_stanje=Decimal("50.000"))

    def administrator(self, username="dean", zgrada=None, **podaci):
        korisnik = Korisnik.objects.create_user(username, password="lozinka-123", **podaci)
        AdministratorZgrade.objects.create(korisnik=korisnik, zgrada=zgrada or self.zgrada)
        return korisnik


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


class UpravljanjeTest(Osnova):
    def setUp(self):
        super().setUp()
        self.admin = self.administrator()
        self.mjesec = timezone.localdate().replace(day=1)
        self.o = predaj_ocitanje(self.ana, self.v3, "105")

    def test_suvlasnik_ne_vidi_upravljanje(self):
        self.client.login(username="ana", password="lozinka-123")
        self.assertEqual(self.client.get("/").status_code, 403)

    def test_neprijavljen_ide_na_prijavu(self):
        self.assertRedirects(self.client.get("/"), "/prijava/?next=/")

    def test_pregled_prikazuje_sve_stanove(self):
        self.client.login(username="dean", password="lozinka-123")
        r = self.client.get("/")
        self.assertContains(r, "1 / 2")
        self.assertContains(r, "Ana Horvat")
        self.assertContains(r, "Nije predano")

    def test_potvrda_i_ispravak(self):
        self.client.login(username="dean", password="lozinka-123")
        self.client.post(f"/ocitanje/{self.o.pk}/", {"akcija": "ispravi", "novo_stanje": "104", "napomena": ""})
        self.o.refresh_from_db()
        self.assertEqual(self.o.razlika, Decimal("4"))
        self.client.post(f"/ocitanje/{self.o.pk}/", {"akcija": "potvrdi"})
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, Ocitanje.Status.POTVRDENO)

    def test_ispravak_uskladjuje_sljedeci_mjesec(self):
        rujan = predaj_ocitanje(self.ana, self.v3, "103", datum_ocitanja=trenutak(2020, 9))
        listopad = predaj_ocitanje(self.ana, self.v3, "106", datum_ocitanja=trenutak(2020, 10))
        self.client.login(username="dean", password="lozinka-123")
        self.client.post(f"/ocitanje/{rujan.pk}/", {"akcija": "ispravi", "novo_stanje": "102", "napomena": ""})
        listopad.refresh_from_db()
        self.assertEqual(listopad.prethodno_stanje, Decimal("102"))
        self.assertEqual(listopad.razlika, Decimal("4"))

    def test_promjena_vlasnika_s_novim_korisnikom(self):
        self.client.login(username="dean", password="lozinka-123")
        r = self.client.post(f"/stan/{self.stan3.pk}/promjena-vlasnika/", {
            "od_datuma": timezone.localdate().isoformat(), "ime": "Marko", "prezime": "Marić",
            "korisnicko_ime": "marko", "lozinka": "Sigurna-lozinka-9", "deaktiviraj_stare": "on",
        })
        self.assertRedirects(r, f"/stan/{self.stan3.pk}/")
        marko = Korisnik.objects.get(username="marko")
        self.assertEqual(list(marko.aktivni_stanovi()), [self.stan3])
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.is_active)

    def test_rucni_unos(self):
        self.client.login(username="dean", password="lozinka-123")
        r = self.client.post(f"/stan/{self.stan4.pk}/", {"novo_stanje": "58", "datum_ocitanja": timezone.localdate().isoformat()})
        self.assertEqual(r.status_code, 302)
        o = Ocitanje.objects.get(vodomjer=self.v4)
        self.assertEqual(o.razlika, Decimal("8"))

    def test_izvoz_excel(self):
        from openpyxl import load_workbook

        self.client.login(username="dean", password="lozinka-123")
        r = self.client.get(f"/izvoz/?mjesec={self.mjesec:%Y-%m}")
        self.assertEqual(r.status_code, 200)
        list_ = load_workbook(BytesIO(r.content)).active
        self.assertEqual(list_["A2"].value, "3")
        self.assertEqual(list_["B2"].value, "Ana Horvat")
        self.assertEqual(list_["F2"].value, 5)
        self.assertEqual(list_["G3"].value, "Nije predano")


class FotografijaTest(Osnova):
    def setUp(self):
        super().setUp()
        self.administrator()
        self.o = predaj_ocitanje(self.ana, self.v3, "105", fotografija=slika())

    def test_samo_administrator_vidi_fotografiju(self):
        url = self.o.fotografija.url
        self.client.login(username="ana", password="lozinka-123")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.login(username="dean", password="lozinka-123")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")

    def test_izlazak_iz_mape_nije_moguc(self):
        self.client.login(username="dean", password="lozinka-123")
        self.assertEqual(self.client.get("/media/../../config/settings.py").status_code, 404)


class AplikacijaTest(TestCase):
    def test_bez_apk_datoteke(self):
        with override_settings(APK_DATOTEKA=Path(MEDIA) / "nema.apk"):
            self.assertContains(self.client.get("/aplikacija/"), "još nije postavljena")
            self.assertEqual(self.client.get("/aplikacija/ocitanje-vode.apk").status_code, 404)

    def test_verzija_u_api_ja(self):
        apk = Path(MEDIA) / "verzija" / "ocitanje-vode.apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        ana = Korisnik.objects.create_user("ana", password="lozinka-123")
        api = APIClient()
        api.force_authenticate(ana)
        with override_settings(APK_DATOTEKA=apk, APK_VERZIJA=apk.with_name("verzija.txt")):
            self.assertEqual(api.get("/api/ja/").data["aplikacija"], {"verzija": None})
            apk.with_name("verzija.txt").write_text("17\n")
            self.assertEqual(api.get("/api/ja/").data["aplikacija"], {"verzija": 17})

    def test_preuzimanje_bez_prijave(self):
        apk = Path(MEDIA) / "ocitanje-vode.apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_bytes(b"PK" + b"0" * 2000)
        with override_settings(APK_DATOTEKA=apk):
            self.assertContains(self.client.get("/aplikacija/"), "Preuzmi aplikaciju")
            r = self.client.get("/aplikacija/ocitanje-vode.apk")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r["Content-Type"], "application/vnd.android.package-archive")
