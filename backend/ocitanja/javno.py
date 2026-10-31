"""Javna početna stranica: opis aplikacije, slike ekrana, upute i preuzimanje uputa."""
from pathlib import Path

from django.contrib.staticfiles import finders
from django.shortcuts import render

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
