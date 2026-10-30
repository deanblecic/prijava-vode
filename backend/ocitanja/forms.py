from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Korisnik, Postavke, Zgrada


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


class PostavkeForm(forms.ModelForm):
    class Meta:
        model = Postavke
        fields = ["dan_ocitanja", "sat_podsjetnika", "email_obavijesti"]

    def clean_email_obavijesti(self):
        adrese = [a.strip() for a in self.cleaned_data["email_obavijesti"].split(",") if a.strip()]
        for adresa in adrese:
            forms.EmailField().clean(adresa)
        return ", ".join(adrese)


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
