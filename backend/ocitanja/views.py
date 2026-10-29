from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Ocitanje, Postavke
from .serializers import (
    OcitanjeSerializer,
    PredajaOcitanjaSerializer,
    StanSerializer,
)
from .servisi import GreskaOcitanja, predaj_ocitanje, verzija_aplikacije


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def prijava(request):
    korisnik = authenticate(
        request,
        username=request.data.get("korisnicko_ime", ""),
        password=request.data.get("lozinka", ""),
    )
    if korisnik is None:
        return Response(
            {"kod": "neispravna_prijava", "poruka": "Pogrešno korisničko ime ili lozinka."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    token, _ = Token.objects.get_or_create(user=korisnik)
    return Response({"token": token.key})


@api_view(["POST"])
def odjava(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def ja(request):
    korisnik = request.user
    context = {"request": request, "sada": timezone.now()}
    postavke = Postavke.ucitaj()
    return Response({
        "korisnicko_ime": korisnik.username,
        "ime": korisnik.first_name,
        "prezime": korisnik.last_name,
        "stanovi": StanSerializer(korisnik.aktivni_stanovi(), many=True, context=context).data,
        "podsjetnik": {"dan": postavke.dan_ocitanja, "sat": postavke.sat_podsjetnika},
        # Aplikacija uspoređuje sa svojom verzijom i nudi nadogradnju.
        "aplikacija": {"verzija": verzija_aplikacije()},
    })


@api_view(["GET", "POST"])
def ocitanja(request):
    if request.method == "GET":
        moja = (
            Ocitanje.objects.filter(vodomjer__stan__in=request.user.aktivni_stanovi())
            .select_related("vodomjer__stan", "korisnik")[:36]
        )
        return Response(OcitanjeSerializer(moja, many=True, context={"request": request}).data)

    unos = PredajaOcitanjaSerializer(data=request.data)
    unos.is_valid(raise_exception=True)
    try:
        ocitanje = predaj_ocitanje(request.user, **unos.validated_data)
    except GreskaOcitanja as greska:
        kod_statusa = status.HTTP_403_FORBIDDEN if greska.kod == "nema_prava" else status.HTTP_409_CONFLICT
        return Response({"kod": greska.kod, "poruka": greska.poruka}, status=kod_statusa)
    return Response(
        OcitanjeSerializer(ocitanje, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )
