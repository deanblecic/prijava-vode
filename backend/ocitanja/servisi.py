"""Pravila za predaju očitanja i upravljanje računima, zajednička API-ju i web sučelju."""
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from .models import Ocitanje, Vodomjer


SLOVA_LOZINKE = "abcdefghjkmnpqrstuvwxyz23456789"


def nova_lozinka():
    """Lozinka za podjelu na papiru: bez slova i brojki koje se lako zamijene (l/1, o/0)."""
    return "-".join("".join(secrets.choice(SLOVA_LOZINKE) for _ in range(4)) for _ in range(3))


class GreskaOcitanja(Exception):
    def __init__(self, kod, poruka):
        super().__init__(poruka)
        self.kod = kod
        self.poruka = poruka


def verzija_aplikacije():
    """Broj verzije APK-a na serveru ili None ako ga nema."""
    try:
        return int(settings.APK_VERZIJA.read_text().strip())
    except (OSError, ValueError):
        return None


def prvi_u_mjesecu(trenutak):
    datum = timezone.localtime(trenutak).date() if hasattr(trenutak, "hour") else trenutak
    return datum.replace(day=1)


def prethodno_stanje(vodomjer, razdoblje):
    """Zadnje neodbijeno očitanje prije razdoblja, a ako ga nema početno stanje vodomjera."""
    zadnje = (
        vodomjer.ocitanja.filter(razdoblje__lt=razdoblje)
        .exclude(status=Ocitanje.Status.ODBIJENO)
        .order_by("-razdoblje")
        .first()
    )
    return zadnje.novo_stanje if zadnje else vodomjer.pocetno_stanje


def prosjecna_razlika(vodomjer, razdoblje, broj_mjeseci=12):
    ids = (
        vodomjer.ocitanja.filter(razdoblje__lt=razdoblje)
        .exclude(status=Ocitanje.Status.ODBIJENO)
        .order_by("-razdoblje")
        .values_list("id", flat=True)[:broj_mjeseci]
    )
    return Ocitanje.objects.filter(id__in=list(ids)).aggregate(p=Avg("razlika"))["p"]


def korisnik_smije_ocitati(korisnik, vodomjer, samo_vlasnik=False):
    """Vlasnik stana; na webu i administrator zgrade u kojoj je stan ili superadministrator."""
    if not samo_vlasnik and korisnik.zgrade_za_upravljanje().filter(pk=vodomjer.stan.zgrada_id).exists():
        return True
    return korisnik.aktivni_stanovi().filter(pk=vodomjer.stan_id).exists()


