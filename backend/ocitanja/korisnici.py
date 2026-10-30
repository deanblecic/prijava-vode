"""Web stranice administratora zgrade: korisnici, spajanje računa, administratori, stanovi, zgrade i zapisnik."""
from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import NoviAdministratorForm, NoviStanForm, ZamjenaVodomjeraForm, ZgradaForm
from .models import Korisnik, Postavke, Stan, Vodomjer, Zapisnik
from .racuni import (
    GreskaRacuna,
    dodaj_administratora,
    isto_ime,
    korisnici_zgrade,
    ponisti_spajanje,
    postavi_novu_lozinku,
    provjeri_spajanje,
    samo_u_zgradi,
    smije_upravljati,
    spoji_racune,
    ukloni_administratora,
)
from .upravljanje import KLJUC_ZGRADE, kljuc_stana, samo_administrator, za_zgradu


def opis(korisnik):
    return f"{korisnik.get_full_name() or korisnik.username} ({korisnik.username})"


def korisnik_zgrade(request, pk):
    """Korisnik odabrane zgrade; superadministrator smije i korisnika bilo koje zgrade (spajanje među zgradama)."""
    if request.user.is_superuser:
        return get_object_or_404(Korisnik, pk=pk)
    return get_object_or_404(korisnici_zgrade(request.zgrada), pk=pk)


def stanovi_u_zgradi(korisnik, zgrada):
    danas = timezone.localdate()
    return sorted(
        (v.stan.broj_stana for v in korisnik.vlasnistva.all()
         if v.stan.zgrada_id == zgrada.pk and v.od_datuma <= danas and (v.do_datuma is None or v.do_datuma >= danas)),
        key=kljuc_stana,
    )


@za_zgradu
def korisnici(request):
    zgrada = request.zgrada
    svi = list(korisnici_zgrade(zgrada).prefetch_related("vlasnistva__stan", "uloge_u_zgradama"))
    administratori = set(zgrada.administratori.values_list("pk", flat=True))
    redovi = [{
        "k": k,
        "stanovi": ", ".join(stanovi_u_zgradi(k, zgrada)),
        "administrator": k.pk in administratori,
        "drugdje": not samo_u_zgradi(k, zgrada) and not k.is_superuser,
        "upravlja": smije_upravljati(request.user, k, zgrada),
    } for k in svi]
    skupine = isto_ime(svi)
    if request.user.is_superuser:
        # Superadministrator vidi i istoimene suvlasnike drugih zgrada.
        ovdje = {k.pk for k in svi}
        sa_stanom = Korisnik.objects.filter(is_active=True, vlasnistva__isnull=False).distinct()
        skupine = [s for s in isto_ime(sa_stanom) if any(k.pk in ovdje for k in s)] or skupine
    for skupina in skupine:
        for k in skupina:
            k.oznake_zgrada = ", ".join(sorted({v.stan.oznaka for v in k.vlasnistva.select_related("stan__zgrada")}))
    return render(request, "upravljanje/korisnici.html", {"redovi": redovi, "skupine": skupine})


@za_zgradu
def nova_lozinka(request, pk):
    korisnik = korisnik_zgrade(request, pk)
    if not smije_upravljati(request.user, korisnik, request.zgrada):
        raise PermissionDenied
    if request.method != "POST":
        return redirect("korisnici")
    lozinka = postavi_novu_lozinku(korisnik)
    Zapisnik.upisi(Zapisnik.Radnja.NOVA_LOZINKA, f"Nova lozinka za {opis(korisnik)}", request=request,
                   zgrada=request.zgrada, korisnik_id=korisnik.pk)
    return render(request, "upravljanje/nova_lozinka.html", {"korisnik": korisnik, "lozinka": lozinka})


