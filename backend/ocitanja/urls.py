from django.urls import path

from . import views

urlpatterns = [
    path("prijava/", views.prijava, name="api-prijava"),
    path("odjava/", views.odjava, name="api-odjava"),
    path("ja/", views.ja, name="api-ja"),
    path("ocitanja/", views.ocitanja, name="api-ocitanja"),
]
