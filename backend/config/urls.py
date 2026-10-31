from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import TemplateView

from ocitanja import korisnici, lozinka, prijava, upravljanje

admin.site.site_header = "Očitanja vodomjera"
admin.site.site_title = "Očitanja vodomjera"
admin.site.index_title = "Administracija"

urlpatterns = [
    path("", upravljanje.pregled, name="pregled"),
    path("zgrade/", upravljanje.zgrade, name="zgrade"),
    path("zgrade/odaberi/", upravljanje.odaberi_zgradu, name="odaberi_zgradu"),
    path("zgrade/nova/", korisnici.nova_zgrada, name="nova_zgrada"),
    path("korisnici/", korisnici.korisnici, name="korisnici"),
    path("korisnici/<int:pk>/nova-lozinka/", korisnici.nova_lozinka, name="nova_lozinka"),
    path("korisnici/spoji/", korisnici.spajanje, name="spajanje"),
    path("administratori/", korisnici.administratori, name="administratori"),
    path("stanovi/", korisnici.stanovi, name="stanovi"),
    path("stan/<int:pk>/vodomjer/", korisnici.zamjena_vodomjera, name="zamjena_vodomjera"),
    path("zapisnik/", korisnici.zapisnik, name="zapisnik"),
    path("zapisnik/<int:pk>/ponisti/", korisnici.ponisti, name="ponisti_spajanje"),
    path("prijava/", prijava.Prijava.as_view(), name="prijava"),
    path("prijava/kod/", prijava.prijava_kod, name="prijava_kod"),
    path("prijava/zaboravljena-lozinka/", lozinka.ZaboravljenaLozinka.as_view(), name="zaboravljena_lozinka"),
    path("prijava/zaboravljena-lozinka/poslano/", TemplateView.as_view(
        template_name="upravljanje/zaboravljena_lozinka_poslano.html"), name="zaboravljena_lozinka_poslano"),
    path("prijava/nova-lozinka/<uidb64>/<token>/", lozinka.NovaLozinkaIzLinka.as_view(), name="nova_lozinka_iz_linka"),
    path("prijava/nova-lozinka/gotovo/", TemplateView.as_view(
        template_name="upravljanje/nova_lozinka_gotovo.html"), name="zaboravljena_lozinka_gotovo"),
    path("lozinka/", prijava.promjena_lozinke, name="promjena_lozinke"),
    path("racun/", lozinka.moj_racun, name="moj_racun"),
    path("odjava/", auth_views.LogoutView.as_view(next_page="prijava"), name="odjava"),
    path("ocitanje/<int:pk>/", upravljanje.ocitanje_detalj, name="ocitanje"),
    path("stan/<int:pk>/", upravljanje.stan_detalj, name="stan"),
    path("stan/<int:pk>/promjena-vlasnika/", upravljanje.promjena_vlasnika, name="promjena_vlasnika"),
    path("postavke/", upravljanje.postavke, name="postavke"),
    path("izvoz/", upravljanje.izvoz_excel, name="izvoz"),
    path("media/<path:putanja>", upravljanje.fotografija, name="fotografija"),
    path("aplikacija/", upravljanje.aplikacija, name="aplikacija"),
    path("aplikacija/ocitanje-vode.apk", upravljanje.aplikacija_apk, name="aplikacija_apk"),
    path(settings.ADMIN_PUTANJA, admin.site.urls),
    path("api/", include("ocitanja.urls")),
]
