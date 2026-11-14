"""Excel predložak za uvoz zgrade: zgrada, stanovi s vodomjerima, suvlasnici i zamjenski očitavači.

Isti opis stupaca koristi i uvoz (uvoz.py), pa predložak i čitanje tablice ne mogu otići svaki na svoju stranu.
"""
from dataclasses import dataclass
from datetime import date

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

REDOVA = 500  # do kojeg retka vrijede padajući izbornici i provjere u Excelu


@dataclass(frozen=True)
class Stupac:
    kljuc: str
    naslov: str
    obavezno: bool
    sirina: int
    opis: str
    vrsta: str  # tekst, cijeli, decimalni, datum, dane, stan
    najvise: int = 0  # tekst: najviše znakova; cijeli: gornja granica
    najmanje: int = 0  # cijeli: donja granica


ZGRADA = [
    Stupac("oznaka", "Oznaka zgrade", True, 16, "Kratka oznaka koju ćete koristiti u aplikaciji, npr. RI-ALB-2 (grad-ulica-broj). Najviše 20 znakova, mora biti jedinstvena.", "tekst", 20),
    Stupac("ulica", "Ulica", True, 28, "Naziv ulice bez kućnog broja, npr. Moše Albaharija. Najviše 150 znakova.", "tekst", 150),
    Stupac("kucni_broj", "Kućni broj", True, 12, "Npr. 2 ili 12A. Najviše 20 znakova.", "tekst", 20),
    Stupac("postanski_broj", "Poštanski broj", True, 14, "Npr. 51000.", "tekst", 10),
    Stupac("grad", "Grad", True, 16, "Npr. Rijeka.", "tekst", 100),
    Stupac("admin_ime", "Ime administratora", True, 18, "Osoba koja će u aplikaciji upravljati ovom zgradom (pregled očitanja, stanovi, podsjetnici).", "tekst", 150),
    Stupac("admin_prezime", "Prezime administratora", True, 22, "", "tekst", 150),
    Stupac("admin_email", "E-mail administratora", True, 30, "Obavezno: na njega stižu popis neočitanih vodomjera i zaboravljena lozinka.", "tekst", 254),
    Stupac("admin_telefon", "Telefon administratora", False, 18, "Npr. 091 123 4567.", "tekst", 30),
    Stupac("rok_dan", "Krajnji rok očitanja", False, 16, "Dan u mjesecu (1–28) do kojeg suvlasnici predaju očitanje. Prazno = zadnji dan u mjesecu.", "cijeli", 28, 1),
    Stupac("referentni_dan", "Referentni dan očitanja", False, 18, "Dan u mjesecu (1–31) kada bi trebalo očitati vodomjer. Prazno = nije postavljen.", "cijeli", 31, 1),
]
STANOVI = [
    Stupac("broj_stana", "Broj stana", True, 11, "Kako se stan vodi u zgradi, npr. 1, 01 ili 12A. Svaki broj samo jednom. Najviše 10 znakova.", "tekst", 10),
    Stupac("kat", "Kat", False, 7, "Cijeli broj: 0 = prizemlje, -1 = podrum, 1 = prvi kat ...", "cijeli", 99, -5),
    Stupac("ima_vodomjer", "Ima vodomjer", True, 13, "DA ako stan ima vlastiti vodomjer koji se očitava. NE za prostore bez vodomjera (npr. prostor u vlasništvu grada bez brojila).", "dane"),
    Stupac("pocetno_stanje", "Početno stanje vodomjera (m³)", False, 18, "Stanje vodomjera na dan uvoza, s najviše 3 decimale, npr. 1574,25. Obavezno ako stan ima vodomjer; od njega se računa prva potrošnja.", "decimalni"),
    Stupac("serijski_broj", "Serijski broj vodomjera", False, 20, "Broj otisnut na vodomjeru. Pomaže kod provjere i zamjene vodomjera. Najviše 50 znakova.", "tekst", 50),
    Stupac("mjesto_vodomjera", "Mjesto vodomjera", False, 18, "Gdje se vodomjer nalazi, npr. kupaonica, kuhinja, hodnik. Najviše 50 znakova.", "tekst", 50),
    Stupac("napomena", "Napomena", False, 34, "Bilo što važno za administratora, npr. 'ključ kod susjeda'. Najviše 200 znakova.", "tekst", 200),
]
SUVLASNICI = [
    Stupac("broj_stana", "Broj stana", True, 11, "Broj stana s lista Stanovi. Ako stan ima više suvlasnika, svaki je u svom retku s istim brojem stana. Ako osoba ima više stanova, upišite je u više redaka s istim imenom i e-mailom.", "stan"),
    Stupac("ime", "Ime", False, 16, "Ime osobe. Prazno samo za pravne osobe i ustanove (npr. Grad Rijeka).", "tekst", 150),
    Stupac("prezime", "Prezime ili naziv", True, 26, "Prezime osobe ili naziv pravne osobe (npr. Grad Rijeka).", "tekst", 150),
    Stupac("email", "E-mail", False, 30, "Preporučeno: na njega stižu podsjetnici i poveznica za zaboravljenu lozinku. Po e-mailu se prepoznaje ista osoba u više stanova.", "tekst", 254),
    Stupac("telefon", "Telefon", False, 18, "Npr. 091 123 4567. Najviše 30 znakova.", "tekst", 30),
    Stupac("od_datuma", "Suvlasnik od", False, 14, "Datum od kada je osoba suvlasnik (DD.MM.GGGG.). Prazno = od dana uvoza.", "datum"),
    Stupac("prijava", "Prijava u aplikaciju", True, 14, "DA ako osoba sama predaje očitanja u aplikaciji (dobiva korisničko ime i lozinku). NE za pravne osobe, preminule ili osobe koje ne koriste aplikaciju.", "dane"),
]
ZAMJENSKI = [
    Stupac("broj_stana", "Broj stana", True, 11, "Stan za koji ova osoba predaje očitanje umjesto suvlasnika (npr. susjed starije osobe bez mobitela).", "stan"),
    Stupac("ime", "Ime", True, 16, "", "tekst", 150),
    Stupac("prezime", "Prezime", True, 22, "", "tekst", 150),
    Stupac("email", "E-mail", False, 30, "Ako je osoba već suvlasnik u zgradi, upišite isti e-mail (ili isto ime i prezime) pa se koristi njezin postojeći račun.", "tekst", 254),
    Stupac("telefon", "Telefon", False, 18, "", "tekst", 30),
]

