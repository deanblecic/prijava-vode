"""Zadnji dan u mjesecu javlja administratorima svake zgrade e-poštom koji vodomjeri nisu očitani.

Cron ga pokreće svaki sat (deploy/zakazi.sh); šalje samo zadnji dan u mjesecu u SAT_SLANJA po hrvatskom vremenu.
"""
from datetime import timedelta

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from ocitanja.models import Ocitanje, Postavke, Zgrada
from ocitanja.servisi import prvi_u_mjesecu
from ocitanja.upravljanje import redovi_mjeseca

SAT_SLANJA = 20


def neocitani(zgrada, mjesec):
    """Redovi stanova bez očitanja u mjesecu; odbijeno očitanje treba ponoviti pa se i ono broji."""
    return [
        r for r in redovi_mjeseca(zgrada, mjesec)
        if r["ocitanje"] is None or r["ocitanje"].status == Ocitanje.Status.ODBIJENO
    ]


def primatelji(zgrada):
    upisano = [a.strip() for a in Postavke.ucitaj(zgrada).email_obavijesti.split(",") if a.strip()]
    if upisano:
        return upisano
    return sorted({k.email for k in zgrada.administratori.filter(is_active=True) if k.email})


class Command(BaseCommand):
    help = "Zadnji dan u mjesecu šalje administratorima svake zgrade popis neočitanih vodomjera."

    def add_arguments(self, parser):
        parser.add_argument("--odmah", action="store_true", help="Pošalji odmah, bez obzira na dan i sat.")

    def handle(self, *args, odmah=False, **opcije):
        sada = timezone.localtime()
        danas = sada.date()
        zadnji_dan = (danas + timedelta(days=1)).day == 1
        if not (zadnji_dan and sada.hour == SAT_SLANJA or odmah):
            return
        mjesec = prvi_u_mjesecu(danas)
        for zgrada in Zgrada.objects.filter(aktivna=True):
            self.obavijesti(zgrada, mjesec, danas)

    def obavijesti(self, zgrada, mjesec, danas):
        redovi = neocitani(zgrada, mjesec)
        if not redovi:
            self.stdout.write(f"{zgrada.oznaka} {mjesec:%m/%Y}: svi vodomjeri su očitani.")
            return
        kome = primatelji(zgrada)
        if not kome:
            self.stderr.write(f"{zgrada.oznaka}: nema primatelja, upišite e-mail u Podsjetnicima ili administratoru.")
            return
        popis = "\n".join(f"- stan {r['stan'].broj_stana}: {r['vlasnici'] or 'bez vlasnika'}" for r in redovi)
        send_mail(
            f"{zgrada.ulica} {zgrada.kucni_broj}: neočitani vodomjeri za {mjesec:%m/%Y} ({len(redovi)})",
            f"Zgrada {zgrada.adresa} ({zgrada.oznaka}).\n\n"
            f"Do danas ({danas:%d.%m.%Y.}) nisu očitani vodomjeri ovih stanova:\n\n{popis}\n",
            None,
            kome,
        )
        self.stdout.write(
            f"{zgrada.oznaka} {mjesec:%m/%Y}: poslana obavijest za {len(redovi)} stanova na {', '.join(kome)}."
        )
