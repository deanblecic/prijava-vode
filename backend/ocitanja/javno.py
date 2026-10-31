"""Javna početna stranica: opis aplikacije, slike ekrana, upute i preuzimanje uputa."""
import logging
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.shortcuts import render
from django.utils import timezone

from .models import ip_klijenta

log = logging.getLogger(__name__)

from . import upravljanje

# Upute koje se mogu preuzeti s početne stranice (datoteke su u static/javno/upute/).
UPUTE = [
    {
        "naslov": "Upute za suvlasnike",
        "opis": "Preuzimanje i instalacija aplikacije, prva prijava i mjesečno očitanje, korak po korak.",
        "za": "Suvlasnici",
        "datoteka": "ocitanje-vode-upute-za-suvlasnike",
    },
    {
        "naslov": "Upute za korištenje aplikacije",
        "opis": "Svi ekrani Android aplikacije: prijava, otisak prsta, očitanje kamerom i iz galerije, ispravak i povijest.",
        "za": "Suvlasnici",
        "datoteka": "ocitanje-vode-upute-za-koristenje-aplikacije",
    },
    {
        "naslov": "Priručnik za web administraciju",
        "opis": "Mjesečni pregled, potvrda i ispravak očitanja, stanovi, korisnici, podsjetnici i izvoz u Excel.",
        "za": "Administratori",
        "datoteka": "prijava-vode-prirucnik-za-web-administraciju",
    },
]


def _velicina(putanja):
    pronadjeno = finders.find(putanja)
    if not pronadjeno:
        return None
    kb = Path(pronadjeno).stat().st_size / 1024
    return f"{kb:.0f} kB" if kb < 1024 else f"{kb / 1024:.1f} MB"


def _upute():
    popis = []
    for u in UPUTE:
        formati = []
        for nastavak, naziv in (("pdf", "PDF"), ("docx", "Word")):
            putanja = f"javno/upute/{u['datoteka']}.{nastavak}"
            velicina = _velicina(putanja)
            if velicina:
                formati.append({"putanja": putanja, "naziv": naziv, "velicina": velicina})
        popis.append({**u, "formati": formati})
    return popis


def pocetna(request):
    """Prijavljenom administratoru mjesečni pregled, svima ostalima javna početna stranica."""
    if request.user.is_authenticated:
        return upravljanje.pregled(request)
    return render(request, "javno/pocetna.html", {"upute": _upute()})


# --- Kontaktirajte nas -----------------------------------------------------------------------------

NAJVISE_ZNAKOVA = 3000
# Najviše ovoliko poruka s iste adrese u jednom satu, da obrazac ne posluži za slanje neželjene pošte.
NAJVISE_PORUKA_NA_SAT = 5


class KontaktForm(forms.Form):
    ime = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"autocomplete": "email"}),
                             error_messages={"invalid": "Upišite ispravnu e-mail adresu."})
    poruka = forms.CharField(
        max_length=NAJVISE_ZNAKOVA, widget=forms.Textarea(attrs={"rows": 8, "maxlength": NAJVISE_ZNAKOVA}),
        error_messages={"required": "Upišite poruku.",
                        "max_length": f"Poruka može imati najviše {NAJVISE_ZNAKOVA} znakova."},
    )
    # Skriveno polje: ljudi ga ne vide, a automatski programi za neželjenu poštu ga ispune.
    web_stranica = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_poruka(self):
        poruka = self.cleaned_data["poruka"].strip()
        if not poruka:
            raise forms.ValidationError("Upišite poruku.")
        return poruka


def _posalji_poruku(podaci, request):
    ime = " ".join(podaci["ime"].split())  # bez prijeloma reda u naslovu poruke
    email = podaci["email"].strip()
    tijelo = (
        f"{podaci['poruka']}\n\n"
        "---\n"
        f"Ime: {ime or '(nije upisano)'}\n"
        f"E-mail za odgovor: {email or '(nije upisan)'}\n"
        f"Poslano: {timezone.localtime():%d.%m.%Y. %H:%M}\n"
        f"Adresa: {ip_klijenta(request) or '-'}\n"
    )
    naslov = "Očitanje vode – poruka s web stranice" + (f" ({ime})" if ime else "")
    EmailMessage(
        subject=naslov[:150],
        body=tijelo,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.KONTAKT_EMAIL],
        reply_to=[email] if email else None,
    ).send()


def kontakt(request):
    """Javni obrazac čija se poruka šalje e-mailom na KONTAKT_EMAIL."""
    kontekst = {"najvise_znakova": NAJVISE_ZNAKOVA}
    if request.method == "POST":
        form = KontaktForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["web_stranica"]:
                # Automatski program: pravimo se da je poslano, ali ništa ne šaljemo.
                return render(request, "javno/kontakt.html", {**kontekst, "form": form, "poslano": True})
            kljuc = f"kontakt:{ip_klijenta(request) or 'nepoznato'}"
            broj = cache.get(kljuc, 0)
            if broj >= NAJVISE_PORUKA_NA_SAT:
                kontekst["greska"] = "Poslali ste previše poruka. Pokušajte ponovno za sat vremena."
            else:
                try:
                    _posalji_poruku(form.cleaned_data, request)
                except Exception:
                    log.exception("Slanje poruke iz obrasca Kontaktirajte nas nije uspjelo")
                    kontekst["greska"] = "Poruku trenutno nije moguće poslati. Pokušajte ponovno malo kasnije."
                else:
                    cache.set(kljuc, broj + 1, 3600)
                    return render(request, "javno/kontakt.html", {**kontekst, "form": form, "poslano": True})
    else:
        form = KontaktForm()
    return render(request, "javno/kontakt.html", {**kontekst, "form": form})
