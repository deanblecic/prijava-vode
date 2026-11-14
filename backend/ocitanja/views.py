from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import citac
from .models import Ocitanje, Zapisnik, Zgrada
from .serializers import (
    OcitanjeSerializer,
    PredajaOcitanjaSerializer,
    StanSerializer,
    ZgradaSerializer,
)
from .servisi import GreskaOcitanja, predaj_ocitanje, verzija_aplikacije
from .upravljanje import kljuc_stana
from .sigurnost import blokirano, poruka_blokade, zabiljezi_neuspjeh


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def prijava(request):
    korisnicko_ime = str(request.data.get("korisnicko_ime", ""))
    if blokirano(korisnicko_ime, request):
        return Response({"kod": "blokirano", "poruka": poruka_blokade()}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    korisnik = authenticate(request, username=korisnicko_ime, password=str(request.data.get("lozinka", "")))
    if korisnik is None:
        zabiljezi_neuspjeh(request, korisnicko_ime, "aplikacija")
        return Response(
            {"kod": "neispravna_prijava", "poruka": "Pogrešno korisničko ime ili lozinka."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    token, _ = Token.objects.get_or_create(user=korisnik)
    Zapisnik.upisi(Zapisnik.Radnja.PRIJAVA, f"Prijava u aplikaciju: {korisnik.username}", request=request, korisnik=korisnik)
    return Response({"token": token.key, "mora_promijeniti_lozinku": korisnik.mora_promijeniti_lozinku})


@api_view(["POST"])
def odjava(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def lozinka(request):
    """Suvlasnik postavlja svoju lozinku; obavezno kad mu je lozinku postavio administrator."""
    korisnik = request.user
    nova = str(request.data.get("nova_lozinka", ""))
    if not korisnik.mora_promijeniti_lozinku and not korisnik.check_password(str(request.data.get("stara_lozinka", ""))):
        return Response({"kod": "stara_lozinka", "poruka": "Trenutna lozinka nije točna."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(nova, korisnik)
    except ValidationError as greska:
        return Response({"kod": "slaba_lozinka", "poruka": " ".join(greska.messages)}, status=status.HTTP_400_BAD_REQUEST)
    korisnik.set_password(nova)
    korisnik.mora_promijeniti_lozinku = False
    korisnik.save()
    Zapisnik.upisi(Zapisnik.Radnja.PROMJENA_LOZINKE, f"{korisnik.username} je promijenio lozinku u aplikaciji",
                   request=request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def ja(request):
    korisnik = request.user
    context = {"request": request, "sada": timezone.now()}
    vlastiti = set(korisnik.aktivni_stanovi().values_list("pk", flat=True))
    # Vlastiti stanovi prvi, zatim stanovi za koje očitava umjesto vlasnika.
    stanovi = sorted(
        korisnik.stanovi_za_ocitanje().select_related("zgrada"),
        key=lambda s: (s.pk not in vlastiti, s.zgrada_id, kljuc_stana(s.broj_stana)),
    )
    context["vlastiti"] = vlastiti
    zgrade = Zgrada.objects.filter(stanovi__in=[s.pk for s in stanovi]).distinct()
    # Aplikacije starije od podrške za više zgrada znaju samo za jedan podsjetnik.
    prvi = ZgradaSerializer(zgrade[0]).data["podsjetnik"] if zgrade else {"dan": 26, "sat": 9}
    return Response({
        "korisnicko_ime": korisnik.username,
        "mora_promijeniti_lozinku": korisnik.mora_promijeniti_lozinku,
        "ime": korisnik.first_name,
        "prezime": korisnik.last_name,
        "zgrade": ZgradaSerializer(zgrade, many=True).data,
        "stanovi": StanSerializer(stanovi, many=True, context=context).data,
        "podsjetnik": prvi,
        # Aplikacija uspoređuje sa svojom verzijom i nudi nadogradnju.
        "aplikacija": {"verzija": verzija_aplikacije()},
    })


@api_view(["GET", "POST"])
def ocitanja(request):
    if request.method == "GET":
        moja = (
            Ocitanje.objects.filter(vodomjer__stan__in=request.user.stanovi_za_ocitanje())
            .select_related("vodomjer__stan", "korisnik")[:36]
        )
        return Response(OcitanjeSerializer(moja, many=True, context={"request": request}).data)

    unos = PredajaOcitanjaSerializer(data=request.data)
    unos.is_valid(raise_exception=True)
    try:
        ocitanje = predaj_ocitanje(request.user, samo_vlasnik=True, **unos.validated_data)
    except GreskaOcitanja as greska:
        kod_statusa = status.HTTP_403_FORBIDDEN if greska.kod == "nema_prava" else status.HTTP_409_CONFLICT
        return Response({"kod": greska.kod, "poruka": greska.poruka}, status=kod_statusa)
    return Response(
        OcitanjeSerializer(ocitanje, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def procitaj(request):
    """Stanje vodomjera s fotografije (Claude), za prijedlog u polju za upis; ništa se ne sprema."""
    if not citac.ukljucen():
        return Response({"kod": "nije_ukljuceno"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    fotografija = request.FILES.get("fotografija")
    if fotografija is None or fotografija.size > 8 * 1024 * 1024:
        return Response({"kod": "neispravna_fotografija"}, status=status.HTTP_400_BAD_REQUEST)
    kljuc = f"citanja:{request.user.pk}:{timezone.localdate():%Y%m%d}"
    cache.add(kljuc, 0, 24 * 3600)
    if cache.incr(kljuc) > settings.CITANJA_DNEVNO:
        return Response({"kod": "previse_citanja"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    prethodno = None
    try:
        prethodno = Decimal(request.data.get("prethodno_stanje") or "0")
    except InvalidOperation:
        pass
    stanje, sigurno = citac.procitaj(fotografija.read(), prethodno)
    return Response({"stanje": str(stanje) if stanje is not None else None, "sigurno": sigurno})
