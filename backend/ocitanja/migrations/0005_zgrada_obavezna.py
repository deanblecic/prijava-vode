import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ocitanja", "0004_postojeca_zgrada"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stan",
            name="uid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="jedinstveni ID"),
        ),
        migrations.AlterField(
            model_name="stan",
            name="zgrada",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stanovi", to="ocitanja.zgrada"),
        ),
        migrations.AlterField(
            model_name="stan",
            name="broj_stana",
            field=models.CharField(max_length=10),
        ),
        migrations.AlterModelOptions(
            name="stan",
            options={"ordering": ["zgrada_id", "broj_stana"], "verbose_name": "stan", "verbose_name_plural": "stanovi"},
        ),
        migrations.AddConstraint(
            model_name="stan",
            constraint=models.UniqueConstraint(fields=("zgrada", "broj_stana"), name="broj_stana_jedinstven_u_zgradi"),
        ),
        migrations.AlterField(
            model_name="postavke",
            name="zgrada",
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="postavke", to="ocitanja.zgrada"),
        ),
        migrations.AlterField(
            model_name="postavke",
            name="email_obavijesti",
            field=models.CharField(blank=True, help_text="Kamo zadnji dan u mjesecu stiže popis neočitanih vodomjera; više adresa odvojite zarezom. Prazno: svim administratorima zgrade s upisanim e-mailom.", max_length=300, verbose_name="e-mail za obavijest"),
        ),
        migrations.RemoveField(
            model_name="korisnik",
            name="uloga",
        ),
    ]