LISTOVI = [
    ("Zgrada", ZGRADA, True),
    ("Stanovi", STANOVI, True),
    ("Suvlasnici", SUVLASNICI, True),
    ("Zamjenski očitavači", ZAMJENSKI, False),
]
TEKSTUALNI = {"broj_stana", "postanski_broj", "kucni_broj", "telefon", "admin_telefon", "serijski_broj"}

PRIMJER = {
    "Zgrada": [["RI-ALB-2", "Moše Albaharija", "2", "51000", "Rijeka", "Ivana", "Horvat", "ivana.horvat@primjer.hr", "091 123 4567", None, 26]],
    "Stanovi": [
        ["01", 0, "DA", 314.5, "ZR-2019-00431", "kupaonica", ""],
        ["02", 0, "NE", None, "", "", "Poslovni prostor Grada, bez vodomjera"],
        ["03", 1, "DA", 1574.25, "ZR-2019-00433", "kuhinja", ""],
        ["04", 1, "DA", 2554, "ZR-2019-00434", "kupaonica", "Ključ kod susjeda u stanu 03"],
        ["05", 2, "DA", 1039.002, "", "hodnik", ""],
    ],
    "Suvlasnici": [
        ["01", "Marko", "Kovačević", "marko.kovacevic@primjer.hr", "098 765 4321", None, "DA"],
        ["02", "", "Grad Rijeka", "", "", None, "NE"],
        ["03", "Sanja", "Njirić", "sanja.njiric@primjer.hr", "", date(2015, 3, 1), "DA"],
        ["03", "Petar", "Njirić", "", "", date(2015, 3, 1), "DA"],
        ["04", "Nataša", "Prelić Gerdević", "", "051 222 333", None, "DA"],
        ["05", "Sanja", "Njirić", "sanja.njiric@primjer.hr", "", date(2020, 9, 15), "DA"],
    ],
    "Zamjenski očitavači": [
        ["04", "Sanja", "Njirić", "sanja.njiric@primjer.hr", ""],
    ],
}

