"""Zaštita prijave: blokada pogađanja lozinke, prijava u dva koraka (TOTP) i sigurnosna zaglavlja."""
import hashlib
import secrets
from datetime import timedelta

import pyotp
import segno
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import Zapisnik, ip_klijenta

NAZIV_IZDAVATELJA = "Prijava vode"
SESIJA_DVA_KORAKA = "dva_koraka_potvrdjen"


# --- Blokada pogađanja lozinke -------------------------------------------------------------------

def blokirano(korisnicko_ime, request):
    """Previše neuspjelih prijava za isto korisničko ime ili s iste adrese u zadnjih nekoliko minuta."""
    od = timezone.now() - timedelta(minutes=settings.BLOKADA_MINUTA)
    neuspjele = Zapisnik.objects.filter(radnja=Zapisnik.Radnja.NEUSPJELA_PRIJAVA, vrijeme__gte=od)
    ip = ip_klijenta(request)
    po_imenu = neuspjele.filter(podaci__korisnicko_ime=(korisnicko_ime or "").strip().lower()).count()
    po_adresi = neuspjele.filter(ip=ip).count() if ip else 0
    return po_imenu >= settings.BLOKADA_POKUSAJA or po_adresi >= settings.BLOKADA_POKUSAJA_ADRESA


def zabiljezi_neuspjeh(request, korisnicko_ime, gdje):
    Zapisnik.upisi(
        Zapisnik.Radnja.NEUSPJELA_PRIJAVA, f"Neuspjela prijava ({gdje}) za '{(korisnicko_ime or '')[:50]}'",
        request=request, korisnik=None, korisnicko_ime=(korisnicko_ime or "").strip().lower(), gdje=gdje,
    )


PORUKA_BLOKADE = "Previše pogrešnih pokušaja. Pričekajte {} minuta i pokušajte ponovno."


def poruka_blokade():
    return PORUKA_BLOKADE.format(settings.BLOKADA_MINUTA)


# --- Prijava u dva koraka ------------------------------------------------------------------------

def nova_tajna():
    return pyotp.random_base32()


def qr_kod_svg(tajna, korisnik):
    uri = pyotp.TOTP(tajna).provisioning_uri(name=korisnik.username, issuer_name=NAZIV_IZDAVATELJA)
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#1d232b")


def _sazetak(kod):
    return hashlib.sha256(kod.replace("-", "").replace(" ", "").lower().encode()).hexdigest()


def novi_rezervni_kodovi(korisnik, broj=10):
    """Jednokratni kodovi za slučaj gubitka mobitela; u bazi ostaje samo njihov sažetak."""
    kodovi = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(broj)]
    korisnik.rezervni_kodovi = [_sazetak(k) for k in kodovi]
    return kodovi


def provjeri_kod(korisnik, kod, tajna=None):
    """Šesteroznamenkasti kod iz aplikacije ili rezervni kod; isti kod ne vrijedi dvaput."""
    kod = (kod or "").strip().replace(" ", "")
    tajna = tajna or korisnik.totp_tajna
    if not tajna or not kod:
        return False
    if kod.isdigit() and len(kod) == 6:
        totp = pyotp.TOTP(tajna)
        sada = timezone.now()
        for pomak in (0, -1, 1):  # dopušta 30 sekundi razlike u satu mobitela
            trenutak = sada + timedelta(seconds=30 * pomak)
            korak = totp.timecode(trenutak)
            if secrets.compare_digest(totp.at(trenutak), kod):
                if korisnik.totp_zadnji_korak is not None and korak <= korisnik.totp_zadnji_korak:
                    return False
                korisnik.totp_zadnji_korak = korak
                korisnik.save(update_fields=["totp_zadnji_korak"])
                return True
        return False
    sazetak = _sazetak(kod)
    if sazetak in korisnik.rezervni_kodovi:
        korisnik.rezervni_kodovi = [k for k in korisnik.rezervni_kodovi if k != sazetak]
        korisnik.save(update_fields=["rezervni_kodovi"])
        return True
    return False


def ponisti_dva_koraka(korisnik):
    korisnik.totp_tajna = ""
    korisnik.totp_zadnji_korak = None
    korisnik.rezervni_kodovi = []
    korisnik.save(update_fields=["totp_tajna", "totp_zadnji_korak", "rezervni_kodovi"])


# --- Middleware -----------------------------------------------------------------------------------

IZUZETO = ("/api/", "/aplikacija/", "/static/", "/prijava/", "/odjava/")


class ZastitaPrijave:
    """Administrator bez potvrđenog drugog koraka se odjavljuje; tko mora promijeniti lozinku, ide na promjenu."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        korisnik = request.user
        if korisnik.is_authenticated and not request.path.startswith(IZUZETO):
            if not request.session.get(SESIJA_DVA_KORAKA):
                # Sesija iz vremena prije dva koraka ili pokušaj zaobilaženja drugog koraka.
                logout(request)
                return redirect(f"{reverse('prijava')}?next={request.path}")
            if korisnik.mora_promijeniti_lozinku and request.path != reverse("promjena_lozinke"):
                return redirect("promjena_lozinke")
        return self.get_response(request)


class SigurnosnaZaglavlja:
    CSP = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        odgovor = self.get_response(request)
        odgovor.setdefault("Content-Security-Policy", self.CSP)
        odgovor.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        odgovor.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            odgovor.setdefault("Cache-Control", "no-store")
        return odgovor


# --- API ------------------------------------------------------------------------------------------

class TokenSIstekom(TokenAuthentication):
    """Prijava u aplikaciji istječe nakon TOKEN_ISTEK_DANA dana nekorištenja; svako korištenje je produljuje."""

    def authenticate_credentials(self, key):
        korisnik, token = super().authenticate_credentials(key)
        sada = timezone.now()
        if token.created < sada - timedelta(days=settings.TOKEN_ISTEK_DANA):
            token.delete()
            raise AuthenticationFailed("Prijava je istekla. Prijavite se ponovno.")
        if token.created < sada - timedelta(days=1):
            type(token).objects.filter(pk=token.pk).update(created=sada)
        return korisnik, token


# --- Lozinke --------------------------------------------------------------------------------------

class DuljaLozinkaAdministratora:
    """Administratori imaju pristup podacima cijele zgrade, pa im lozinka mora biti dulja."""

    def __init__(self, min_length=12):
        self.min_length = min_length

    def validate(self, password, user=None):
        if user is not None and getattr(user, "pk", None) and user.je_administrator and len(password) < self.min_length:
            raise ValidationError(
                f"Lozinka administratora mora imati barem {self.min_length} znakova.", code="password_too_short"
            )

    def get_help_text(self):
        return f"Administratori: barem {self.min_length} znakova."
