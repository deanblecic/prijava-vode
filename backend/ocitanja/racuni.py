"""Računi korisnika u zgradi: tko kome smije mijenjati lozinku, spajanje istoimenih računa i administratori."""
import unicodedata
from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from rest_framework.authtoken.models import Token

from .models import AdministratorZgrade, Korisnik, KorisnikStan, Ocitanje
from .servisi import nova_lozinka


class GreskaRacuna(Exception):
    pass


def korisnici_zgrade(zgrada):
    """Svi koji su ikad bili suvlasnici u zgradi ili su njezini administratori."""
    return (
        Korisnik.objects.filter(Q(vlasnistva__stan__zgrada=zgrada) | Q(uloge_u_zgradama__zgrada=zgrada))
        .distinct().order_by("last_name", "first_name", "username")
    )


def samo_u_zgradi(korisnik, zgrada):
    """Račun bez ikakve veze s drugom zgradom; samo takvim računom upravlja administrator zgrade."""
    return (
        not korisnik.is_superuser
        and not korisnik.vlasnistva.exclude(stan__zgrada=zgrada).exists()
        and not korisnik.uloge_u_zgradama.exclude(zgrada=zgrada).exists()
    )


def smije_upravljati(administrator, korisnik, zgrada):
    if administrator.is_superuser:
        return True
    if not administrator.zgrade_za_upravljanje().filter(pk=zgrada.pk).exists():
        return False
    return samo_u_zgradi(korisnik, zgrada)


def postavi_novu_lozinku(korisnik):
    """Nova lozinka za podjelu korisniku; mijenja je sam kod sljedeće prijave, a stare prijave prestaju vrijediti."""
    lozinka = nova_lozinka()
    korisnik.set_password(lozinka)
    korisnik.mora_promijeniti_lozinku = True
    korisnik.is_active = True
    korisnik.save()
    Token.objects.filter(user=korisnik).delete()
    return lozinka


def kljuc_imena(korisnik):
    tekst = f"{korisnik.first_name} {korisnik.last_name}".replace("đ", "dj").replace("Đ", "Dj")
    tekst = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(tekst.split()))


def isto_ime(korisnici):
    """Skupine aktivnih računa s istim imenom i prezimenom (bez obzira na kvačice i redoslijed)."""
    skupine = defaultdict(list)
    for korisnik in korisnici:
        if korisnik.is_active and kljuc_imena(korisnik):
            skupine[kljuc_imena(korisnik)].append(korisnik)
    return [s for s in skupine.values() if len(s) > 1]


def provjeri_spajanje(administrator, ostaje, odlazi, zgrada):
    if ostaje.pk == odlazi.pk:
        raise GreskaRacuna("Odaberite dva različita računa.")
    if odlazi.is_superuser:
        raise GreskaRacuna("Račun superadministratora ne može se spojiti u drugi.")
    if not odlazi.is_active:
        raise GreskaRacuna("Račun koji se spaja već je isključen.")
    for korisnik in (ostaje, odlazi):
        if not smije_upravljati(administrator, korisnik, zgrada):
            raise GreskaRacuna(
                f"{korisnik} ({korisnik.username}) ima stan ili ulogu i u drugoj zgradi. "
                "Takve račune spaja superadministrator."
            )


@transaction.atomic
def spoji_racune(ostaje, odlazi):
    """Stanovi, očitanja i uloge prelaze na račun koji ostaje; drugi se isključuje, ali ne briše.

    Vraća id-jeve premještenih redova, da se spajanje može poništiti.
    """
    vlasnistva = list(odlazi.vlasnistva.values_list("pk", flat=True))
    ocitanja = list(Ocitanje.objects.filter(korisnik=odlazi).values_list("pk", flat=True))
    uloge, suvisne = [], []
    for uloga in odlazi.uloge_u_zgradama.all():
        if AdministratorZgrade.objects.filter(korisnik=ostaje, zgrada=uloga.zgrada).exists():
            suvisne.append(uloga.zgrada_id)
            uloga.delete()
        else:
            uloge.append(uloga.pk)
    KorisnikStan.objects.filter(pk__in=vlasnistva).update(korisnik=ostaje)
    Ocitanje.objects.filter(pk__in=ocitanja).update(korisnik=ostaje)
    AdministratorZgrade.objects.filter(pk__in=uloge).update(korisnik=ostaje)
    odlazi.is_active = False
    odlazi.save(update_fields=["is_active"])
    Token.objects.filter(user=odlazi).delete()
    return {
        "ostaje": ostaje.pk, "odlazi": odlazi.pk,
        "vlasnistva": vlasnistva, "ocitanja": ocitanja, "uloge": uloge, "suvisne_uloge": suvisne,
    }


@transaction.atomic
def ponisti_spajanje(podaci):
    odlazi = Korisnik.objects.get(pk=podaci["odlazi"])
    KorisnikStan.objects.filter(pk__in=podaci["vlasnistva"]).update(korisnik=odlazi)
    Ocitanje.objects.filter(pk__in=podaci["ocitanja"]).update(korisnik=odlazi)
    AdministratorZgrade.objects.filter(pk__in=podaci["uloge"]).update(korisnik=odlazi)
    for zgrada_id in podaci.get("suvisne_uloge", []):
        AdministratorZgrade.objects.get_or_create(korisnik=odlazi, zgrada_id=zgrada_id)
    odlazi.is_active = True
    odlazi.save(update_fields=["is_active"])
    return odlazi


def dodaj_administratora(korisnik, zgrada):
    _, novi = AdministratorZgrade.objects.get_or_create(korisnik=korisnik, zgrada=zgrada)
    if not novi:
        raise GreskaRacuna(f"{korisnik} je već administrator ove zgrade.")


@transaction.atomic
def ukloni_administratora(korisnik, zgrada):
    uloge = AdministratorZgrade.objects.select_for_update().filter(zgrada=zgrada)
    if not uloge.filter(korisnik=korisnik).exists():
        raise GreskaRacuna(f"{korisnik} nije administrator ove zgrade.")
    if uloge.count() == 1:
        raise GreskaRacuna("Zgrada mora imati barem jednog administratora. Prvo dodajte drugog.")
    uloge.filter(korisnik=korisnik).delete()
