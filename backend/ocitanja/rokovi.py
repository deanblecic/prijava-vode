"""Krajnji rok očitanja zgrade i dani na koje se šalju podsjetnici suvlasnicima i obavijesti administratoru.

Razdoblje očitanja traje od 1. u mjesecu do dana roka. Dani slanja računaju se uvijek unutar tog razdoblja.
"""
import calendar
import datetime

RASPOREDI = [
    ("prvi", "Samo prvi dan"),
    ("prvi_rok", "Prvi dan i na dan roka"),
    ("rok", "Samo na dan roka"),
    ("predzadnji_rok", "Dan prije roka i na dan roka"),
    ("svaki_dan", "Svaki dan od 1. do roka"),
    ("od_dana", "Svaki dan od odabranog dana do roka"),
    ("prije_roka", "Svaki dan zadnjih nekoliko dana do roka"),
    ("prilagodeno", "Samo odabrani dani"),
]

# Odabrani dani: 1–28 su dani u mjesecu, 0 je dan roka, a -1 i -2 dan i dva dana prije roka.
ODABIRI_DANA = (
    [("0", "na dan roka"), ("-1", "dan prije roka"), ("-2", "2 dana prije roka")]
    + [(str(d), f"{d}.") for d in range(1, 29)]
)


def zadnji_u_mjesecu(mjesec):
    return mjesec.replace(day=calendar.monthrange(mjesec.year, mjesec.month)[1])


def dan_roka(rok_dan, mjesec):
    """Dan u mjesecu do kojeg se predaje očitanje; 0 znači zadnji dan u mjesecu."""
    return rok_dan or zadnji_u_mjesecu(mjesec).day


def datum_roka(postavke, mjesec):
    return mjesec.replace(day=dan_roka(postavke.rok_dan, mjesec))


def dani_slanja(raspored, rok, *, od_dana=1, broj_dana=1, dani=()):
    """Dani u mjesecu (1..rok) na koje se šalje poruka po odabranom rasporedu."""
    if raspored == "prvi":
        odabrani = {1}
    elif raspored == "prvi_rok":
        odabrani = {1, rok}
    elif raspored == "rok":
        odabrani = {rok}
    elif raspored == "predzadnji_rok":
        odabrani = {rok - 1, rok}
    elif raspored == "svaki_dan":
        odabrani = set(range(1, rok + 1))
    elif raspored == "od_dana":
        odabrani = set(range(min(od_dana, rok), rok + 1))
    elif raspored == "prije_roka":
        odabrani = set(range(rok - max(broj_dana, 1) + 1, rok + 1))
    elif raspored == "prilagodeno":
        odabrani = {int(d) if int(d) > 0 else rok + int(d) for d in dani}
    else:
        odabrani = set()
    return sorted(d for d in odabrani if 1 <= d <= rok)


def dani_podsjetnika(postavke, mjesec):
    return dani_slanja(
        postavke.podsjetnik_raspored, dan_roka(postavke.rok_dan, mjesec),
        od_dana=postavke.dan_ocitanja, broj_dana=postavke.podsjetnik_broj_dana, dani=postavke.podsjetnik_dani,
    )


def dani_obavijesti(postavke, mjesec):
    return dani_slanja(
        postavke.obavijest_raspored, dan_roka(postavke.rok_dan, mjesec),
        od_dana=postavke.obavijest_od_dana, broj_dana=postavke.obavijest_broj_dana, dani=postavke.obavijest_dani,
    )


def rok_istekao(postavke, razdoblje, danas):
    """Je li danas iza roka za očitanje mjeseca razdoblje (prvi dan mjeseca)."""
    return danas > datum_roka(postavke, razdoblje)
