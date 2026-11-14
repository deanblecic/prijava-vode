from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from . import citac
from .tests import Osnova, slika


def odgovor(tekst, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=tekst)],
    )


def lazni_klijent(*odgovori):
    klijent = mock.MagicMock()
    klijent.beta.messages.create.side_effect = list(odgovori)
    return klijent


@override_settings(ANTHROPIC_API_KEY="test-kljuc", ANTHROPIC_MODEL="claude-opus-5-5", CITANJA_DNEVNO=3)
class CitacTest(Osnova):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.api = APIClient()
        r = self.api.post("/api/prijava/", {"korisnicko_ime": "ana", "lozinka": "lozinka-123"})
        self.api.credentials(HTTP_AUTHORIZATION="Token " + r.data["token"])

    def posalji(self, **podaci):
        return self.api.post("/api/ocitanja/procitaj/", {"fotografija": slika(), **podaci}, format="multipart")

    def test_procita_stanje(self):
        klijent = lazni_klijent(odgovor('{"stanje": "784.806", "sigurno": true}'))
        with mock.patch.object(citac, "_klijent", return_value=klijent):
            r = self.posalji(prethodno_stanje="781.885")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"stanje": "784.806", "sigurno": True})
        poziv = klijent.beta.messages.create.call_args.kwargs
        self.assertEqual(poziv["model"], "claude-opus-5-5")
        self.assertEqual(poziv["fallbacks"], "default")
        sadrzaj = poziv["messages"][0]["content"]
        self.assertEqual(sadrzaj[0]["source"]["media_type"], "image/jpeg")
        self.assertIn("781.885", sadrzaj[1]["text"])

    def test_tri_decimale_i_zarez(self):
        klijent = lazni_klijent(odgovor('{"stanje": "2565,1", "sigurno": false}'))
        with mock.patch.object(citac, "_klijent", return_value=klijent):
            r = self.posalji()
        self.assertEqual(r.data["stanje"], "2565.100")

    def test_brojilo_nije_vidljivo(self):
        klijent = lazni_klijent(odgovor('{"stanje": null, "sigurno": false}'))
        with mock.patch.object(citac, "_klijent", return_value=klijent):
            r = self.posalji()
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["stanje"])

    def test_odbijeno_ili_neispravno(self):
        klijent = lazni_klijent(odgovor("", stop_reason="refusal"), odgovor("nije json"))
        with mock.patch.object(citac, "_klijent", return_value=klijent):
            self.assertEqual(citac.procitaj(b"\xff\xd8\xff", Decimal("1")), (None, False))
            self.assertEqual(citac.procitaj(b"\xff\xd8\xff", None), (None, False))

    def test_dnevno_ogranicenje(self):
        klijent = lazni_klijent(*[odgovor('{"stanje": "1.000", "sigurno": true}')] * 4)
        with mock.patch.object(citac, "_klijent", return_value=klijent):
            kodovi = [self.posalji().status_code for _ in range(4)]
        self.assertEqual(kodovi, [200, 200, 200, 429])

    def test_bez_prijave(self):
        self.assertEqual(APIClient().post("/api/ocitanja/procitaj/", {"fotografija": slika()}).status_code, 401)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_bez_kljuca_nista_ne_salje(self):
        with mock.patch.object(citac, "_klijent") as klijent:
            r = self.posalji()
        self.assertEqual(r.status_code, 503)
        klijent.assert_not_called()
