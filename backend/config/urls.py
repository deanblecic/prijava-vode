from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from ocitanja import upravljanje

admin.site.site_header = "Očitanja vodomjera"
admin.site.site_title = "Očitanja vodomjera"
admin.site.index_title = "Administracija"

urlpatterns = [
    path("", upravljanje.pregled, name="pregled"),
    path("zgrade/", upravljanje.zgrade, name="zgrade"),
    path("zgrade/odaberi/", upravljanje.odaberi_zgradu, name="odaberi_zgradu"),
    path("prijava/", upravljanje.Prijava.as_view(), name="prijava"),
    path("odjava/", auth_views.LogoutView.as_view(next_page="prijava"), name="odjava"),
    path("ocitanje/<int:pk>/", upravljanje.ocitanje_detalj, name="ocitanje"),
    path("stan/<int:pk>/", upravljanje.stan_detalj, name="stan"),
    path("stan/<int:pk>/promjena-vlasnika/", upravljanje.promjena_vlasnika, name="promjena_vlasnika"),
    path("postavke/", upravljanje.postavke, name="postavke"),
    path("izvoz/", upravljanje.izvoz_excel, name="izvoz"),
    path("media/<path:putanja>", upravljanje.fotografija, name="fotografija"),
    path("aplikacija/", upravljanje.aplikacija, name="aplikacija"),
    path("aplikacija/ocitanje-vode.apk", upravljanje.aplikacija_apk, name="aplikacija_apk"),
    path("admin/", admin.site.urls),
    path("api/", include("ocitanja.urls")),
]
