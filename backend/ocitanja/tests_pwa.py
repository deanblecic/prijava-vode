import datetime
import json
import urllib.error
from decimal import Decimal
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from . import web_push
from .models import PushPretplata
from .servisi import predaj_ocitanje
from .tests import Osnova, trenutak
from .tests_obavijest import postavi


def pretplata_preglednika():
    """Ključevi kakve preglednik stvori pri pretplati: privatni ostaje „na mobitelu” za dešifriranje."""
    privatni = ec.generate_private_key(ec.SECP256R1())
    javni = web_push._javni_bajtovi(privatni)
    auth = web_push.b64u(b"0123456789abcdef")
    return privatni, {"endpoint": "https://web.push.apple.com/QGuQyavXutnMH", "keys": {
        "p256dh": web_push.b64u(javni), "auth": auth}}


class Odgovor:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class WebAplikacijaTest(Osnova):
    def test_aplikacija_za_iphone(self):
        odgovor = self.client.get("/app/")
        self.assertEqual(odgovor.status_code, 200)
        html = odgovor.content.decode()
        self.assertIn('rel="manifest" href="/app/manifest.webmanifest"', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('name="apple-mobile-web-app-capable" content="yes"', html)
        self.assertIn("viewport-fit=cover", html)
        self.assertIn(web_push.javni_kljuc(), html)
        # Pregled fotografije prije slanja (blob:) i kamera moraju biti dopušteni.
        self.assertIn("img-src 'self' data: blob:", odgovor["Content-Security-Policy"])
        self.assertIn("camera=(self)", odgovor["Permissions-Policy"])

    def test_manifest(self):
        odgovor = self.client.get("/app/manifest.webmanifest")
        self.assertEqual(odgovor["Content-Type"], "application/manifest+json")
        podaci = json.loads(odgovor.content)
        self.assertEqual((podaci["start_url"], podaci["scope"], podaci["display"]), ("/app/", "/app/", "standalone"))
        self.assertEqual({i["sizes"] for i in podaci["icons"]}, {"192x192", "512x512"})
        self.assertIn("maskable", {i["purpose"] for i in podaci["icons"]})
        for ikona in podaci["icons"]:
            self.assertTrue(ikona["src"].startswith("/static/app/"))

    def test_service_worker(self):
        odgovor = self.client.get("/app/sw.js")
        self.assertEqual(odgovor.status_code, 200)
        self.assertTrue(odgovor["Content-Type"].startswith("text/javascript"))
        self.assertEqual(odgovor["Cache-Control"], "no-cache")
        tijelo = odgovor.content.decode()
        self.assertIn("/static/app/app.js", tijelo)
        self.assertIn('addEventListener("push"', tijelo)
        self.assertNotIn("/api/", tijelo.split("*/", 1)[1])  # podaci se ne spremaju

    def test_suvlasnik_i_dalje_ne_ulazi_u_web_administraciju(self):
        odgovor = self.client.post("/prijava/", {"username": "ana", "password": "lozinka-123"})
        self.assertContains(odgovor, "aplikaciji za mobitel")

    def test_stranica_aplikacija_nudi_iphone(self):
        self.assertContains(self.client.get("/aplikacija/"), 'href="/app/"')


class PretplataTest(Osnova):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.ivo)
        _, self.podaci = pretplata_preglednika()

    def test_pretplata_i_odjava(self):
        odgovor = self.api.post("/api/obavijesti/pretplata/", {**self.podaci, "uredaj": "iPhone"}, format="json")
        self.assertEqual(odgovor.status_code, 201)
        p = PushPretplata.objects.get()
        self.assertEqual((p.korisnik, p.uredaj, p.auth), (self.ivo, "iPhone", self.podaci["keys"]["auth"]))
        # Ponovna pretplata istog uređaja ne stvara novi zapis.
        self.api.post("/api/obavijesti/pretplata/", self.podaci, format="json")
        self.assertEqual(PushPretplata.objects.count(), 1)
        odgovor = self.api.delete("/api/obavijesti/pretplata/", {"endpoint": self.podaci["endpoint"]}, format="json")
        self.assertEqual(odgovor.status_code, 204)
        self.assertFalse(PushPretplata.objects.exists())

    def test_isti_mobitel_prelazi_na_novog_korisnika(self):
        self.api.post("/api/obavijesti/pretplata/", self.podaci, format="json")
        druga = APIClient()
        druga.force_authenticate(self.ana)
        druga.post("/api/obavijesti/pretplata/", self.podaci, format="json")
        self.assertEqual(PushPretplata.objects.get().korisnik, self.ana)

    def test_tudu_pretplatu_ne_moze_obrisati(self):
        self.api.post("/api/obavijesti/pretplata/", self.podaci, format="json")
        druga = APIClient()
        druga.force_authenticate(self.ana)
        druga.delete("/api/obavijesti/pretplata/", {"endpoint": self.podaci["endpoint"]}, format="json")
        self.assertTrue(PushPretplata.objects.exists())

    def test_samo_https_i_samo_prijavljeni(self):
        podaci = {**self.podaci, "endpoint": "http://zlonamjerno.example/x"}
        self.assertEqual(self.api.post("/api/obavijesti/pretplata/", podaci, format="json").status_code, 400)
        self.assertEqual(APIClient().post("/api/obavijesti/pretplata/", self.podaci, format="json").status_code, 401)

    @mock.patch("urllib.request.urlopen", return_value=Odgovor())
    def test_probna_obavijest(self, urlopen):
        self.assertEqual(self.api.post("/api/obavijesti/proba/").status_code, 409)
        self.api.post("/api/obavijesti/pretplata/", self.podaci, format="json")
        odgovor = self.api.post("/api/obavijesti/proba/")
        self.assertEqual(odgovor.json(), {"uredaja": 1})
        zahtjev = urlopen.call_args[0][0]
        self.assertEqual(zahtjev.full_url, self.podaci["endpoint"])


