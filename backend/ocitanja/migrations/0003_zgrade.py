import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Prvi dio prelaska na više zgrada: nove tablice i polja koja se tek trebaju popuniti."""

    dependencies = [
        ("ocitanja", "0002_postavke"),
    ]

    operations = [
        migrations.CreateModel(
            name="Zgrada",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="jedinstveni ID")),
                ("oznaka", models.CharField(help_text="Kratka oznaka za ljude, npr. RI-ALB-2", max_length=20, unique=True, verbose_name="oznaka")),
                ("ulica", models.CharField(max_length=150, verbose_name="ulica")),
                ("kucni_broj", models.CharField(max_length=20, verbose_name="kućni broj")),
                ("postanski_broj", models.CharField(max_length=10, verbose_name="poštanski broj")),
                ("grad", models.CharField(max_length=100, verbose_name="grad")),
                ("kljuc_adrese", models.CharField(editable=False, max_length=300, unique=True)),
                ("aktivna", models.BooleanField(default=True, verbose_name="aktivna")),
            ],
            options={
                "verbose_name": "zgrada",
                "verbose_name_plural": "zgrade",
                "ordering": ["grad", "ulica", "kucni_broj"],
            },
        ),
        migrations.CreateModel(
            name="AdministratorZgrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("od", models.DateTimeField(auto_now_add=True)),
                ("korisnik", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="uloge_u_zgradama", to="ocitanja.korisnik")),
                ("zgrada", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="uloge_administratora", to="ocitanja.zgrada")),
            ],
            options={
                "verbose_name": "administrator zgrade",
                "verbose_name_plural": "administratori zgrada",
                "constraints": [
                    models.UniqueConstraint(fields=("korisnik", "zgrada"), name="jedan_administrator_jednom_po_zgradi"),
                ],
            },
        ),
        migrations.AddField(
            model_name="zgrada",
            name="administratori",
            field=models.ManyToManyField(blank=True, related_name="administrirane_zgrade", through="ocitanja.AdministratorZgrade", to="ocitanja.korisnik"),
        ),
        # Privremeno prazna polja; popunjava ih 0004, a obaveznima ih čini 0005.
        migrations.AddField(
            model_name="stan",
            name="uid",
            field=models.UUIDField(null=True, editable=False, verbose_name="jedinstveni ID"),
        ),
        migrations.AddField(
            model_name="stan",
            name="zgrada",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stanovi", to="ocitanja.zgrada"),
        ),
        migrations.AddField(
            model_name="postavke",
            name="zgrada",
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="postavke", to="ocitanja.zgrada"),
        ),
    ]
