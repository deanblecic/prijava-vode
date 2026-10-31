"""Zaboravljena lozinka administratora (jednokratni link na e-mail) i e-mail adresa vlastitog računa.

Link vrijedi PASSWORD_RESET_TIMEOUT sekundi i prestaje vrijediti čim se lozinka promijeni. Odgovor na zahtjev
uvijek je isti, da se ne može provjeravati čija je adresa u sustavu. Nova lozinka ne zaobilazi drugi korak:
prijava i dalje traži kod iz Google Authenticatora.
"""
import hashlib
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import Korisnik, Zapisnik, ip_klijenta


def sazetak_adrese(email):
    """Adresa se u zapisniku ne čuva čitljiva, samo toliko da se prebroje zahtjevi za istu adresu."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{email.strip().lower()}".encode()).hexdigest()[:24]


def previse_zahtjeva(request, email):
    od = timezone.now() - timedelta(minutes=60)
    zahtjevi = Zapisnik.objects.filter(radnja=Zapisnik.Radnja.ZABORAVLJENA_LOZINKA, vrijeme__gte=od,
                                       podaci__zahtjev=True)
    ip = ip_klijenta(request)
    po_adresi = zahtjevi.filter(podaci__email=sazetak_adrese(email)).count()
    po_ip = zahtjevi.filter(ip=ip).count() if ip else 0
    return po_adresi >= settings.RESET_LOZINKE_PO_ADRESI or po_ip >= settings.RESET_LOZINKE_PO_IP


def obavijesti_o_promjeni(korisnik, request, kako):
    """Vlasniku računa javlja da je lozinka promijenjena, da odmah vidi ako to nije bio on."""
    if not korisnik.email:
        return
    vrijeme = timezone.localtime()
    send_mail(
        "Lozinka za Očitanja vodomjera je promijenjena",
        f"Poštovani/a {korisnik.get_full_name() or korisnik.username},\n\n"
        f"lozinka vašeg računa {korisnik.username} promijenjena je {vrijeme:%d.%m.%Y.} u {vrijeme:%H:%M} ({kako}),\n"
        f"s adrese {ip_klijenta(request) or 'nepoznato'}.\n\n"
        "Ako to niste bili vi, odmah se javite glavnom administratoru.\n",
        None,
        [korisnik.email],
        fail_silently=True,
    )


class ZaboravljenaLozinkaForm(PasswordResetForm):
    email = forms.EmailField(label="E-mail adresa računa", max_length=254,
                             widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))

    def get_users(self, email):
        """Samo aktivni administratori (glavni i administratori zgrada) s tom adresom."""
        for korisnik in Korisnik.objects.filter(email__iexact=email.strip(), is_active=True):
            if korisnik.has_usable_password() and korisnik.je_administrator:
                yield korisnik


class ZaboravljenaLozinka(auth_views.PasswordResetView):
    form_class = ZaboravljenaLozinkaForm
    template_name = "upravljanje/zaboravljena_lozinka.html"
    email_template_name = "upravljanje/email_zaboravljena_lozinka.txt"
    subject_template_name = "upravljanje/email_zaboravljena_lozinka_naslov.txt"
    success_url = reverse_lazy("zaboravljena_lozinka_poslano")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        if previse_zahtjeva(self.request, email):
            # Isti odgovor kao i inače, ali bez slanja: nitko ne može zatrpavati tuđi sandučić.
            Zapisnik.upisi(Zapisnik.Radnja.ZABORAVLJENA_LOZINKA, "Previše zahtjeva za novu lozinku, ništa nije poslano",
                           request=self.request, email=sazetak_adrese(email), zahtjev=False)
            return redirect(self.success_url)
        korisnici = list(form.get_users(email))
        Zapisnik.upisi(
            Zapisnik.Radnja.ZABORAVLJENA_LOZINKA,
            f"Zatražen link za novu lozinku ({'poslan' if korisnici else 'adresa nije administratorska'})",
            request=self.request, korisnik=korisnici[0] if len(korisnici) == 1 else None,
            email=sazetak_adrese(email), zahtjev=True,
        )
        return super().form_valid(form)


class NovaLozinkaIzLinka(auth_views.PasswordResetConfirmView):
    template_name = "upravljanje/nova_lozinka_iz_linka.html"
    success_url = reverse_lazy("zaboravljena_lozinka_gotovo")
    post_reset_login = False

    def get_form(self, form_class=None):
        forma = super().get_form(form_class)
        for polje in forma.fields.values():
            polje.widget.attrs["autocomplete"] = "new-password"
        return forma

    def form_valid(self, form):
        odgovor = super().form_valid(form)
        korisnik = self.user
        korisnik.mora_promijeniti_lozinku = False
        korisnik.save(update_fields=["mora_promijeniti_lozinku"])
        # Prijave u aplikaciji sa starom lozinkom prestaju vrijediti.
        Token.objects.filter(user=korisnik).delete()
        Zapisnik.upisi(Zapisnik.Radnja.ZABORAVLJENA_LOZINKA, f"{korisnik.username} je postavio novu lozinku preko e-maila",
                       request=self.request, korisnik=korisnik)
        obavijesti_o_promjeni(korisnik, self.request, "preko linka za zaboravljenu lozinku")
        return odgovor


class EmailRacunaForm(forms.Form):
    email = forms.EmailField(label="E-mail adresa", required=True,
                             help_text="Na nju stižu link za zaboravljenu lozinku i obavijesti o neočitanim vodomjerima.")
    lozinka = forms.CharField(label="Trenutna lozinka", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, korisnik, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.korisnik = korisnik

    def clean_lozinka(self):
        if not self.korisnik.check_password(self.cleaned_data["lozinka"]):
            raise forms.ValidationError("Lozinka nije točna.")
        return self.cleaned_data["lozinka"]


@login_required
def moj_racun(request):
    """E-mail za zaboravljenu lozinku; promjena traži trenutnu lozinku, a stara adresa dobiva obavijest."""
    korisnik = request.user
    forma = EmailRacunaForm(korisnik, request.POST or None, initial={"email": korisnik.email})
    if request.method == "POST" and forma.is_valid():
        stara = korisnik.email
        nova = forma.cleaned_data["email"].strip()
        if nova.lower() != stara.lower():
            korisnik.email = nova
            korisnik.save(update_fields=["email"])
            Zapisnik.upisi(Zapisnik.Radnja.EMAIL, f"{korisnik.username} je promijenio e-mail", request=request)
            if stara:
                send_mail(
                    "E-mail adresa za Očitanja vodomjera je promijenjena",
                    f"Adresa računa {korisnik.username} promijenjena je s {stara} na {nova}.\n\n"
                    "Ako to niste bili vi, odmah se javite glavnom administratoru.\n",
                    None, [stara], fail_silently=True,
                )
        messages.success(request, "E-mail adresa je spremljena.")
        return redirect("moj_racun")
    return render(request, "upravljanje/moj_racun.html", {"forma": forma})