PLAVA = PatternFill("solid", fgColor="1F4E79")
ZUTA = PatternFill("solid", fgColor="FFF2CC")
SIVA = PatternFill("solid", fgColor="F2F2F2")
RUB = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
BIJELO = Font(bold=True, color="FFFFFF")


def naslov_stupca(stupac):
    return stupac.naslov + (" *" if stupac.obavezno else "")


def provjera(ws, slovo, s):
    if s.vrsta == "tekst":
        dv = DataValidation(type="textLength", operator="lessThanOrEqual", formula1=str(s.najvise))
        dv.error = f"Najviše {s.najvise} znakova."
    elif s.vrsta == "cijeli":
        dv = DataValidation(type="whole", operator="between", formula1=str(s.najmanje), formula2=str(s.najvise))
        dv.error = f"Upišite cijeli broj od {s.najmanje} do {s.najvise}."
    elif s.vrsta == "decimalni":
        dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0")
        dv.error = "Upišite broj (npr. 1574,25), bez jedinice m³."
    elif s.vrsta == "datum":
        dv = DataValidation(type="date", operator="between", formula1="DATE(1950,1,1)", formula2="DATE(2100,12,31)")
        dv.error = "Upišite datum, npr. 01.03.2015."
    elif s.vrsta == "dane":
        dv = DataValidation(type="list", formula1='"DA,NE"')
        dv.error = "Odaberite DA ili NE."
    else:  # stan
        dv = DataValidation(type="list", formula1=f"=Stanovi!$A$2:$A${REDOVA}")
        dv.error = "Broj stana mora postojati na listu Stanovi."
    dv.errorTitle = s.naslov
    dv.showErrorMessage = True
    if s.opis:
        dv.promptTitle = s.naslov[:32]
        dv.prompt = s.opis[:255]
        dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(f"{slovo}2:{slovo}{REDOVA}")


def list_podataka(wb, ime, stupci, redovi):
    ws = wb.create_sheet(ime)
    ws.sheet_properties.tabColor = "1F4E79"
    for i, s in enumerate(stupci, 1):
        slovo = get_column_letter(i)
        c = ws.cell(1, i, naslov_stupca(s))
        c.font, c.fill, c.border = BIJELO, PLAVA, RUB
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        if s.opis:
            c.comment = Comment(s.opis, "Predložak")
            c.comment.width, c.comment.height = 300, 120
        ws.column_dimensions[slovo].width = s.sirina
        provjera(ws, slovo, s)
        # Brojevi stanova i telefoni kao tekst, da Excel ne pojede vodeće nule.
        oblik = "@" if s.kljuc in TEKSTUALNI or s.vrsta == "stan" else {
            "datum": "DD.MM.YYYY.", "decimalni": "#,##0.000"}.get(s.vrsta)
        if oblik:
            for r in range(2, REDOVA + 1):
                ws.cell(r, i).number_format = oblik
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "A2"
    for r, red in enumerate(redovi, 2):
        for i, v in enumerate(red, 1):
            ws.cell(r, i, v).border = RUB


