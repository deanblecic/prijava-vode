from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import AdministratorZgrade, Korisnik, KorisnikStan, Ocitanje, Postavke, Stan, Vodomjer, Zgrada

# Django administracija ne zna za zgrade, pa je smije koristiti samo superadministrator.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser


class KorisnikStanInline(admin.TabularInline):
    model = KorisnikStan
    extra = 0


@admin.register(Korisnik)
class KorisnikAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "is_superuser", "is_active"]
    list_filter = ["is_superuser", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("Prijava vode", {"fields": ["telefon"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Podaci", {"fields": ["first_name", "last_name"]}),
    )
    inlines = [KorisnikStanInline]


class AdministratorZgradeInline(admin.TabularInline):
    model = AdministratorZgrade
    extra = 0


@admin.register(Zgrada)
class ZgradaAdmin(admin.ModelAdmin):
    list_display = ["oznaka", "ulica", "kucni_broj", "postanski_broj", "grad", "aktivna", "uid"]
    readonly_fields = ["uid"]
    inlines = [AdministratorZgradeInline]


class VodomjerInline(admin.TabularInline):
    model = Vodomjer
    extra = 0


@admin.register(Stan)
class StanAdmin(admin.ModelAdmin):
    list_display = ["broj_stana", "zgrada", "kat", "napomena", "uid"]
    list_filter = ["zgrada"]
    readonly_fields = ["uid"]
    inlines = [KorisnikStanInline, VodomjerInline]


@admin.register(Vodomjer)
class VodomjerAdmin(admin.ModelAdmin):
    list_display = ["stan", "zgrada", "serijski_broj", "oznaka", "pocetno_stanje", "aktivan"]
    list_filter = ["aktivan", "stan__zgrada"]

    @admin.display(description="Zgrada", ordering="stan__zgrada")
    def zgrada(self, obj):
        return obj.stan.zgrada.oznaka


@admin.register(Ocitanje)
class OcitanjeAdmin(admin.ModelAdmin):
    list_display = [
        "razdoblje_mjesec", "datum_ocitanja", "broj_stana", "ime_prezime",
        "prethodno_stanje", "novo_stanje", "razlika", "status", "za_provjeru",
    ]
    list_filter = ["vodomjer__stan__zgrada", "status", "za_provjeru", "razdoblje"]
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


admin.site.register(Postavke)
