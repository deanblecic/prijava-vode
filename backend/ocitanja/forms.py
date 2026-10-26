from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Korisnik


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
        queryset=Korisnik.objects.filter(is_active=True).order_by("last_name", "first_name"),
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
