"""Puni praznu bazu primjerom zgrade od 21 stana, za isprobavanje sučelja."""
import datetime
import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ocitanja.models import Korisnik, KorisnikStan, Ocitanje, Stan, Vodomjer
from ocitanja.servisi import predaj_ocitanje

IMENA = ["Ana", "Ivan", "Marija", "Luka", "Petra", "Josip", "Ivana", "Marko", "Katarina", "Tomislav", "Lucija"]
PREZIMENA = ["Horvat", "Kovačević", "Babić", "Marić", "Jurić", "Novak", "Knežević", "Vuković", "Perić", "Pavlović"]


class Command(BaseCommand):
    help = "Stvara 21 stan, suvlasnike (lozinka: probna-lozinka) i tri mjeseca očitanja."

    def handle(self, *args, **opcije):
        if Stan.objects.exists():
            raise CommandError("Baza već ima stanove; primjer se puni samo u praznu bazu.")
        slucajno = random.Random(7)
        if not Korisnik.objects.filter(username="admin").exists():
            Korisnik.objects.create_user(
                "admin", password="probna-lozinka", first_name="Dean", uloga=Korisnik.Uloga.ADMINISTRATOR
            )
        danas = timezone.localdate().replace(day=1)
        mjeseci = [(danas - datetime.timedelta(days=31 * i)).replace(day=1) for i in (2, 1, 0)]
        for broj in range(1, 22):
            stan = Stan.objects.create(broj_stana=str(broj), kat=(broj - 1) // 4)
            korisnik = Korisnik.objects.create_user(
                f"stan{broj}", password="probna-lozinka",
                first_name=slucajno.choice(IMENA), last_name=slucajno.choice(PREZIMENA),
            )
            KorisnikStan.objects.create(korisnik=korisnik, stan=stan, od_datuma=datetime.date(2020, 1, 1))
            stanje = Decimal(slucajno.randint(80, 900))
            vodomjer = Vodomjer.objects.create(stan=stan, serijski_broj=f"VM{40000 + broj}", pocetno_stanje=stanje)
            for i, mjesec in enumerate(mjeseci):
                if i == 2 and broj % 5 == 0:
                    continue  # nekoliko stanova još nije predalo ovaj mjesec
                stanje += Decimal(slucajno.randint(2000, 9000)) / 1000
                if i == 2 and broj == 7:
                    stanje += 40  # sumnjivo velika potrošnja
                trenutak = timezone.make_aware(datetime.datetime.combine(mjesec.replace(day=3), datetime.time(18)))
                o = predaj_ocitanje(korisnik, vodomjer, stanje, datum_ocitanja=trenutak, ocr_vrijednost=stanje)
                if i < 2:
                    o.status = Ocitanje.Status.POTVRDENO
                    o.save()
        self.stdout.write(self.style.SUCCESS("Primjer podataka je spremljen. Prijava: admin / probna-lozinka"))
