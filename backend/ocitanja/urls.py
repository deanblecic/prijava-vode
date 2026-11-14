from django.urls import path

from . import pwa, views

urlpatterns = [
    path("prijava/", views.prijava, name="api-prijava"),
    path("odjava/", views.odjava, name="api-odjava"),
    path("ja/", views.ja, name="api-ja"),
    path("lozinka/", views.lozinka, name="api-lozinka"),
    path("ocitanja/", views.ocitanja, name="api-ocitanja"),
    path("obavijesti/pretplata/", pwa.pretplata, name="api-pretplata"),
    path("obavijesti/proba/", pwa.proba, name="api-proba"),
]