@transaction.atomic
def predaj_ocitanje(
    korisnik,
    vodomjer,
    novo_stanje,
    *,
    datum_ocitanja=None,
    ocr_vrijednost=None,
    fotografija=None,
    napomena="",
    potvrdi_manje=False,
    samo_vlasnik=False,
):
    """Sprema ili ispravlja očitanje za mjesec u kojem je snimljeno.

    Aplikacija šalje samo_vlasnik=True: tamo i administrator očitava samo svoje stanove.
    Diže GreskaOcitanja kad korisnik nema pravo na vodomjer, kad je očitanje
    već potvrđeno ili kad je novo stanje manje od prethodnog bez potvrde.
    """
    if not vodomjer.aktivan:
        raise GreskaOcitanja("vodomjer_neaktivan", "Ovaj vodomjer više nije aktivan.")
    if not korisnik_smije_ocitati(korisnik, vodomjer, samo_vlasnik):
        raise GreskaOcitanja("nema_prava", "Nemate pravo predati očitanje za ovaj vodomjer.")

    novo_stanje = Decimal(novo_stanje)
    if novo_stanje < 0:
        raise GreskaOcitanja("negativno", "Stanje vodomjera ne može biti negativno.")

    datum_ocitanja = datum_ocitanja or timezone.now()
    razdoblje = prvi_u_mjesecu(datum_ocitanja)
    vodomjer = Vodomjer.objects.select_for_update().get(pk=vodomjer.pk)

    postojece = vodomjer.ocitanja.filter(razdoblje=razdoblje).first()
    if postojece and postojece.status == Ocitanje.Status.POTVRDENO:
        raise GreskaOcitanja(
            "vec_potvrdeno",
            "Očitanje za ovaj mjesec je već potvrđeno. Za ispravak se javite ovlaštenom predstavniku suvlasnika.",
        )

    prethodno = prethodno_stanje(vodomjer, razdoblje)
    razlozi = []
    if novo_stanje < prethodno:
        if not potvrdi_manje:
            raise GreskaOcitanja(
                "manje_od_prethodnog",
                f"Novo stanje ({novo_stanje}) manje je od prethodnog ({prethodno}). Provjerite broj.",
            )
        razlozi.append("novo stanje manje od prethodnog")

    razlika = novo_stanje - prethodno
    prosjek = prosjecna_razlika(vodomjer, razdoblje)
    prag = Decimal(str(settings.PRAG_SUMNJIVE_RAZLIKE))
    if prosjek and prosjek > 0 and razlika > prosjek * prag:
        razlozi.append(f"razlika {razlika} m³ veća je od {prag}× prosjeka ({prosjek:.3f} m³)")

    ocitanje = postojece or Ocitanje(vodomjer=vodomjer, razdoblje=razdoblje)
    ocitanje.korisnik = korisnik
    ocitanje.datum_ocitanja = datum_ocitanja
    ocitanje.prethodno_stanje = prethodno
    ocitanje.novo_stanje = novo_stanje
    ocitanje.ocr_vrijednost = ocr_vrijednost
    ocitanje.rucno_ispravljeno = ocr_vrijednost is not None and Decimal(ocr_vrijednost) != novo_stanje
    ocitanje.status = Ocitanje.Status.PREDANO
    ocitanje.za_provjeru = bool(razlozi)
    ocitanje.razlog_provjere = "; ".join(razlozi)[:200]
    ocitanje.napomena = napomena
    if fotografija is not None:
        ocitanje.fotografija = fotografija
    ocitanje.save()
    return ocitanje


@transaction.atomic
def promijeni_vlasnika(stan, novi_vlasnici, od_datuma):
    """Prodaja stana: zatvara trenutna suvlasništva dan prije od_datuma i otvara nova.

    Očitanja ostaju vezana uz vodomjer stana, pa povijest pokazuje i stare i nove vlasnike.
    """
    from datetime import timedelta

    from .models import KorisnikStan

    stan.vlasnistva.filter(do_datuma__isnull=True).update(do_datuma=od_datuma - timedelta(days=1))
    return [
        KorisnikStan.objects.create(korisnik=korisnik, stan=stan, od_datuma=od_datuma)
        for korisnik in novi_vlasnici
    ]


def uskladi_sljedece(vodomjer, razdoblje):
    """Nakon ispravka ili odbijanja preračunava prethodno stanje sljedećeg očitanja.

    Potvrđeno sljedeće očitanje se ne dira; tada vraća poruku upozorenja.
    """
    sljedece = (
        vodomjer.ocitanja.filter(razdoblje__gt=razdoblje)
        .exclude(status=Ocitanje.Status.ODBIJENO)
        .order_by("razdoblje")
        .first()
    )
    if not sljedece:
        return None
    ispravno = prethodno_stanje(vodomjer, sljedece.razdoblje)
    if sljedece.prethodno_stanje == ispravno:
        return None
    if sljedece.status == Ocitanje.Status.POTVRDENO:
        return (
            f"Potvrđeno očitanje za {sljedece.razdoblje:%m/%Y} ima prethodno stanje "
            f"{sljedece.prethodno_stanje}, a sada bi trebalo biti {ispravno}. Provjerite ga."
        )
    sljedece.prethodno_stanje = ispravno
    sljedece.save()
    return None


@transaction.atomic
def ispravi_ocitanje(ocitanje, novo_stanje, napomena=None):
    ocitanje.novo_stanje = Decimal(novo_stanje)
    ocitanje.prethodno_stanje = prethodno_stanje(ocitanje.vodomjer, ocitanje.razdoblje)
    if napomena is not None:
        ocitanje.napomena = napomena
    ocitanje.save()
    return uskladi_sljedece(ocitanje.vodomjer, ocitanje.razdoblje)


@transaction.atomic
def postavi_status(ocitanje, status):
    ocitanje.status = status
    if status == Ocitanje.Status.POTVRDENO:
        ocitanje.za_provjeru = False
    ocitanje.save()
    return uskladi_sljedece(ocitanje.vodomjer, ocitanje.razdoblje)