class WebPushTest(Osnova):
    def test_sifriranje_kao_u_pregledniku(self):
        privatni, podaci = pretplata_preglednika()
        tijelo = web_push.sifriraj(b'{"naslov": "Probno"}', podaci["keys"]["p256dh"], podaci["keys"]["auth"])
        self.assertEqual(web_push.desifriraj(tijelo, privatni, podaci["keys"]["auth"]), b'{"naslov": "Probno"}')

    def test_sifriranje_rfc8291_primjer(self):
        """Primjer iz RFC 8291, dodatak A: isti ulaz mora dati isto šifrirano tijelo."""
        primatelj = ec.derive_private_key(
            int.from_bytes(web_push.iz_b64u("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"), "big"), ec.SECP256R1())
        posiljatelj = ec.derive_private_key(
            int.from_bytes(web_push.iz_b64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
        tijelo = web_push.sifriraj(
            b"When I grow up, I want to be a watermelon",
            web_push.b64u(web_push._javni_bajtovi(primatelj)), "BTBZMqHH6r4Tts7J_aSIgg",
            sol=web_push.iz_b64u("DGv6ra1nlYgDCS1FRnbzlw"), kljuc_posiljatelja=posiljatelj,
        )
        self.assertEqual(web_push.b64u(tijelo), (
            "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
            "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
        ))

    def test_vapid_potpis(self):
        zaglavlje = web_push.vapid_zaglavlje("https://web.push.apple.com/abc", sada=1_800_000_000)
        t, k = zaglavlje.removeprefix("vapid t=").split(", k=")
        self.assertEqual(k, web_push.javni_kljuc())
        glava, tijelo, potpis = t.split(".")
        tvrdnje = json.loads(web_push.iz_b64u(tijelo))
        self.assertEqual(tvrdnje["aud"], "https://web.push.apple.com")
        self.assertEqual(tvrdnje["exp"], 1_800_000_000 + 12 * 3600)
        self.assertTrue(tvrdnje["sub"].startswith("mailto:"))
        rs = web_push.iz_b64u(potpis)
        javni = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), web_push.iz_b64u(k))
        javni.verify(encode_dss_signature(int.from_bytes(rs[:32], "big"), int.from_bytes(rs[32:], "big")),
                     f"{glava}.{tijelo}".encode(), ec.ECDSA(hashes.SHA256()))

    def test_kljuc_je_stalan_i_moze_se_zadati(self):
        self.assertEqual(web_push.javni_kljuc(), web_push.javni_kljuc())
        with override_settings(VAPID_PRIVATNI_KLJUC=web_push.b64u((12345).to_bytes(32, "big"))):
            zadani = web_push.javni_kljuc()
        self.assertNotEqual(zadani, web_push.javni_kljuc())


class PushPodsjetnikTest(Osnova):
    def setUp(self):
        super().setUp()
        predaj_ocitanje(self.ana, self.v3, Decimal("110"), datum_ocitanja=trenutak(2026, 10, 15))
        _, podaci = pretplata_preglednika()
        PushPretplata.objects.create(korisnik=self.ivo, endpoint=podaci["endpoint"], **podaci["keys"])
        PushPretplata.objects.create(korisnik=self.ana, endpoint="https://fcm.googleapis.com/fcm/send/ana",
                                     **podaci["keys"])

    def pokreni(self, dan, sat=10):
        with mock.patch("django.utils.timezone.localtime",
                        return_value=datetime.datetime.combine(dan, datetime.time(sat, 5))):
            call_command("posalji_obavijesti")

    @mock.patch("urllib.request.urlopen", return_value=Odgovor())
    def test_podsjetnik_na_mobitel_samo_onima_koji_nisu_ocitali(self, urlopen):
        # E-mail stanarima je isključen, a obavijest na mobitel je suvlasnik uključio sam.
        postavi(self.zgrada, rok_dan=20, podsjetnik_raspored="svaki_dan", email_stanarima=False)
        self.pokreni(datetime.date(2026, 10, 18))
        self.assertEqual(urlopen.call_count, 1)
        zahtjev = urlopen.call_args[0][0]
        self.assertEqual(zahtjev.full_url, "https://web.push.apple.com/QGuQyavXutnMH")
        self.assertEqual(zahtjev.get_header("Content-encoding"), "aes128gcm")
        self.assertTrue(zahtjev.get_header("Authorization").startswith("vapid t="))
        # Isti dan se ne šalje dvaput.
        self.pokreni(datetime.date(2026, 10, 18), sat=11)
        self.assertEqual(urlopen.call_count, 1)

    def test_istekla_pretplata_se_brise(self):
        postavi(self.zgrada, podsjetnik_raspored="svaki_dan")
        greska = urllib.error.HTTPError("https://web.push.apple.com/x", 410, "Gone", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=greska):
            self.pokreni(datetime.date(2026, 10, 18))
        self.assertFalse(PushPretplata.objects.filter(korisnik=self.ivo).exists())
        self.assertTrue(PushPretplata.objects.filter(korisnik=self.ana).exists())

    def test_greska_push_servisa_ne_rusi_slanje(self):
        postavi(self.zgrada, podsjetnik_raspored="svaki_dan")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("nema mreže")):
            self.pokreni(datetime.date(2026, 10, 18))
        self.assertEqual(PushPretplata.objects.count(), 2)
