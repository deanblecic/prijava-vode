from django import forms
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils import timezone

from .models import Korisnik, Postavke, Zgrada
from .rokovi import ODABIRI_DANA


class IspravakForm(forms.Form):
    novo_stanje = forms.DecimalField(label="Novo stanje (m³)", max_digits=10, decimal_places=3, min_value=0)
    napomena = forms.CharField(label="Napomena", max_length=500, required=False)


class RucniUnosForm(forms.Form):
    novo_stanje = forms.DecimalField(label="Novo stanje (m³)", max_digits=10, decimal_places=3, min_value=0)
    datum_ocitanja = forms.DateField(label="Datum očitanja", widget=forms.DateInput(attrs={"type": "date"}))
    fotografija = forms.ImageField(label="Fotografija (neobavezno)", required=False)
    napomena = forms.CharField(label="Napomena", max_length=500, required=False)


class PromjenaVlasnikaForm(forms.Form):
    od_datuma = forms.DateField(label="Novi vlasnik od", widget=forms.DateInput(attrs={"type": "date"}))
    postojeci = forms.ModelMultipleChoiceField(
        label="Postojeći korisnici",
        queryset=Korisnik.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )
    ime = forms.CharField(label="Ime", max_length=150, required=False)
    prezime = forms.CharField(label="Prezime", max_length=150, required=False)
    korisnicko_ime = forms.CharField(label="Korisničko ime", max_length=150, required=False)
    lozinka = forms.CharField(label="Lozinka", required=False, widget=forms.PasswordInput)
    deaktiviraj_stare = forms.BooleanField(
        label="Deaktiviraj račune starih vlasnika ako nemaju drugih stanova", required=False, initial=True
    )

    def __init__(self, *args, zgrada, **kwargs):
        super().__init__(*args, **kwargs)
        # Ponuđeni su samo suvlasnici ove zgrade; korisnici drugih zgrada se ne vide.
        self.fields["postojeci"].queryset = (
            Korisnik.objects.filter(is_active=True, vlasnistva__stan__zgrada=zgrada)
            .distinct().order_by("last_name", "first_name")
        )

    def clean(self):
        podaci = super().clean()
        novi = any(podaci.get(p) for p in ["ime", "prezime", "korisnicko_ime", "lozinka"])
        if novi:
            for polje in ["ime", "prezime", "korisnicko_ime", "lozinka"]:
                if not podaci.get(polje):
                    self.add_error(polje, "Obavezno za novog korisnika.")
            ime = podaci.get("korisnicko_ime")
            if ime and Korisnik.objects.filter(username=ime).exists():
                self.add_error("korisnicko_ime", "To korisničko ime već postoji.")
            if podaci.get("lozinka"):
                try:
                    validate_password(podaci["lozinka"])
                except forms.ValidationError as e:
                    self.add_error("lozinka", e)
        if not novi and not podaci.get("postojeci"):
            raise forms.ValidationError("Odaberite postojećeg korisnika ili upišite novog.")
        return podaci


class ZamjenskiOcitavacForm(forms.Form):
    """Osoba koja očitava vodomjer umjesto vlasnika: postojeći korisnik zgrade ili novi račun."""

    postojeci = forms.ModelChoiceField(
        label="Postojeći korisnik", queryset=Korisnik.objects.none(), required=False,
        empty_label="– odaberite –",
    )
    ime = forms.CharField(label="Ime", max_length=150, required=False)
    prezime = forms.CharField(label="Prezime", max_length=150, required=False)
    korisnicko_ime = forms.CharField(label="Korisničko ime", max_length=150, required=False)
    lozinka = forms.CharField(label="Lozinka", required=False, widget=forms.PasswordInput)

    NOVI = ["ime", "prezime", "korisnicko_ime", "lozinka"]

    def __init__(self, *args, stan, **kwargs):
        from .racuni import korisnici_zgrade

        super().__init__(*args, **kwargs)
        danas = timezone.localdate()
        vlasnici = stan.vlasnistva.filter(od_datuma__lte=danas).filter(
            Q(do_datuma__isnull=True) | Q(do_datuma__gte=danas)
        ).values("korisnik")
        # Ponuđeni su samo aktivni korisnici ove zgrade koji već ne mogu očitati ovaj stan.
        self.fields["postojeci"].queryset = (
            korisnici_zgrade(stan.zgrada).filter(is_active=True)
            .exclude(pk__in=stan.zamjenski_ocitavaci.values("korisnik"))
            .exclude(pk__in=vlasnici)
        )
        self.fields["postojeci"].label_from_instance = lambda k: f"{k.get_full_name() or k.username} ({k.username})"

    def clean(self):
        podaci = super().clean()
        novi = any(podaci.get(p) for p in self.NOVI)
        if novi and podaci.get("postojeci"):
            raise forms.ValidationError("Odaberite postojećeg korisnika ili upišite novog, ne oboje.")
        if novi:
            for polje in self.NOVI:
                if not podaci.get(polje):
                    self.add_error(polje, "Obavezno za novog korisnika.")
            ime = podaci.get("korisnicko_ime")
            if ime and Korisnik.objects.filter(username=ime).exists():
                self.add_error("korisnicko_ime", "To korisničko ime već postoji.")
            if podaci.get("lozinka"):
                try:
                    validate_password(podaci["lozinka"])
                except forms.ValidationError as e:
                    self.add_error("lozinka", e)
        elif not podaci.get("postojeci"):
            raise forms.ValidationError("Odaberite postojećeg korisnika ili upišite novog.")
        return podaci


