from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Korisnik(AbstractUser):
    """Suvlasnik ili administrator. Ime i prezime su polja first_name i last_name."""

    class Uloga(models.TextChoices):
        SUVLASNIK = "suvlasnik", "Suvlasnik"
        ADMINISTRATOR = "administrator", "Administrator"

    uloga = models.CharField(max_length=20, choices=Uloga.choices, default=Uloga.SUVLASNIK)
    telefon = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = "korisnik"
        verbose_name_plural = "korisnici"

    def save(self, *args, **kwargs):
        # Administrator koristi i Django administraciju za korisnike i stanove.
        if self.uloga == self.Uloga.ADMINISTRATOR:
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def je_administrator(self):
        return self.uloga == self.Uloga.ADMINISTRATOR or self.is_superuser

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


class Stan(models.Model):
    broj_stana = models.CharField(max_length=10, unique=True)
    kat = models.SmallIntegerField(null=True, blank=True)
    napomena = models.CharField(max_length=200, blank=True)
    korisnici = models.ManyToManyField(Korisnik, through="KorisnikStan", related_name="stanovi")

    class Meta:
        verbose_name = "stan"
        verbose_name_plural = "stanovi"
        ordering = ["broj_stana"]

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
        f"ocitanja/{ocitanje.razdoblje:%Y-%m}/"
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
