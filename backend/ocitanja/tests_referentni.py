"""Referentni dan očitanja: crveni prikaz na pregledu, povijest po mjesecu i početak podsjetnika."""
import datetime

from django.utils import timezone

from .models import Postavke, ReferentniDan
from .rokovi import dani_podsjetnika, dani_slanja, referentni_dan
from .servisi import predaj_ocitanje
from .tests import Osnova, trenutak
from .tests_obavijest import podaci_postavki


class ReferentniDanTest(Osnova):
    def setUp(self):
        super().setUp()
        self.administrator()
        self.client.login(username="dean", password="lozinka-123")
        self.mjesec = timezone.localdate().replace(day=1)

    def test_spremanje_u_postavkama_pamti_dan_od_ovog_mjeseca(self):
        self.assertEqual(self.client.post("/postavke/", podaci_postavki(referentni_dan=20)).status_code, 302)
        self.assertEqual(Postavke.ucitaj(self.zgrada).referentni_dan, 20)
        self.assertEqual(referentni_dan(self.zgrada.pk, self.mjesec), 20)
        prosli = (self.mjesec - datetime.timedelta(days=1)).replace(day=1)
        self.assertIsNone(referentni_dan(self.zgrada.pk, prosli))
        self.assertContains(self.client.get("/postavke/"), "Referentni dan očitanja")

        # Ponovna promjena u istom mjesecu prepravlja isti zapis; brisanje dana vraća "nije postavljen".
        self.client.post("/postavke/", podaci_postavki(referentni_dan=22))
        self.client.post("/postavke/", podaci_postavki(referentni_dan=""))
        self.assertEqual(ReferentniDan.objects.count(), 1)
        self.assertIsNone(referentni_dan(self.zgrada.pk, self.mjesec))

    def test_ne_moze_biti_iza_roka(self):
        odgovor = self.client.post("/postavke/", podaci_postavki(rok_dan=15, referentni_dan=20))
        self.assertEqual(odgovor.status_code, 200)
        self.assertIn("referentni_dan", odgovor.context["forma"].errors)
        self.assertEqual(self.client.post("/postavke/", podaci_postavki(rok_dan=0, referentni_dan=31)).status_code, 302)

    def test_dan_iza_kraja_kraceg_mjeseca_je_zadnji_dan(self):
        ReferentniDan.objects.create(zgrada=self.zgrada, od_mjeseca=datetime.date(2026, 1, 1), dan=31)
        self.assertEqual(referentni_dan(self.zgrada.pk, datetime.date(2026, 2, 1)), 28)
        self.assertEqual(referentni_dan(self.zgrada.pk, datetime.date(2026, 4, 1)), 30)
        self.assertEqual(referentni_dan(self.zgrada.pk, datetime.date(2026, 5, 1)), 31)

    def test_pregled_crveni_ocitanja_prije_dana_koji_je_tada_vrijedio(self):
        ReferentniDan.objects.create(zgrada=self.zgrada, od_mjeseca=datetime.date(2026, 8, 1), dan=20)
        ReferentniDan.objects.create(zgrada=self.zgrada, od_mjeseca=datetime.date(2026, 10, 1), dan=10)
        predaj_ocitanje(self.ana, self.v3, "105", datum_ocitanja=trenutak(2026, 9, 15))  # prije 20.: crveno
        predaj_ocitanje(self.ivo, self.v4, "55", datum_ocitanja=trenutak(2026, 9, 20))   # na sam dan: u redu
        predaj_ocitanje(self.ana, self.v3, "110", datum_ocitanja=trenutak(2026, 10, 15))  # iza 10.: u redu
        predaj_ocitanje(self.ivo, self.v4, "60", datum_ocitanja=trenutak(2026, 10, 9))   # prije 10.: crveno

        def crveni(mjesec):
            r = self.client.get(f"/?mjesec={mjesec}")
            return {red["stan"].broj_stana for red in r.context["redovi"] if red["prerano"]}, r

        stanovi, r = crveni("2026-09")
        self.assertEqual(stanovi, {"3"})
        self.assertContains(r, 'class="prerano"', count=1)
        self.assertContains(r, "20.09.2026.")
        self.assertEqual(crveni("2026-10")[0], {"4"})

        stanovi, r = crveni("2026-07")  # prije prvog postavljanja: ništa crveno
        self.assertEqual(stanovi, set())
        self.assertNotContains(r, 'class="prerano"')


class PodsjetniciOdReferentnogDanaTest(Osnova):
    def test_raspored_pocinje_od_referentnog_dana(self):
        self.assertEqual(dani_slanja("svaki_dan", 22, pocetak=20), [20, 21, 22])
        self.assertEqual(dani_slanja("prvi_rok", 25, pocetak=20), [20, 25])
        self.assertEqual(dani_slanja("od_dana", 25, od_dana=15, pocetak=20), [20, 21, 22, 23, 24, 25])
        self.assertEqual(dani_slanja("prilagodeno", 25, dani=[1, 21, 0], pocetak=20), [21, 25])

    def test_podsjetnici_zgrade_krecu_od_referentnog_dana(self):
        mjesec = datetime.date(2026, 11, 1)
        postavke = Postavke.ucitaj(self.zgrada)  # zadano: svaki dan od 26. do zadnjeg u mjesecu
        ReferentniDan.objects.all().delete()
        self.assertEqual(dani_podsjetnika(postavke, mjesec), [26, 27, 28, 29, 30])
        ReferentniDan.objects.create(zgrada=self.zgrada, od_mjeseca=mjesec, dan=27)
        self.assertEqual(dani_podsjetnika(postavke, mjesec), [27, 28, 29, 30])
        ReferentniDan.objects.filter(zgrada=self.zgrada).update(dan=20)
        self.assertEqual(dani_podsjetnika(postavke, mjesec)[0], 20)
