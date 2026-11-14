"""Očitanje stanja vodomjera s fotografije pomoću Claudea (Anthropic API).

Mobitel prvo čita brojilo sam (ML Kit), ali na mutnim, nakošenim i starim vodomjerima to često ne
uspije. Server tada fotografiju šalje Claudeu, koji vodomjer čita kao čovjek: razlikuje crne i
crvene kotačiće, preskače serijski broj i natpise s kućišta te dovršava kotačić koji se okreće.

Uključuje se postavljanjem ANTHROPIC_API_KEY; bez ključa se ništa ne šalje.
"""

import base64
import json
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings

logger = logging.getLogger(__name__)

UPUTA = """Na fotografiji je stanski vodomjer za vodu. Pročitaj stanje brojila u m³.

- Crni kotačići su cijeli kubni metri, crveni kotačići su decimale (litre). Vrati tri decimale.
- Ako ima četiri crvena kotačića, zanemari četvrti. Ako su decimale prikazane samo kazaljkama,
  pročitaj kazaljke x0,1, x0,01 i x0,001 ako se vide, inače stavi decimale 000.
- Kotačić koji je između dvije znamenke čitaj kao manju znamenku, osim kad je prethodni kotačić
  (desno od njega) već prešao na 0 - tada uzmi veću.
- Ne čitaj serijski broj, godinu proizvodnje ni oznake s kućišta (npr. Q3 2,5, Z-14-1016, x 0,0001).
{prethodno}
Ako brojilo uopće nije vidljivo, stavi stanje na null."""

SHEMA = {
    "type": "object",
    "properties": {
        "stanje": {
            "type": ["string", "null"],
            "description": "Stanje u m³ s točkom i tri decimale, npr. 784.806",
        },
        "sigurno": {"type": "boolean", "description": "Jesu li sve znamenke jasno čitljive"},
    },
    "required": ["stanje", "sigurno"],
    "additionalProperties": False,
}


class CitacNijeUkljucen(Exception):
    pass


def ukljucen():
    return bool(settings.ANTHROPIC_API_KEY)


def _klijent():
    import anthropic

    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60.0, max_retries=2)


def _vrsta_slike(podaci):
    if podaci[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if podaci[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if podaci[:4] == b"RIFF" and podaci[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def procitaj(slika, prethodno=None):
    """Vrati (stanje, sigurno) ili (None, False) ako se broj ne može pročitati.

    slika: bajtovi fotografije (JPEG/PNG/WebP, najviše nekoliko MB).
    prethodno: prethodno stanje (Decimal) kao pomoć pri čitanju poluzakrenutih kotačića.
    """
    if not ukljucen():
        raise CitacNijeUkljucen()

    import anthropic

    napomena = ""
    if prethodno is not None and prethodno > 0:
        napomena = (
            f"- Prethodno stanje ovog vodomjera bilo je {prethodno:.3f} m³; novo je obično malo veće. "
            "Ipak pročitaj ono što piše na brojilu, ne pogađaj."
        )
    try:
        odgovor = _klijent().beta.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": SHEMA},
            },
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": _vrsta_slike(slika),
                            "data": base64.standard_b64encode(slika).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": UPUTA.format(prethodno=napomena)},
                ],
            }],
        )
    except anthropic.APIError:
        logger.exception("Claude nije očitao vodomjer")
        return None, False

    if odgovor.stop_reason == "refusal":
        logger.warning("Claude je odbio očitanje: %s", odgovor.stop_details)
        return None, False
    tekst = "".join(blok.text for blok in odgovor.content if blok.type == "text")
    try:
        podaci = json.loads(tekst)
        if podaci.get("stanje") is None:
            return None, False
        stanje = Decimal(str(podaci["stanje"]).replace(",", ".")).quantize(Decimal("0.001"))
    except (ValueError, InvalidOperation, TypeError, AttributeError):
        logger.warning("Neispravan odgovor pri očitanju vodomjera: %r", tekst[:200])
        return None, False
    if stanje < 0 or stanje >= Decimal("10000000"):
        return None, False
    return stanje, bool(podaci.get("sigurno"))
