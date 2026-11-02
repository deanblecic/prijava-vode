"""Web aplikacija za suvlasnike (PWA): radi u Safariju na iPhoneu i u svakom drugom pregledniku.

Nakon „Dodaj na početni zaslon” otvara se kao obična aplikacija, bez adresne trake. Koristi isti API kao
Android aplikacija (/api/, prijava tokenom), pa vrijede ista pravila predaje očitanja.
"""
import hashlib
from functools import lru_cache
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.http import require_GET
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import web_push
from .models import PushPretplata

MAPA = Path(__file__).resolve().parent
DATOTEKE = ["app/app.js", "app/app.css", "app/ikona-192.png", "app/ikona-512.png", "app/ikona-maskable-512.png",
            "app/apple-touch-icon.png"]
NAZIV = "Očitanje vode"
BOJA = "#1f6feb"
POZADINA = "#f6f7f9"

# Fotografija iz kamere prikazuje se prije slanja (blob:), a kamera se smije koristiti na ovoj stranici.
CSP_APLIKACIJE = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)


@lru_cache(maxsize=1)
def verzija():
    """Sažetak datoteka aplikacije: kad se bilo koja promijeni, service worker osvježi spremljene kopije."""
    sazetak = hashlib.sha256()
    for ime in DATOTEKE:
        sazetak.update((MAPA / "static" / ime).read_bytes())
    for ime in ("stanar/app.html", "stanar/sw.js"):
        sazetak.update((MAPA / "templates" / ime).read_bytes())
    return sazetak.hexdigest()[:12]


def _bez_spremanja(odgovor):
    odgovor["Cache-Control"] = "no-cache"
    return odgovor


@require_GET
def aplikacija(request):
    odgovor = render(request, "stanar/app.html", {
        "vapid": web_push.javni_kljuc(),
        "verzija": verzija(),
        "boja": BOJA,
    })
    odgovor["Content-Security-Policy"] = CSP_APLIKACIJE
    odgovor["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=()"
    return _bez_spremanja(odgovor)


@require_GET
def manifest(request):
    podaci = {
        "id": "/app/",
        "name": NAZIV,
        "short_name": NAZIV,
        "description": "Mjesečno očitanje vodomjera u zgradi: fotografija, stanje i podsjetnik na rok.",
        "lang": "hr",
        "start_url": "/app/",
        "scope": "/app/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": POZADINA,
        "theme_color": BOJA,
        "icons": [
            {"src": static("app/ikona-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("app/ikona-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("app/ikona-maskable-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }
    odgovor = JsonResponse(podaci, json_dumps_params={"ensure_ascii": False})
    odgovor["Content-Type"] = "application/manifest+json"
    return _bez_spremanja(odgovor)


@require_GET
def service_worker(request):
    odgovor = render(request, "stanar/sw.js", {
        "verzija": verzija(),
        "datoteke": [static(ime) for ime in DATOTEKE],
    }, content_type="text/javascript; charset=utf-8")
    odgovor["Service-Worker-Allowed"] = "/app/"
    return _bez_spremanja(odgovor)


# --- Obavijesti (API, prijava tokenom kao u Android aplikaciji) ----------------------------------

class PretplataSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)
    p256dh = serializers.CharField(max_length=200, required=False)
    auth = serializers.CharField(max_length=100, required=False)
    uredaj = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def to_internal_value(self, podaci):
        # Preglednik daje PushSubscription.toJSON(): {"endpoint", "keys": {"p256dh", "auth"}}.
        if isinstance(podaci, dict) and isinstance(podaci.get("keys"), dict):
            podaci = {**podaci, **podaci["keys"]}
        return super().to_internal_value(podaci)

    def validate_endpoint(self, endpoint):
        if not endpoint.startswith("https://"):
            raise serializers.ValidationError("Adresa obavijesti mora biti https.")
        return endpoint


@api_view(["POST", "DELETE"])
def pretplata(request):
    unos = PretplataSerializer(data=request.data)
    unos.is_valid(raise_exception=True)
    podaci = unos.validated_data
    if request.method == "DELETE":
        PushPretplata.objects.filter(korisnik=request.user, endpoint=podaci["endpoint"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if not podaci.get("p256dh") or not podaci.get("auth"):
        return Response({"kod": "nepotpuno", "poruka": "Nedostaju ključevi pretplate."},
                        status=status.HTTP_400_BAD_REQUEST)
    # Isti mobitel nakon prijave drugog suvlasnika prelazi na njega.
    PushPretplata.objects.update_or_create(endpoint=podaci["endpoint"], defaults={
        "korisnik": request.user, "p256dh": podaci["p256dh"], "auth": podaci["auth"],
        "uredaj": podaci["uredaj"][:200],
    })
    return Response(status=status.HTTP_201_CREATED)


@api_view(["POST"])
def proba(request):
    """Probna obavijest na sve uređaje prijavljenog korisnika."""
    broj = web_push.posalji_korisniku(
        request.user, NAZIV, "Obavijesti rade. Podsjetit ćemo vas kad bude vrijeme za očitanje.", oznaka="proba",
    )
    if not broj:
        return Response({"kod": "nije_poslano", "poruka": "Obavijest nije poslana. Uključite obavijesti ponovno."},
                        status=status.HTTP_409_CONFLICT)
    return Response({"uredaja": broj})