@za_zgradu
def spajanje(request):
    zgrada = request.zgrada
    try:
        a = korisnik_zgrade(request, int(request.GET.get("a") or request.POST.get("a") or 0))
        b = korisnik_zgrade(request, int(request.GET.get("b") or request.POST.get("b") or 0))
    except ValueError:
        raise Http404
    ostaje_pk = request.POST.get("ostaje")
    ostaje, odlazi = (b, a) if ostaje_pk == str(b.pk) else (a, b)
    greska = None
    try:
        provjeri_spajanje(request.user, ostaje, odlazi, zgrada)
    except GreskaRacuna as e:
        greska = str(e)
    if request.method == "POST" and not greska and request.POST.get("potvrda") == "1":
        podaci = spoji_racune(ostaje, odlazi)
        Zapisnik.upisi(
            Zapisnik.Radnja.SPAJANJE, f"{opis(odlazi)} spojen u {opis(ostaje)}",
            request=request, zgrada=zgrada, **podaci,
        )
        messages.success(
            request,
            f"Računi su spojeni. {ostaje.get_full_name()} se prijavljuje kao {ostaje.username}; "
            f"račun {odlazi.username} je isključen.",
        )
        return redirect("korisnici")
    return render(request, "upravljanje/spajanje.html", {
        "racuni": [
            {"k": k, "stanovi": [v for v in k.vlasnistva.select_related("stan__zgrada").order_by("od_datuma")],
             "broj_ocitanja": k.ocitanja.count()}
            for k in (a, b)
        ],
        "a": a, "b": b, "ostaje": ostaje, "greska": greska,
    })


@za_zgradu
def administratori(request):
    zgrada = request.zgrada
    forma = NoviAdministratorForm(request.POST or None, zgrada=zgrada)
    if request.method == "POST":
        akcija = request.POST.get("akcija")
        if akcija == "ukloni":
            korisnik = get_object_or_404(zgrada.administratori, pk=request.POST.get("korisnik"))
            try:
                ukloni_administratora(korisnik, zgrada)
            except GreskaRacuna as e:
                messages.error(request, str(e))
            else:
                Zapisnik.upisi(Zapisnik.Radnja.ADMINISTRATOR, f"Uklonjen administrator {opis(korisnik)}",
                               request=request, zgrada=zgrada, korisnik_id=korisnik.pk)
                messages.success(request, f"{korisnik} više nije administrator zgrade.")
                if korisnik == request.user and not request.user.je_administrator:
                    logout(request)
                    return redirect("prijava")
            return redirect("administratori")
        if forma.is_valid():
            d = forma.cleaned_data
            lozinka = None
            with transaction.atomic():
                korisnik = d["postojeci"]
                if korisnik is None:
                    korisnik = Korisnik.objects.create_user(
                        d["korisnicko_ime"], email=d["email"], first_name=d["ime"], last_name=d["prezime"],
                    )
                    lozinka = postavi_novu_lozinku(korisnik)
                try:
                    dodaj_administratora(korisnik, zgrada)
                except GreskaRacuna as e:
                    messages.error(request, str(e))
                    return redirect("administratori")
            Zapisnik.upisi(Zapisnik.Radnja.ADMINISTRATOR, f"Dodan administrator {opis(korisnik)}",
                           request=request, zgrada=zgrada, korisnik_id=korisnik.pk)
            if lozinka:
                return render(request, "upravljanje/nova_lozinka.html", {
                    "korisnik": korisnik, "lozinka": lozinka, "administrator": True,
                })
            messages.success(request, f"{korisnik} je sada administrator zgrade.")
            return redirect("administratori")
    return render(request, "upravljanje/administratori.html", {
        "administratori": zgrada.administratori.order_by("last_name", "first_name"),
        "forma": forma,
    })


@za_zgradu
def stanovi(request):
    zgrada = request.zgrada
    forma = NoviStanForm(request.POST or None, zgrada=zgrada)
    if request.method == "POST" and forma.is_valid():
        d = forma.cleaned_data
        with transaction.atomic():
            stan = Stan.objects.create(zgrada=zgrada, broj_stana=d["broj_stana"], kat=d["kat"], napomena=d["napomena"])
            if d["pocetno_stanje"] is not None:
                Vodomjer.objects.create(stan=stan, serijski_broj=d["serijski_broj"], pocetno_stanje=d["pocetno_stanje"])
        Zapisnik.upisi(Zapisnik.Radnja.STAN, f"Dodan stan {stan.oznaka}", request=request, zgrada=zgrada,
                       stan=str(stan.uid))
        messages.success(request, f"Stan {stan.broj_stana} je dodan. Vlasnika upišite preko Promjena vlasnika.")
        return redirect("stan", pk=stan.pk)
    danas = timezone.localdate()
    redovi = []
    for stan in zgrada.stanovi.prefetch_related("vlasnistva__korisnik", "vodomjeri"):
        vlasnici = [v.korisnik for v in stan.vlasnistva.all()
                    if v.od_datuma <= danas and (v.do_datuma is None or v.do_datuma >= danas)]
        redovi.append({
            "stan": stan,
            "vlasnici": ", ".join(k.get_full_name() or k.username for k in vlasnici),
            "vodomjer": next((v for v in stan.vodomjeri.all() if v.aktivan), None),
        })
    redovi.sort(key=lambda r: kljuc_stana(r["stan"].broj_stana))
    return render(request, "upravljanje/stanovi.html", {"redovi": redovi, "forma": forma})


@za_zgradu
def zamjena_vodomjera(request, pk):
    stan = get_object_or_404(Stan, pk=pk, zgrada=request.zgrada)
    forma = ZamjenaVodomjeraForm(request.POST or None)
    if request.method == "POST" and forma.is_valid():
        d = forma.cleaned_data
        with transaction.atomic():
            stan.vodomjeri.filter(aktivan=True).update(aktivan=False)
            Vodomjer.objects.create(stan=stan, serijski_broj=d["serijski_broj"], pocetno_stanje=d["pocetno_stanje"])
        Zapisnik.upisi(Zapisnik.Radnja.STAN, f"Novi vodomjer u stanu {stan.oznaka}, početno stanje {d['pocetno_stanje']}",
                       request=request, zgrada=request.zgrada, stan=str(stan.uid))
        messages.success(request, "Novi vodomjer je upisan. Stari ostaje u povijesti.")
        return redirect("stan", pk=stan.pk)
    return render(request, "upravljanje/zamjena_vodomjera.html", {"stan": stan, "forma": forma})


@samo_administrator
def nova_zgrada(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    forma = ZgradaForm(request.POST or None)
    if request.method == "POST" and forma.is_valid():
        zgrada = forma.save()
        Postavke.ucitaj(zgrada)
        Zapisnik.upisi(Zapisnik.Radnja.ZGRADA, f"Dodana zgrada {zgrada.adresa} ({zgrada.oznaka})",
                       request=request, zgrada=zgrada, uid=str(zgrada.uid))
        request.session[KLJUC_ZGRADE] = zgrada.pk
        messages.success(request, f"Zgrada {zgrada.adresa} je dodana. Sada joj dodajte administratora.")
        return redirect("administratori")
    return render(request, "upravljanje/nova_zgrada.html", {"forma": forma})


@za_zgradu
def zapisnik(request):
    zapisi = Zapisnik.objects.filter(zgrada=request.zgrada).select_related("korisnik")[:300]
    return render(request, "upravljanje/zapisnik.html", {"zapisi": zapisi})


@za_zgradu
def ponisti(request, pk):
    if not request.user.is_superuser or request.method != "POST":
        raise PermissionDenied
    zapis = get_object_or_404(Zapisnik, pk=pk, radnja=Zapisnik.Radnja.SPAJANJE)
    if zapis.podaci.get("ponisteno"):
        messages.error(request, "Ovo spajanje je već poništeno.")
        return redirect("zapisnik")
    odlazi = ponisti_spajanje(zapis.podaci)
    zapis.podaci["ponisteno"] = True
    zapis.save(update_fields=["podaci"])
    Zapisnik.upisi(Zapisnik.Radnja.PONISTENO_SPAJANJE, f"Poništeno spajanje, {opis(odlazi)} ponovno aktivan",
                   request=request, zgrada=zapis.zgrada, zapis=zapis.pk)
    messages.success(request, f"Spajanje je poništeno; račun {odlazi.username} ponovno radi.")
    return redirect("zapisnik")
