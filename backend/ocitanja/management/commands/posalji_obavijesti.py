"""Šalje podsjetnike suvlasnicima i popis neočitanih administratorima po rasporedu svake zgrade.

Cron ga pokreće svakih 15 minuta (deploy/zakazi.sh); svaka poruka ide najviše jednom dnevno.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ocitanja.models import Zgrada
from ocitanja.obavijesti import posalji


class Command(BaseCommand):
    help = "Šalje podsjetnike i obavijesti o neočitanim vodomjerima kojima je sada termin."

    def add_arguments(self, parser):
        parser.add_argument("--odmah", action="store_true",
                            help="Pošalji odmah, bez obzira na dan i sat (za probu; ne bilježi se kao poslano).")
        parser.add_argument("--zgrada", help="Samo zgrada s ovom oznakom, npr. RI-ALB-2.")

    def handle(self, *args, odmah=False, zgrada=None, **opcije):
        zgrade = None
        if zgrada:
            zgrade = list(Zgrada.objects.filter(oznaka=zgrada.strip().upper()))
            if not zgrade:
                raise CommandError(f"Nema zgrade s oznakom {zgrada}.")
        for red in posalji(timezone.localtime(), odmah=odmah, zgrade=zgrade):
            self.stdout.write(red)
