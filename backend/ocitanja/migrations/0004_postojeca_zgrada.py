import uuid

from django.db import migrations

# Zgrada u kojoj je aplikacija radila prije podrške za više zgrada.
POSTOJECA = {
    "oznaka": "RI-ALB-2",
    "ulica": "Moše Albaharija",
    "kucni_broj": "2",
    "postanski_broj": "51000",
    "grad": "Rijeka",
    "kljuc_adrese": "mose albaharija|2|rijeka",
}


def u_postojecu_zgradu(apps, schema_editor):
    Zgrada = apps.get_model("ocitanja", "Zgrada")
    Stan = apps.get_model("ocitanja", "Stan")
    Postavke = apps.get_model("ocitanja", "Postavke")
    Korisnik = apps.get_model("ocitanja", "Korisnik")
    AdministratorZgrade = apps.get_model("ocitanja", "AdministratorZgrade")

    # Svaki stan dobiva svoj uid; zajednički default bi svima dao isti.
    for stan in Stan.objects.all():
        stan.uid = uuid.uuid4()
        stan.save(update_fields=["uid"])

    administratori = Korisnik.objects.filter(uloga="administrator")
    if not (Stan.objects.exists() or Postavke.objects.exists() or administratori.exists()):
        return  # nova, prazna baza
    zgrada = Zgrada.objects.create(uid=uuid.uuid4(), **POSTOJECA)
    Stan.objects.update(zgrada=zgrada)
    postavke = Postavke.objects.order_by("pk").first()
    if postavke:
        Postavke.objects.exclude(pk=postavke.pk).delete()
        postavke.zgrada = zgrada
        postavke.save(update_fields=["zgrada"])
    for korisnik in administratori:
        AdministratorZgrade.objects.create(korisnik=korisnik, zgrada=zgrada)
    # Django administracija ostaje samo superadministratoru.
    Korisnik.objects.filter(is_superuser=False).update(is_staff=False)


class Migration(migrations.Migration):

    dependencies = [
        ("ocitanja", "0003_zgrade"),
    ]

    operations = [
        migrations.RunPython(u_postojecu_zgradu, migrations.RunPython.noop),
    ]
