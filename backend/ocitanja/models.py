import unicodedata
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


def kljuc_adrese(ulica, kucni_broj, grad):
    """Ulica, kućni broj i grad bez kvačica, točaka, velikih slova i viška razmaka."""
    tekst = f"{ulica}|{kucni_broj}|{grad}".replace("đ", "dj").replace("Đ", "Dj")
    tekst = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower()
    return "|".join(" ".join(dio.replace(".", " ").split()) for dio in tekst.split("|"))


class Zgrada(models.Model):
    """Zgradu ljudi prepoznaju po adresi, a sve veze u bazi idu preko id-a i uid-a koji se ne mijenjaju."""

    uid = models.UUIDField("jedinstveni ID", default=uuid.uuid4, unique=True, editable=False)
    oznaka = models.CharField(
        "oznaka", max_length=20, unique=True, help_text="Kratka oznaka za ljude, npr. RI-ALB-2"
    )
    ulica = models.CharField("ulica", max_length=150)
    kucni_broj = models.CharField("kućni broj", max_length=20)
    postanski_broj = models.CharField("poštanski broj", max_length=10)
    grad = models.CharField("grad", max_length=100)
    kljuc_adrese = models.CharField(max_length=300, unique=True, editable=False)
    aktivna = models.BooleanField("aktivna", default=True)
    administratori = models.ManyToManyField(
        "Korisnik", through="AdministratorZgrade", related_name="administrirane_zgrade", blank=True
    )

    class Meta:
        verbose_name = "zgrada"
        verbose_name_plural = "zgrade"
        ordering = ["grad", "ulica", "kucni_broj"]

    def clean(self):
        kljuc = kljuc_adrese(self.ulica, self.kucni_broj, self.grad)
        if Zgrada.objects.filter(kljuc_adrese=kljuc).exclude(pk=self.pk).exists():
            raise ValidationError("Zgrada s tom ulicom, kućnim brojem i gradom već postoji.")

    def save(self, *args, **kwargs):
        self.kljuc_adrese = kljuc_adrese(self.ulica, self.kucni_broj, self.grad)
        self.oznaka = self.oznaka.strip().upper()
        super().save(*args, **kwargs)

    @property
    def adresa(self):
        return f"{self.ulica} {self.kucni_broj}, {self.postanski_broj} {self.grad}"

    def __str__(self):
        return self.adresa


class Korisnik(AbstractUser):
    """Suvlasnik ili administrator. Ime i prezime su polja first_name i last_name.

    Superadministrator je is_superuser; administrator zgrade ima red u AdministratorZgrade.
    Zgrade u kojima je netko suvlasnik izvode se iz njegovih stanova.
    """

    telefon = models.CharField(max_length=30, blank=True)
    mora_promijeniti_lozinku = models.BooleanField(
        "mora promijeniti lozinku", default=False,
        help_text="Lozinku je postavio administrator, pa je korisnik mijenja kod sljedeće prijave.",
    )

    class Meta:
        verbose_name = "korisnik"
        verbose_name_plural = "korisnici"

    def save(self, *args, **kwargs):
        # Django administraciju (/admin/) koristi samo superadministrator; ona ne zna za zgrade.
        self.is_staff = self.is_superuser
        super().save(*args, **kwargs)

    @property
    def je_administrator(self):
        return self.is_superuser or self.administrirane_zgrade.exists()

    def zgrade_za_upravljanje(self):
        if self.is_superuser:
            return Zgrada.objects.all()
        return self.administrirane_zgrade.all()

    def aktivni_stanovi(self, na_dan=None):
        na_dan = na_dan or timezone.localdate()
        # Jedan filter() da se svi uvjeti odnose na isti red suvlasništva.
        return Stan.objects.filter(
            Q(vlasnistva__do_datuma__isnull=True) | Q(vlasnistva__do_datuma__gte=na_dan),
            vlasnistva__korisnik=self,
            vlasnistva__od_datuma__lte=na_dan,
        ).distinct()

    def __str__(self):
        return self.get_full_name() or self.username


class AdministratorZgrade(models.Model):
    korisnik = models.ForeignKey(Korisnik, on_delete=models.CASCADE, related_name="uloge_u_zgradama")
    zgrada = models.ForeignKey(Zgrada, on_delete=models.CASCADE, related_name="uloge_administratora")
    od = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "administrator zgrade"
        verbose_name_plural = "administratori zgrada"
        constraints = [
            models.UniqueConstraint(fields=["korisnik", "zgrada"], name="jedan_administrator_jednom_po_zgradi"),
        ]

    def __str__(self):
        return f"{self.korisnik} – {self.zgrada}"


