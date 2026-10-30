"""Poništava Google Authenticator korisniku koji je izgubio mobitel i rezervne kodove.

Za superadministratora koji se sam ne može prijaviti; pokreće se na serveru.
"""
from django.core.management.base import BaseCommand, CommandError

from ocitanja.models import Korisnik, Zapisnik
from ocitanja.sigurnost import ponisti_dva_koraka


class Command(BaseCommand):
    help = "Poništava Google Authenticator; korisnik ga ponovno postavlja kod sljedeće prijave."

    def add_arguments(self, parser):
        parser.add_argument("korisnicko_ime")

    def handle(self, korisnicko_ime, **opcije):
        korisnik = Korisnik.objects.filter(username=korisnicko_ime).first()
        if korisnik is None:
            raise CommandError(f"Korisnik '{korisnicko_ime}' ne postoji.")
        ponisti_dva_koraka(korisnik)
        Zapisnik.upisi(Zapisnik.Radnja.DVA_KORAKA, f"Poništen Google Authenticator za {korisnik.username} (na serveru)",
                       korisnik=korisnik)
        self.stdout.write(self.style.SUCCESS(
            f"{korisnik.username}: kod sljedeće prijave na webu ponovno postavlja Google Authenticator."
        ))
