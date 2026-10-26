from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import Korisnik, KorisnikStan, Ocitanje, Stan, Vodomjer


class KorisnikStanInline(admin.TabularInline):
    model = KorisnikStan
    extra = 0


@admin.register(Korisnik)
class KorisnikAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "uloga", "is_active"]
    list_filter = ["uloga", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("Prijava vode", {"fields": ["uloga", "telefon"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Podaci", {"fields": ["first_name", "last_name", "uloga"]}),
    )
    inlines = [KorisnikStanInline]


class VodomjerInline(admin.TabularInline):
    model = Vodomjer
    extra = 0


@admin.register(Stan)
class StanAdmin(admin.ModelAdmin):
    list_display = ["broj_stana", "kat", "napomena"]
    inlines = [KorisnikStanInline, VodomjerInline]


@admin.register(Vodomjer)
class VodomjerAdmin(admin.ModelAdmin):
    list_display = ["stan", "serijski_broj", "oznaka", "pocetno_stanje", "aktivan"]
    list_filter = ["aktivan"]


@admin.register(Ocitanje)
class OcitanjeAdmin(admin.ModelAdmin):
    list_display = [
        "razdoblje_mjesec", "datum_ocitanja", "broj_stana", "ime_prezime",
        "prethodno_stanje", "novo_stanje", "razlika", "status", "za_provjeru",
    ]
    list_filter = ["status", "za_provjeru", "razdoblje"]
    search_fields = ["vodomjer__stan__broj_stana", "korisnik__first_name", "korisnik__last_name"]
    readonly_fields = ["razlika", "slika", "stvoreno", "izmijenjeno"]
    list_select_related = ["vodomjer__stan", "korisnik"]

    @admin.display(description="Mjesec", ordering="razdoblje")
    def razdoblje_mjesec(self, obj):
        return f"{obj.razdoblje:%m/%Y}"

    @admin.display(description="Stan", ordering="vodomjer__stan__broj_stana")
    def broj_stana(self, obj):
        return obj.vodomjer.stan.broj_stana

    @admin.display(description="Ime i prezime")
    def ime_prezime(self, obj):
        return obj.korisnik.get_full_name()

    @admin.display(description="Fotografija")
    def slika(self, obj):
        if not obj.fotografija:
            return "–"
        return format_html('<a href="{0}"><img src="{0}" style="max-height:300px"></a>', obj.fotografija.url)