class Stan(models.Model):
    uid = models.UUIDField("jedinstveni ID", default=uuid.uuid4, unique=True, editable=False)
    zgrada = models.ForeignKey(Zgrada, on_delete=models.PROTECT, related_name="stanovi")
    broj_stana = models.CharField(max_length=10)
    kat = models.SmallIntegerField(null=True, blank=True)
    napomena = models.CharField(max_length=200, blank=True)
    korisnici = models.ManyToManyField(Korisnik, through="KorisnikStan", related_name="stanovi")

    class Meta:
        verbose_name = "stan"
        verbose_name_plural = "stanovi"
        ordering = ["zgrada_id", "broj_stana"]
        constraints = [
            models.UniqueConstraint(fields=["zgrada", "broj_stana"], name="broj_stana_jedinstven_u_zgradi"),
        ]

    def save(self, *args, **kwargs):
        # Stan se nikad ne premješta u drugu zgradu; krivo upisan stan zamjenjuje se novim.
        if self.pk:
            prije = Stan.objects.filter(pk=self.pk).values_list("zgrada_id", flat=True).first()
            if prije is not None and prije != self.zgrada_id:
                raise ValidationError("Stan se ne može premjestiti u drugu zgradu.")
        super().save(*args, **kwargs)

    @property
    def oznaka(self):
        return f"{self.zgrada.oznaka}/{self.broj_stana}"

    def __str__(self):
        return f"Stan {self.broj_stana}"


class KorisnikStan(models.Model):
    """Tko je suvlasnik kojeg stana i od kada; do_datuma prazno znači i danas."""

    korisnik = models.ForeignKey(Korisnik, on_delete=models.CASCADE, related_name="vlasnistva")
    stan = models.ForeignKey(Stan, on_delete=models.CASCADE, related_name="vlasnistva")
    od_datuma = models.DateField(default=timezone.localdate)
    do_datuma = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "suvlasništvo"
        verbose_name_plural = "suvlasništva"

    def __str__(self):
        return f"{self.korisnik} – {self.stan}"


class Vodomjer(models.Model):
    stan = models.ForeignKey(Stan, on_delete=models.PROTECT, related_name="vodomjeri")
    serijski_broj = models.CharField(max_length=50, blank=True)
    oznaka = models.CharField(max_length=50, blank=True, help_text="Npr. kupaonica ili kuhinja")
    pocetno_stanje = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    aktivan = models.BooleanField(default=True)

    class Meta:
        verbose_name = "vodomjer"
        verbose_name_plural = "vodomjeri"
        ordering = ["stan__broj_stana", "oznaka"]
        constraints = [
            # Svaki stan ima jedan vodomjer; zamijenjeni ostaju neaktivni radi povijesti.
            models.UniqueConstraint(
                fields=["stan"], condition=Q(aktivan=True), name="jedan_aktivni_vodomjer_po_stanu"
            ),
        ]

    def __str__(self):
        opis = f" ({self.oznaka})" if self.oznaka else ""
        return f"{self.stan}{opis}"


def putanja_fotografije(ocitanje, ime_datoteke):
    ekstenzija = ime_datoteke.rsplit(".", 1)[-1].lower() if "." in ime_datoteke else "jpg"
    return (
        f"ocitanja/zgrada-{ocitanje.vodomjer.stan.zgrada_id}/{ocitanje.razdoblje:%Y-%m}/"
        f"stan-{ocitanje.vodomjer.stan.broj_stana}-vodomjer-{ocitanje.vodomjer_id}.{ekstenzija}"
    )


