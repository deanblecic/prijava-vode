import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from openpyxl import Workbook
from rest_framework.test import APIClient

from .models import AdministratorZgrade, Korisnik, KorisnikStan, Stan, Vodomjer, Zgrada, kljuc_adrese
from .servisi import predaj_ocitanje
from .tests import Osnova, slika


class DvijeZgrade(Osnova):
    """Zgrada A (iz Osnove, stanovi 3 i 4) i zgrada B sa stanom 3 i suvlasnicom Marijom."""

    def setUp(self):
        super().setUp()
        self.zgrada_b = Zgrada.objects.create(
            oznaka="ZG-ILI-10", ulica="Ilica", kucni_broj="10", postanski_broj="10000", grad="Zagreb"
        )
        self.marija = Korisnik.objects.create_user(
            "marija", password="lozinka-123", first_name="Marija", last_name="Babić"
        )
        self.b3 = Stan.objects.create(zgrada=self.zgrada_b, broj_stana="3")
        KorisnikStan.objects.create(korisnik=self.marija, stan=self.b3, od_datuma=datetime.date(2020, 1, 1))
        self.vb3 = Vodomjer.objects.create(stan=self.b3, pocetno_stanje=Decimal("10"))
        self.admin_a = self.administrator("admin_a")
        self.admin_b = self.administrator("admin_b", zgrada=self.zgrada_b)
        self.o_a = predaj_ocitanje(self.ana, self.v3, "105", fotografija=slika())
        self.o_b = predaj_ocitanje(self.marija, self.vb3, "12", fotografija=slika())

    def prijava(self, ime):
        self.assertTrue(self.client.login(username=ime, password="lozinka-123"))


