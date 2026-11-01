"""Web Push obavijesti za web aplikaciju (iPhone od iOS-a 16.4, Android Chrome, računala).

Bez vanjskih servisa i dodatnih paketa osim cryptography: poruka se šifrira po RFC 8291 (aes128gcm),
a server se pregledniku predstavlja VAPID ključem (RFC 8292). Ključ se izvodi iz DJANGO_SECRET_KEY,
pa ga ne treba posebno postavljati; VAPID_PRIVATNI_KLJUC ga može zadati izravno.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
from django.conf import settings

log = logging.getLogger(__name__)

# Red krivulje P-256; privatni ključ mora biti u rasponu 1..N-1.
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
TRAJANJE_PORUKE = 4 * 24 * 3600  # koliko dugo push servis čuva poruku za isključen mobitel


class PretplataIstekla(Exception):
    """Push servis kaže da pretplata više ne postoji (korisnik je ugasio obavijesti ili obrisao aplikaciju)."""


def b64u(podaci):
    return base64.urlsafe_b64encode(podaci).rstrip(b"=").decode()


def iz_b64u(tekst):
    tekst = tekst.strip()
    return base64.urlsafe_b64decode(tekst + "=" * (-len(tekst) % 4))


def privatni_kljuc():
    zadani = getattr(settings, "VAPID_PRIVATNI_KLJUC", "")
    if zadani:
        broj = int.from_bytes(iz_b64u(zadani), "big")
    else:
        sazetak = hmac.new(settings.SECRET_KEY.encode(), b"prijava-vode:vapid", hashlib.sha256).digest()
        broj = int.from_bytes(sazetak, "big") % (_N - 1) + 1
    return ec.derive_private_key(broj, ec.SECP256R1())


def _javni_bajtovi(kljuc):
    return kljuc.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def javni_kljuc():
    """Javni VAPID ključ (base64url) koji preglednik treba za pretplatu (applicationServerKey)."""
    return b64u(_javni_bajtovi(privatni_kljuc()))


def vapid_zaglavlje(endpoint, kljuc=None, sada=None):
    kljuc = kljuc or privatni_kljuc()
    dijelovi = urlsplit(endpoint)
    tvrdnje = {
        "aud": f"{dijelovi.scheme}://{dijelovi.netloc}",
        "exp": int(sada or time.time()) + 12 * 3600,
        "sub": f"mailto:{settings.KONTAKT_EMAIL}",
    }
    zaglavlje = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    tijelo = b64u(json.dumps(tvrdnje, separators=(",", ":")).encode())
    za_potpis = f"{zaglavlje}.{tijelo}".encode()
    r, s = decode_dss_signature(kljuc.sign(za_potpis, ec.ECDSA(hashes.SHA256())))
    potpis = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={zaglavlje}.{tijelo}.{potpis}, k={b64u(_javni_bajtovi(kljuc))}"


def _hkdf(sol, ikm, info, duljina):
    return HKDF(algorithm=hashes.SHA256(), length=duljina, salt=sol, info=info).derive(ikm)


def sifriraj(poruka, p256dh, auth, *, sol=None, kljuc_posiljatelja=None):
    """Tijelo poruke šifrirano za jednu pretplatu (RFC 8291, aes128gcm, jedan zapis)."""
    javni_primatelja = iz_b64u(p256dh)
    tajna_primatelja = iz_b64u(auth)
    sol = sol or os.urandom(16)
    kljuc_posiljatelja = kljuc_posiljatelja or ec.generate_private_key(ec.SECP256R1())
    javni_posiljatelja = _javni_bajtovi(kljuc_posiljatelja)
    zajednicka = kljuc_posiljatelja.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), javni_primatelja)
    )
    ikm = _hkdf(tajna_primatelja, zajednicka, b"WebPush: info\x00" + javni_primatelja + javni_posiljatelja, 32)
    kljuc = _hkdf(sol, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(sol, ikm, b"Content-Encoding: nonce\x00", 12)
    sifrirano = AESGCM(kljuc).encrypt(nonce, poruka + b"\x02", None)
    zaglavlje = sol + struct.pack("!IB", 4096, len(javni_posiljatelja)) + javni_posiljatelja
    return zaglavlje + sifrirano


def desifriraj(tijelo, privatni_primatelja, auth):
    """Obrnuto od sifriraj; služi testovima kao preglednik."""
    sol, velicina_id = tijelo[:16], tijelo[20]
    javni_posiljatelja = tijelo[21:21 + velicina_id]
    javni_primatelja = _javni_bajtovi(privatni_primatelja)
    zajednicka = privatni_primatelja.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), javni_posiljatelja)
    )
    ikm = _hkdf(iz_b64u(auth), zajednicka, b"WebPush: info\x00" + javni_primatelja + javni_posiljatelja, 32)
    kljuc = _hkdf(sol, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(sol, ikm, b"Content-Encoding: nonce\x00", 12)
    otvoreno = AESGCM(kljuc).decrypt(nonce, tijelo[21 + velicina_id:], None)
    return otvoreno.rstrip(b"\x00")[:-1]


def posalji(pretplata, naslov, tekst, url="/app/", oznaka="podsjetnik"):
    """Šalje jednu obavijest. Diže PretplataIstekla kad je treba obrisati, a druge greške propušta."""
    poruka = json.dumps({"naslov": naslov, "tekst": tekst, "url": url, "oznaka": oznaka}).encode()
    zahtjev = urllib.request.Request(
        pretplata.endpoint,
        data=sifriraj(poruka, pretplata.p256dh, pretplata.auth),
        method="POST",
        headers={
            "Authorization": vapid_zaglavlje(pretplata.endpoint),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TRAJANJE_PORUKE),
            "Urgency": "normal",
        },
    )
    try:
        with urllib.request.urlopen(zahtjev, timeout=15) as odgovor:
            return odgovor.status
    except urllib.error.HTTPError as greska:
        if greska.code in (404, 410):
            raise PretplataIstekla(pretplata.endpoint) from greska
        raise


def posalji_korisniku(korisnik, naslov, tekst, url="/app/", oznaka="podsjetnik"):
    """Šalje na sve uređaje korisnika; istekle pretplate briše. Vraća broj uređaja koji su je primili."""
    poslano = 0
    for pretplata in list(korisnik.push_pretplate.all()):
        try:
            posalji(pretplata, naslov, tekst, url, oznaka)
            poslano += 1
        except PretplataIstekla:
            pretplata.delete()
        except Exception:
            log.exception("Push obavijest korisniku %s nije poslana", korisnik.username)
    return poslano