def list_uputa(wb, primjer):
    ws = wb.active
    ws.title = "Upute"
    ws.sheet_properties.tabColor = "70AD47"
    for slovo, sirina in zip("ABC", (26, 12, 95)):
        ws.column_dimensions[slovo].width = sirina
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    red = 1
    naslov = Font(bold=True, size=12, color="1F4E79")

    def pisi(tekst, font=None, fill=None, visina=None):
        nonlocal red
        ws.merge_cells(start_row=red, start_column=1, end_row=red, end_column=3)
        c = ws.cell(red, 1, tekst)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if font:
            c.font = font
        if fill:
            c.fill = fill
        if visina or len(tekst) > 110:
            ws.row_dimensions[red].height = visina or 32
        red += 1

    pisi("Uvoz zgrade u aplikaciju Prijava vode", Font(bold=True, size=16, color="1F4E79"), visina=26)
    if primjer:
        pisi("OVO JE POPUNJENI PRIMJER s izmišljenim podacima. Za stvarnu zgradu koristite prazni predložak.",
             Font(bold=True, color="C00000"), ZUTA, 20)
    pisi("Tablicu popunjava administrator ili upravitelj zgrade i šalje je natrag. Aplikacija iz nje sama stvara zgradu, "
         "stanove, vodomjere s početnim stanjem i korisničke račune suvlasnika, a korisnička imena i lozinke dobivate "
         "u zasebnoj tablici za podjelu suvlasnicima.", visina=48)
    red += 1
    pisi("Kako popuniti", naslov)
    for k in [
        "1. List Zgrada: jedan redak s adresom zgrade i podacima administratora.",
        "2. List Stanovi: jedan redak po stanu (ili poslovnom prostoru), s vodomjerom i njegovim stanjem na dan uvoza.",
        "3. List Suvlasnici: jedan redak po osobi i stanu. Stan s dva suvlasnika ima dva retka; osoba s dva stana također ima dva retka "
        "(isto ime, prezime i e-mail), a dobiva jedan račun za oba stana.",
        "4. List Zamjenski očitavači (neobavezno): osobe koje predaju očitanje umjesto suvlasnika, npr. susjed starije osobe.",
        "5. Stupci označeni zvjezdicom (*) su obavezni. Kliknite na naslov stupca za objašnjenje.",
        "6. Ne mijenjajte nazive listova ni nazive stupaca. Ne spajajte ćelije i ne dodajte retke iznad naslova.",
        "7. Brojeve stanova pišite jednako na svim listovima (01 i 1 nisu isti stan).",
    ]:
        pisi(k)
    red += 1
    pisi("Opis stupaca", naslov)
    for ime, stupci, _ in LISTOVI:
        for i, t in enumerate((f"List {ime}", "Obavezno", "Opis"), 1):
            c = ws.cell(red, i, t)
            c.font, c.fill, c.border = BIJELO, PLAVA, RUB
        red += 1
        for s in stupci:
            celije = [ws.cell(red, 1, s.naslov), ws.cell(red, 2, "DA" if s.obavezno else "ne"), ws.cell(red, 3, s.opis)]
            for c in celije:
                c.border = RUB
                c.alignment = Alignment(wrap_text=True, vertical="top")
                if red % 2:
                    c.fill = SIVA
            celije[1].alignment = Alignment(horizontal="center", vertical="top")
            if s.obavezno:
                celije[1].font = Font(bold=True)
            if len(s.opis) > 95:
                ws.row_dimensions[red].height = 15 * (len(s.opis) // 95 + 1)
            red += 1
        red += 1
    pisi("Što aplikacija napravi s tablicom", naslov)
    for t in [
        "• Provjeri cijelu tablicu prije upisa: ako ijedan redak ima grešku (npr. stan bez suvlasnika ili vodomjer bez stanja), "
        "ništa se ne upisuje i dobivate popis grešaka po listu i retku.",
        "• Svaki suvlasnik s prijavom (DA) dobiva korisničko ime oblika prezime.ime i privremenu lozinku koju mijenja kod prve prijave.",
        "• Osoba čiji e-mail već postoji u aplikaciji (npr. suvlasnik u drugoj zgradi) zadržava svoj račun i lozinku.",
        "• Suvlasnici bez prijave (NE) vide se u pregledu kao vlasnici, ali se ne mogu prijaviti.",
        "• Stanovi bez vodomjera ne ulaze u mjesečni pregled očitanja.",
        "• Ako zgrada već postoji u aplikaciji, dodaju se samo novi stanovi; stanovi koji već postoje ne uvoze se ponovno.",
    ]:
        pisi(t)


def napravi_predlozak(primjer=False):
    wb = Workbook()
    list_uputa(wb, primjer)
    for ime, stupci, _ in LISTOVI:
        list_podataka(wb, ime, stupci, PRIMJER[ime] if primjer else [])
    return wb