class PostavkeForm(forms.ModelForm):
    podsjetnik_dani = forms.TypedMultipleChoiceField(
        label="Odabrani dani", choices=ODABIRI_DANA, coerce=int, required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    obavijest_dani = forms.TypedMultipleChoiceField(
        label="Odabrani dani", choices=ODABIRI_DANA, coerce=int, required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Postavke
        fields = [
            "rok_dan", "nakon_roka", "referentni_dan",
            "podsjetnik_raspored", "dan_ocitanja", "podsjetnik_broj_dana", "podsjetnik_dani", "sat_podsjetnika",
            "email_stanarima",
            "obavijest_raspored", "obavijest_od_dana", "obavijest_broj_dana", "obavijest_dani", "sat_obavijesti",
            "email_obavijesti",
        ]
        widgets = {"nakon_roka": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for polje in ("podsjetnik_dani", "obavijest_dani"):
            self.initial[polje] = [str(d) for d in (self.initial.get(polje) or [])]

    def clean_email_obavijesti(self):
        adrese = [a.strip() for a in self.cleaned_data["email_obavijesti"].split(",") if a.strip()]
        for adresa in adrese:
            forms.EmailField().clean(adresa)
        return ", ".join(adrese)

    def clean(self):
        podaci = super().clean()
        rok = podaci.get("rok_dan")
        if rok is None:
            return podaci
        referentni = podaci.get("referentni_dan")
        if referentni and rok and referentni > rok:
            self.add_error("referentni_dan", f"Ne može biti iza krajnjeg roka ({rok}.).")
        for raspored, od_dana, dani in (
            ("podsjetnik_raspored", "dan_ocitanja", "podsjetnik_dani"),
            ("obavijest_raspored", "obavijest_od_dana", "obavijest_dani"),
        ):
            odabran = podaci.get(raspored)
            if odabran == "od_dana" and rok and (podaci.get(od_dana) or 0) > rok:
                self.add_error(od_dana, f"Mora biti najkasnije dan roka ({rok}.).")
            if odabran == "prilagodeno" and not podaci.get(dani):
                self.add_error(dani, "Odaberite barem jedan dan.")
            if odabran == "prilagodeno" and rok:
                kasni = [d for d in podaci.get(dani) or [] if d > rok]
                if kasni:
                    self.add_error(dani, f"Dani iza roka ({', '.join(f'{d}.' for d in kasni)}) se ne šalju.")
        return podaci


class NoviAdministratorForm(forms.Form):
    postojeci = forms.ModelChoiceField(
        label="Postojeći suvlasnik zgrade", queryset=Korisnik.objects.none(), required=False,
    )
    ime = forms.CharField(label="Ime", max_length=150, required=False)
    prezime = forms.CharField(label="Prezime", max_length=150, required=False)
    korisnicko_ime = forms.CharField(label="Korisničko ime", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", required=False)

    def __init__(self, *args, zgrada, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["postojeci"].queryset = (
            Korisnik.objects.filter(is_active=True, vlasnistva__stan__zgrada=zgrada)
            .exclude(uloge_u_zgradama__zgrada=zgrada).distinct().order_by("last_name", "first_name")
        )

    def clean(self):
        podaci = super().clean()
        novi = [p for p in ["ime", "prezime", "korisnicko_ime", "email"] if podaci.get(p)]
        if podaci.get("postojeci") and novi:
            raise forms.ValidationError("Odaberite postojećeg suvlasnika ili upišite novu osobu, ne oboje.")
        if not podaci.get("postojeci"):
            if not novi:
                raise forms.ValidationError("Odaberite postojećeg suvlasnika ili upišite novu osobu.")
            for polje in ["ime", "prezime", "korisnicko_ime"]:
                if not podaci.get(polje):
                    self.add_error(polje, "Obavezno za novu osobu.")
            ime = podaci.get("korisnicko_ime")
            if ime and Korisnik.objects.filter(username__iexact=ime).exists():
                self.add_error("korisnicko_ime", "To korisničko ime već postoji.")
        return podaci


class NoviStanForm(forms.Form):
    broj_stana = forms.CharField(label="Broj stana", max_length=10)
    kat = forms.IntegerField(label="Kat", required=False)
    napomena = forms.CharField(label="Napomena", max_length=200, required=False)
    serijski_broj = forms.CharField(label="Serijski broj vodomjera", max_length=50, required=False)
    pocetno_stanje = forms.DecimalField(
        label="Početno stanje vodomjera (m³)", max_digits=10, decimal_places=3, min_value=0, required=False,
        help_text="Prazno ako stan nema vodomjer koji se očitava.",
    )

    def __init__(self, *args, zgrada, **kwargs):
        super().__init__(*args, **kwargs)
        self.zgrada = zgrada

    def clean_broj_stana(self):
        broj = self.cleaned_data["broj_stana"].strip()
        if self.zgrada.stanovi.filter(broj_stana=broj).exists():
            raise forms.ValidationError("Stan s tim brojem u ovoj zgradi već postoji.")
        return broj


class ZamjenaVodomjeraForm(forms.Form):
    serijski_broj = forms.CharField(label="Serijski broj novog vodomjera", max_length=50, required=False)
    pocetno_stanje = forms.DecimalField(
        label="Stanje novog vodomjera kod ugradnje (m³)", max_digits=10, decimal_places=3, min_value=0,
    )


class ZgradaForm(forms.ModelForm):
    class Meta:
        model = Zgrada
        fields = ["ulica", "kucni_broj", "postanski_broj", "grad", "oznaka"]
