"""Slanje podsjetnika suvlasnicima i popisa neočitanih administratoru po rasporedu svake zgrade.

Naredbu posalji_obavijesti cron pokreće svakih 15 minuta (deploy/zakazi.sh). Poruka se šalje prvi put
kad je dan slanja i sat slanja (po hrvatskom vremenu) prošao, a PoslanaObavijest pamti da je poslana.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import IntegrityError, transaction

from .models import Ocitanje, PoslanaObavijest, Postavke, Zgrada
from .rokovi import datum_roka, dani_obavijesti, dani_podsjetnika
from .upravljanje import redovi_mjeseca, vlasnici_u_mjesecu

log = logging.getLogger(__name__)


def neocitani(zgrada, mjesec):
    """Redovi stanova bez očitanja u mjesecu; odbijeno očitanje treba ponoviti pa se i ono broji."""
    return [
        r for r in redovi_mjeseca(zgrada, mjesec)
        if r["ocitanje"] is None or r["ocitanje"].status == Ocitanje.Status.ODBIJENO
    ]


def primatelji_obavijesti(zgrada, postavke):
    upisano = [a.strip() for a in postavke.email_obavijesti.split(",") if a.strip()]
    if upisano:
        return upisano
    return sorted({k.email for k in zgrada.administratori.filter(is_active=True) if k.email})


def podsjetnici(zgrada, postavke, danas, mjesec):
    """Jedan e-mail svakom suvlasniku s e-mailom čiji stan još nije očitan."""
    if not postavke.email_stanarima:
        return []
    po_korisniku = {}
    for red in neocitani(zgrada, mjesec):
        for korisnik in vlasnici_u_mjesecu(red["stan"], mjesec):
            if korisnik.is_active and korisnik.email:
                po_korisniku.setdefault(korisnik, []).append(red["stan"].broj_stana)
    rok = datum_roka(postavke, mjesec)
    poruke = []
    for korisnik, stanovi in po_korisniku.items():
        koji = f"stana {stanovi[0]}" if len(stanovi) == 1 else f"stanova {', '.join(stanovi)}"
        poruke.append(EmailMessage(
            f"Podsjetnik: očitajte vodomjer do {rok:%d.%m.%Y.}",
            f"Poštovani/a {korisnik.get_full_name() or korisnik.username},\n\n"
            f"vodomjer {koji} u zgradi {zgrada.adresa} za {mjesec:%m/%Y} još nije očitan.\n"
            f"Rok za očitanje je {rok:%d.%m.%Y.} Očitanje predajte u aplikaciji Očitanje vode.\n\n"
            "Ova poruka je poslana automatski.\n",
            None,
            [korisnik.email],
        ))
    return poruke


def popis_neocitanih(zgrada, postavke, danas, mjesec):
    """Popis stanova koji još nisu očitali, administratorima zgrade."""
    redovi = neocitani(zgrada, mjesec)
    kome = primatelji_obavijesti(zgrada, postavke)
    if not redovi or not kome:
        if redovi:
            log.warning("%s: nema primatelja obavijesti; upišite e-mail u Podsjetnicima ili administratoru.", zgrada.oznaka)
        return []
    rok = datum_roka(postavke, mjesec)
    popis = "\n".join(f"- stan {r['stan'].broj_stana}: {r['vlasnici'] or 'bez vlasnika'}" for r in redovi)
    return [EmailMessage(
        f"{zgrada.ulica} {zgrada.kucni_broj}: neočitani vodomjeri za {mjesec:%m/%Y} ({len(redovi)})",
        f"Zgrada {zgrada.adresa} ({zgrada.oznaka}).\n\n"
        f"Do danas ({danas:%d.%m.%Y.}) nisu očitani vodomjeri ovih stanova:\n\n{popis}\n\n"
        f"Rok za očitanje je {rok:%d.%m.%Y.}\n",
        None,
        kome,
    )]


VRSTE = [
    (PoslanaObavijest.Vrsta.PODSJETNIK, dani_podsjetnika, "sat_podsjetnika", podsjetnici),
    (PoslanaObavijest.Vrsta.NEOCITANI, dani_obavijesti, "sat_obavijesti", popis_neocitanih),
]


def zauzmi(zgrada, vrsta, danas):
    """Upisuje da se poruka šalje; False ako ju je danas već poslao netko drugi."""
    try:
        with transaction.atomic():
            return PoslanaObavijest.objects.create(zgrada=zgrada, vrsta=vrsta, datum=danas)
    except IntegrityError:
        return None


def posalji(sada, *, odmah=False, zgrade=None):
    """Šalje sve što je za trenutak sada na redu; vraća opis za log. odmah: bez obzira na dan, sat i zapis."""
    danas = sada.date()
    mjesec = danas.replace(day=1)
    izvjestaj = []
    zgrade = zgrade if zgrade is not None else Zgrada.objects.filter(aktivna=True)
    for zgrada in zgrade:
        postavke = Postavke.ucitaj(zgrada)
        for vrsta, dani, polje_sata, poruke_za in VRSTE:
            if not odmah and (danas.day not in dani(postavke, mjesec) or sada.hour < getattr(postavke, polje_sata)):
                continue
            zapis = None
            if not odmah:
                zapis = zauzmi(zgrada, vrsta, danas)
                if zapis is None:
                    continue
            try:
                poruke = poruke_za(zgrada, postavke, danas, mjesec)
                if poruke:
                    get_connection().send_messages(poruke)
            except Exception:
                # Zapis se briše da se sljedeće pokretanje pokuša ponovno.
                if zapis is not None:
                    zapis.delete()
                log.exception("%s: slanje (%s) nije uspjelo", zgrada.oznaka, vrsta)
                izvjestaj.append(f"{zgrada.oznaka} {vrsta}: GREŠKA pri slanju")
                continue
            primatelja = sum(len(p.to) for p in poruke)
            if zapis is not None:
                zapis.broj_primatelja = primatelja
                zapis.save(update_fields=["broj_primatelja"])
            izvjestaj.append(f"{zgrada.oznaka} {vrsta} {danas:%d.%m.%Y.}: {primatelja} primatelja")
    return izvjestaj