class OdvajanjeZgradaTest(DvijeZgrade):
    def test_administrator_vidi_samo_svoju_zgradu(self):
        self.prijava("admin_b")
        r = self.client.get("/")
        self.assertContains(r, "Marija Babić")
        self.assertNotContains(r, "Ana Horvat")
        self.assertContains(r, "1 / 1")

    def test_tudji_podaci_ne_postoje(self):
        self.prijava("admin_b")
        for url in [
            f"/stan/{self.stan3.pk}/",
            f"/stan/{self.stan3.pk}/promjena-vlasnika/",
            f"/ocitanje/{self.o_a.pk}/",
            self.o_a.fotografija.url,
        ]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.get(self.o_b.fotografija.url).status_code, 200)

    def test_potvrda_tudjeg_ocitanja_nije_moguca(self):
        self.prijava("admin_b")
        self.client.post(f"/ocitanje/{self.o_a.pk}/", {"akcija": "potvrdi"})
        self.o_a.refresh_from_db()
        self.assertEqual(self.o_a.status, "predano")

    def test_odabir_tudje_zgrade_se_ne_pamti(self):
        self.prijava("admin_b")
        self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada.pk})
        self.assertNotContains(self.client.get("/"), "Ana Horvat")

    def test_promjena_vlasnika_nudi_samo_suvlasnike_zgrade(self):
        self.prijava("admin_b")
        r = self.client.get(f"/stan/{self.b3.pk}/promjena-vlasnika/")
        self.assertEqual(list(r.context["forma"].fields["postojeci"].queryset), [self.marija])
        r = self.client.post(f"/stan/{self.b3.pk}/promjena-vlasnika/", {
            "od_datuma": "2026-10-01", "postojeci": [self.ana.pk],
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.ana.vlasnistva.filter(stan=self.b3).exists())

    def test_izvoz_samo_svoje_zgrade(self):
        from io import BytesIO

        from openpyxl import load_workbook

        self.prijava("admin_b")
        r = self.client.get(f"/izvoz/?mjesec={self.o_b.razdoblje:%Y-%m}")
        self.assertIn("ZG-ILI-10", r["Content-Disposition"])
        list_ = load_workbook(BytesIO(r.content)).active
        self.assertEqual([c.value for c in list_["B"]][1:-1], ["Marija Babić"])

    def test_postavke_po_zgradi(self):
        self.prijava("admin_b")
        self.client.post("/postavke/", {"dan_ocitanja": 20, "sat_podsjetnika": 8, "email_obavijesti": ""})
        api = APIClient()
        api.force_authenticate(self.ana)
        self.assertEqual(api.get("/api/ja/").json()["podsjetnik"], {"dan": 26, "sat": 9})
        api.force_authenticate(self.marija)
        self.assertEqual(api.get("/api/ja/").json()["podsjetnik"], {"dan": 20, "sat": 8})

    def test_administrator_ne_predaje_za_tudju_zgradu(self):
        api = APIClient()
        api.force_authenticate(self.admin_b)
        r = api.post("/api/ocitanja/", {"vodomjer": self.v4.pk, "novo_stanje": "60"})
        self.assertEqual(r.status_code, 403)
        # U aplikaciji i administrator predaje samo za svoje stanove; ručni unos za zgradu radi na webu.
        r = api.post("/api/ocitanja/", {"vodomjer": self.vb3.pk, "novo_stanje": "13"})
        self.assertEqual(r.status_code, 403)

    def test_obavijest_ide_administratorima_svake_zgrade(self):
        self.admin_a.email = "a@example.com"
        self.admin_a.save()
        self.admin_b.email = "b@example.com"
        self.admin_b.save()
        call_command("obavijest_neocitani", odmah=True)
        poruke = {tuple(p.to): p.body for p in mail.outbox}
        self.assertEqual(set(poruke), {("a@example.com",)})  # u zgradi B je sve očitano
        self.assertIn("stan 4: Ivo Ivić", poruke[("a@example.com",)])
        self.assertNotIn("Marija", poruke[("a@example.com",)])


class SuperadministratorTest(DvijeZgrade):
    def setUp(self):
        super().setUp()
        Korisnik.objects.create_superuser("dean", password="lozinka-123")

    def test_bira_zgradu(self):
        self.prijava("dean")
        self.assertRedirects(self.client.get("/"), "/zgrade/")
        r = self.client.get("/zgrade/")
        self.assertContains(r, "Moše Albaharija 2, 51000 Rijeka")
        self.assertContains(r, "Ilica 10, 10000 Zagreb")
        self.assertRedirects(self.client.post("/zgrade/odaberi/", {"zgrada": self.zgrada_b.pk}), "/")
        r = self.client.get("/")
        self.assertContains(r, "Marija Babić")
        self.assertContains(r, f'value="{self.zgrada.pk}"')  # izbornik u zaglavlju
        self.client.post("/zgrade/odaberi/", {"zgrada": ""})
        self.assertRedirects(self.client.get("/"), "/zgrade/")

    def test_vidi_sve_fotografije(self):
        self.prijava("dean")
        self.assertEqual(self.client.get(self.o_a.fotografija.url).status_code, 200)
        self.assertEqual(self.client.get(self.o_b.fotografija.url).status_code, 200)

    def test_samo_superadministrator_ulazi_u_django_administraciju(self):
        url = reverse("admin:ocitanja_stan_changelist")
        self.assertNotIn("/admin/", url)
        self.prijava("admin_a")
        self.assertNotEqual(self.client.get(url).status_code, 200)
        self.prijava("dean")
        self.assertEqual(self.client.get(url).status_code, 200)


class AdministratorViseZgradaTest(DvijeZgrade):
    def test_bira_samo_svoje_zgrade(self):
        AdministratorZgrade.objects.create(korisnik=self.admin_a, zgrada=self.zgrada_b)
        treca = Zgrada.objects.create(oznaka="ST-RIV-1", ulica="Riva", kucni_broj="1", postanski_broj="21000", grad="Split")
        self.prijava("admin_a")
        self.assertRedirects(self.client.get("/"), "/zgrade/")
        r = self.client.get("/zgrade/")
        self.assertContains(r, "Ilica 10")
        self.assertNotContains(r, "Riva")
        self.client.post("/zgrade/odaberi/", {"zgrada": treca.pk})
        self.assertRedirects(self.client.get("/"), "/zgrade/")


class WebPrijavaTest(DvijeZgrade):
    def test_suvlasnik_se_ne_prijavljuje_na_web(self):
        r = self.client.post("/prijava/", {"username": "ana", "password": "lozinka-123"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "samo administratorima")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_administrator_nakon_lozinke_upisuje_kod(self):
        r = self.client.post("/prijava/", {"username": "admin_b", "password": "lozinka-123"})
        self.assertRedirects(r, "/prijava/kod/")
        self.assertNotIn("_auth_user_id", self.client.session)


class ViseStanovaUViseZgradaTest(DvijeZgrade):
    def test_api_vraca_stanove_i_zgrade(self):
        KorisnikStan.objects.create(korisnik=self.ana, stan=self.b3, od_datuma=datetime.date(2020, 1, 1))
        api = APIClient()
        api.force_authenticate(self.ana)
        ja = api.get("/api/ja/").json()
        self.assertEqual(sorted(z["oznaka"] for z in ja["zgrade"]), ["RI-ALB-2", "ZG-ILI-10"])
        self.assertEqual(sorted(s["oznaka"] for s in ja["stanovi"]), ["RI-ALB-2/3", "ZG-ILI-10/3"])
        stan = next(s for s in ja["stanovi"] if s["zgrada"] == self.zgrada_b.pk)
        self.assertEqual(stan["uid"], str(self.b3.uid))
        r = api.post("/api/ocitanja/", {"vodomjer": self.vb3.pk, "novo_stanje": "13"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["zgrada"], self.zgrada_b.pk)


class JedinstvenostTest(TestCase):
    def setUp(self):
        self.zgrada = Zgrada.objects.create(
            oznaka="ri-alb-2", ulica="Moše Albaharija", kucni_broj="2", postanski_broj="51000", grad="Rijeka"
        )

    def test_ista_adresa_ne_moze_dvaput(self):
        self.assertEqual(self.zgrada.oznaka, "RI-ALB-2")
        self.assertEqual(kljuc_adrese(" mose  albaharija. ", "2", "RIJEKA"), self.zgrada.kljuc_adrese)
        druga = Zgrada(oznaka="X", ulica="Mose Albaharija.", kucni_broj="2", postanski_broj="51000", grad="rijeka")
        with self.assertRaises(ValidationError):
            druga.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            druga.save()

    def test_broj_stana_jedinstven_samo_u_zgradi(self):
        druga = Zgrada.objects.create(oznaka="RI-ALB-4", ulica="Moše Albaharija", kucni_broj="4", postanski_broj="51000", grad="Rijeka")
        a = Stan.objects.create(zgrada=self.zgrada, broj_stana="1")
        b = Stan.objects.create(zgrada=druga, broj_stana="1")
        self.assertNotEqual(a.uid, b.uid)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stan.objects.create(zgrada=self.zgrada, broj_stana="1")

    def test_stan_se_ne_premjesta(self):
        druga = Zgrada.objects.create(oznaka="RI-ALB-4", ulica="Moše Albaharija", kucni_broj="4", postanski_broj="51000", grad="Rijeka")
        stan = Stan.objects.create(zgrada=self.zgrada, broj_stana="1")
        stan.zgrada = druga
        with self.assertRaises(ValidationError):
            stan.save()

    def test_zgrada_sa_stanovima_se_ne_brise(self):
        from django.db.models import ProtectedError

        Stan.objects.create(zgrada=self.zgrada, broj_stana="1")
        with self.assertRaises(ProtectedError):
            self.zgrada.delete()


class UvozUDruguZgraduTest(TestCase):
    def test_isto_ime_u_drugoj_zgradi_novi_racun_i_napomena(self):
        a = Zgrada.objects.create(oznaka="A", ulica="Prva", kucni_broj="1", postanski_broj="1", grad="Rijeka")
        b = Zgrada.objects.create(oznaka="B", ulica="Druga", kucni_broj="1", postanski_broj="1", grad="Rijeka")
        mapa = Path(tempfile.mkdtemp())
        izlaz = []
        for zgrada, redovi in [(a, [("1", "Njirić Sanja", 5)]), (b, [("1", "Njirić Sanja", 7)])]:
            knjiga = Workbook()
            for red in redovi:
                knjiga.active.append(red)
            knjiga.save(mapa / f"{zgrada.oznaka}.xlsx")
            from io import StringIO

            ispis = StringIO()
            call_command(
                "uvoz_stanova", str(mapa / f"{zgrada.oznaka}.xlsx"), zgrada=str(zgrada.uid),
                pristupni_podaci=str(mapa / f"pristup-{zgrada.oznaka}.xlsx"), stdout=ispis,
            )
            izlaz.append(ispis.getvalue())
        self.assertEqual(
            sorted(Korisnik.objects.filter(last_name="Njirić").values_list("username", flat=True)),
            ["njiric.sanja", "njiric.sanja2"],
        )
        self.assertNotIn("isto ime", izlaz[0])
        self.assertIn("isto ime postoji i u zgradi A", izlaz[1])


class MigracijaPostojeceZgradeTest(TransactionTestCase):
    """Baza prije više zgrada (20 stanova, Sanja s dva stana) prelazi u zgradu Moše Albaharija 2."""

    prije = [("ocitanja", "0002_postavke")]
    poslije = [("ocitanja", "0005_zgrada_obavezna")]

    def test_migracija(self):
        izvrsitelj = MigrationExecutor(connection)
        izvrsitelj.migrate(self.prije)
        stari = izvrsitelj.loader.project_state(self.prije).apps
        Korisnik_ = stari.get_model("ocitanja", "Korisnik")
        Stan_ = stari.get_model("ocitanja", "Stan")
        KorisnikStan_ = stari.get_model("ocitanja", "KorisnikStan")
        Postavke_ = stari.get_model("ocitanja", "Postavke")
        dean = Korisnik_.objects.create(username="administrator", is_superuser=True, is_staff=True)
        Korisnik_.objects.create(username="predstavnik", uloga="administrator", is_staff=True)
        sanja = Korisnik_.objects.create(username="njiric.sanja")
        for broj in ("17", "19"):
            KorisnikStan_.objects.create(
                korisnik=sanja, stan=Stan_.objects.create(broj_stana=broj), od_datuma=datetime.date(2026, 9, 26)
            )
        Postavke_.objects.create(pk=1, dan_ocitanja=26, sat_podsjetnika=10, email_obavijesti="d@example.com")

        izvrsitelj = MigrationExecutor(connection)
        izvrsitelj.loader.build_graph()
        izvrsitelj.migrate(self.poslije)
        novi = izvrsitelj.loader.project_state(self.poslije).apps
        Zgrada_ = novi.get_model("ocitanja", "Zgrada")
        zgrada = Zgrada_.objects.get()
        self.assertEqual(
            (zgrada.oznaka, zgrada.ulica, zgrada.kucni_broj, zgrada.postanski_broj, zgrada.grad),
            ("RI-ALB-2", "Moše Albaharija", "2", "51000", "Rijeka"),
        )
        self.assertEqual(zgrada.kljuc_adrese, kljuc_adrese("Moše Albaharija", "2", "Rijeka"))
        stanovi = novi.get_model("ocitanja", "Stan").objects.all()
        self.assertEqual({s.zgrada_id for s in stanovi}, {zgrada.pk})
        self.assertEqual(len({s.uid for s in stanovi}), 2)
        postavke = novi.get_model("ocitanja", "Postavke").objects.get()
        self.assertEqual((postavke.zgrada_id, postavke.sat_podsjetnika), (zgrada.pk, 10))
        uloge = novi.get_model("ocitanja", "AdministratorZgrade").objects.values_list("korisnik__username", flat=True)
        self.assertEqual(list(uloge), ["predstavnik"])
        K = novi.get_model("ocitanja", "Korisnik")
        self.assertTrue(K.objects.get(username="administrator").is_staff)
        self.assertFalse(K.objects.get(username="predstavnik").is_staff)
        self.assertEqual(
            novi.get_model("ocitanja", "KorisnikStan").objects.filter(korisnik__username="njiric.sanja").count(), 2
        )
        self.assertEqual(dean.pk, K.objects.get(username="administrator").pk)
