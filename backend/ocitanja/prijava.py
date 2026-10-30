"""Web prijava: lozinka, zatim kod iz Google Authenticatora; prvi put i postavljanje Authenticatora."""
import time

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Korisnik, Zapisnik
from .sigurnost import (
    SESIJA_DVA_KORAKA,
    blokirano,
    nova_tajna,
    novi_rezervni_kodovi,
    poruka_blokade,
    provjeri_kod,
    qr_kod_svg,
    zabiljezi_neuspjeh,
)

U_TIJEKU = "prijava_u_tijeku"
ROK_DRUGOG_KORAKA = 300  # sekundi između lozinke i koda


class Prijava(auth_views.LoginView):
    """Prvi korak: korisničko ime i lozinka. Prijava se završava tek s kodom iz Authenticatora."""

    template_name = "upravljanje/prijava.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if blokirano(request.POST.get("username"), request):
            return self.render_to_response(self.get_context_data(form=self.get_form(), blokada=poruka_blokade()))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        zabiljezi_neuspjeh(self.request, self.request.POST.get("username"), "web")
        return super().form_invalid(form)

    def form_valid(self, form):
        korisnik = form.get_user()
        # Web je za sada samo za administratore; suvlasnici očitanje unose u aplikaciji.
        if not korisnik.je_administrator:
            return self.render_to_response(self.get_context_data(form=form, samo_aplikacija=True))
        self.request.session[U_TIJEKU] = {
            "id": korisnik.pk, "vrijeme": time.time(), "dalje": self.get_success_url(),
            "backend": korisnik.backend,
        }
        return redirect("prijava_kod")


def korisnik_u_tijeku(request):
    podaci = request.session.get(U_TIJEKU)
    if not podaci or time.time() - podaci["vrijeme"] > ROK_DRUGOG_KORAKA:
        return None, None
    return Korisnik.objects.filter(pk=podaci["id"], is_active=True).first(), podaci


def prijava_kod(request):
    korisnik, podaci = korisnik_u_tijeku(request)
    if korisnik is None:
        request.session.pop(U_TIJEKU, None)
        messages.info(request, "Prijava je istekla. Upišite ponovno korisničko ime i lozinku.")
        return redirect("prijava")
    postavljanje = not korisnik.totp_tajna
    if postavljanje:
        # Tajna se sprema tek kad korisnik upiše prvi ispravan kod, da ne ostane polovično postavljena.
        tajna = podaci.get("nova_tajna") or nova_tajna()
        if podaci.get("nova_tajna") != tajna:
            podaci["nova_tajna"] = tajna
            request.session[U_TIJEKU] = podaci
    greska = None
    if request.method == "POST":
        if blokirano(korisnik.username, request):
            greska = poruka_blokade()
        elif provjeri_kod(korisnik, request.POST.get("kod"), tajna=tajna if postavljanje else None):
            rezervni = None
            if postavljanje:
                korisnik.totp_tajna = tajna
                rezervni = novi_rezervni_kodovi(korisnik)
                korisnik.save(update_fields=["totp_tajna", "rezervni_kodovi"])
                Zapisnik.upisi(Zapisnik.Radnja.DVA_KORAKA, f"{korisnik.username} je postavio Google Authenticator",
                               request=request, korisnik=korisnik)
            korisnik.backend = podaci["backend"]
            login(request, korisnik)
            request.session[SESIJA_DVA_KORAKA] = True
            request.session.pop(U_TIJEKU, None)
            Zapisnik.upisi(Zapisnik.Radnja.PRIJAVA, f"Prijava na web: {korisnik.username}", request=request)
            if rezervni:
                return render(request, "upravljanje/rezervni_kodovi.html", {"kodovi": rezervni})
            dalje = podaci.get("dalje") or "/"
            if not url_has_allowed_host_and_scheme(dalje, allowed_hosts={request.get_host()}):
                dalje = "/"
            return redirect(dalje)
        else:
            zabiljezi_neuspjeh(request, korisnik.username, "kod")
            greska = "Kod nije ispravan. Upišite novi kod iz aplikacije."
    return render(request, "upravljanje/prijava_kod.html", {
        "korisnik": korisnik,
        "postavljanje": postavljanje,
        "qr": qr_kod_svg(tajna, korisnik) if postavljanje else None,
        "tajna": tajna if postavljanje else None,
        "greska": greska,
    })


@login_required
def promjena_lozinke(request):
    """Nova lozinka; obavezna kad je lozinku postavio administrator."""
    forma = SetPasswordForm(request.user, request.POST or None)
    for polje in forma.fields.values():
        polje.widget.attrs["autocomplete"] = "new-password"
    if request.method == "POST" and forma.is_valid():
        korisnik = forma.save()
        korisnik.mora_promijeniti_lozinku = False
        korisnik.save(update_fields=["mora_promijeniti_lozinku"])
        update_session_auth_hash(request, korisnik)
        Zapisnik.upisi(Zapisnik.Radnja.PROMJENA_LOZINKE, f"{korisnik.username} je promijenio lozinku", request=request)
        messages.success(request, "Lozinka je promijenjena.")
        return redirect("pregled")
    return render(request, "upravljanje/promjena_lozinke.html", {"forma": forma})