class Ocitanje(models.Model):
    class Status(models.TextChoices):
        PREDANO = "predano", "Predano"
        POTVRDENO = "potvrdeno", "Potvrđeno"
        ODBIJENO = "odbijeno", "Odbijeno"

    vodomjer = models.ForeignKey(Vodomjer, on_delete=models.PROTECT, related_name="ocitanja")
    korisnik = models.ForeignKey(Korisnik, on_delete=models.PROTECT, related_name="ocitanja")
    razdoblje = models.DateField(help_text="Prvi dan mjeseca na koji se očitanje odnosi")
    datum_ocitanja = models.DateTimeField(default=timezone.now)
    prethodno_stanje = models.DecimalField(max_digits=10, decimal_places=3)
    novo_stanje = models.DecimalField(max_digits=10, decimal_places=3)
    razlika = models.DecimalField(max_digits=10, decimal_places=3)
    ocr_vrijednost = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    rucno_ispravljeno = models.BooleanField(default=False)
    fotografija = models.ImageField(upload_to=putanja_fotografije, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PREDANO)
    za_provjeru = models.BooleanField(default=False)
    razlog_provjere = models.CharField(max_length=200, blank=True)
    napomena = models.CharField(max_length=500, blank=True)
    stvoreno = models.DateTimeField(auto_now_add=True)
    izmijenjeno = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "očitanje"
        verbose_name_plural = "očitanja"
        ordering = ["-razdoblje", "vodomjer__stan__broj_stana"]
        constraints = [
            models.UniqueConstraint(fields=["vodomjer", "razdoblje"], name="jedno_ocitanje_mjesecno"),
        ]

    def save(self, *args, **kwargs):
        self.razlika = self.novo_stanje - self.prethodno_stanje
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vodomjer} {self.razdoblje:%m/%Y}: {self.novo_stanje}"


class Postavke(models.Model):
    """Postavke podsjetnika jedne zgrade koje administrator mijenja u web sučelju."""

    zgrada = models.OneToOneField(Zgrada, on_delete=models.CASCADE, related_name="postavke")

    dan_ocitanja = models.PositiveSmallIntegerField(
        "dan očitanja", default=26, validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text="Od ovog dana do kraja mjeseca aplikacija podsjeća suvlasnike koji još nisu očitali vodomjer.",
    )
    sat_podsjetnika = models.PositiveSmallIntegerField(
        "sat podsjetnika", default=9, validators=[MinValueValidator(0), MaxValueValidator(23)],
        help_text="U koliko sati (0–23) mobitel prikazuje podsjetnik.",
    )
    email_obavijesti = models.CharField(
        "e-mail za obavijest", max_length=300, blank=True,
        help_text="Kamo zadnji dan u mjesecu stiže popis neočitanih vodomjera; više adresa odvojite zarezom. "
                  "Prazno: svim administratorima zgrade s upisanim e-mailom.",
    )

    class Meta:
        verbose_name = "postavke"
        verbose_name_plural = "postavke"

    @classmethod
    def ucitaj(cls, zgrada):
        return cls.objects.get_or_create(zgrada=zgrada)[0]

    def __str__(self):
        return f"Postavke – {self.zgrada}"


def ip_klijenta(request):
    """Adresa posjetitelja; nginx je dopisuje kao zadnju u X-Forwarded-For, prethodne može lažirati klijent."""
    proslijedjeno = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proslijedjeno:
        return proslijedjeno.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR")


class Zapisnik(models.Model):
    """Trag važnih radnji: tko je, kada i u kojoj zgradi što napravio."""

    class Radnja(models.TextChoices):
        PRIJAVA = "prijava", "Prijava"
        NEUSPJELA_PRIJAVA = "neuspjela_prijava", "Neuspjela prijava"
        NOVA_LOZINKA = "nova_lozinka", "Nova lozinka"
        PROMJENA_LOZINKE = "promjena_lozinke", "Promjena lozinke"
        SPAJANJE = "spajanje", "Spajanje računa"
        PONISTENO_SPAJANJE = "ponisteno_spajanje", "Poništeno spajanje"
        ADMINISTRATOR = "administrator", "Administrator zgrade"
        ZGRADA = "zgrada", "Zgrada"
        STAN = "stan", "Stan i vodomjer"
        OCITANJE = "ocitanje", "Očitanje"
        DVA_KORAKA = "dva_koraka", "Prijava u dva koraka"

    vrijeme = models.DateTimeField(default=timezone.now, db_index=True)
    korisnik = models.ForeignKey(Korisnik, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    zgrada = models.ForeignKey(Zgrada, null=True, blank=True, on_delete=models.SET_NULL, related_name="zapisi")
    radnja = models.CharField(max_length=30, choices=Radnja.choices)
    opis = models.CharField(max_length=500)
    podaci = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "zapis"
        verbose_name_plural = "zapisnik"
        ordering = ["-vrijeme"]

    @classmethod
    def upisi(cls, radnja, opis, *, request=None, korisnik=None, zgrada=None, **podaci):
        if request is not None and korisnik is None and request.user.is_authenticated:
            korisnik = request.user
        return cls.objects.create(
            radnja=radnja, opis=opis[:500], korisnik=korisnik, zgrada=zgrada, podaci=podaci,
            ip=ip_klijenta(request) if request is not None else None,
        )

    def __str__(self):
        return f"{self.vrijeme:%d.%m.%Y. %H:%M} {self.opis}"
