from rest_framework import serializers

from .models import Ocitanje, Postavke, Stan, Vodomjer, Zgrada
from .servisi import prethodno_stanje, prvi_u_mjesecu


class OcitanjeSerializer(serializers.ModelSerializer):
    broj_stana = serializers.CharField(source="vodomjer.stan.broj_stana", read_only=True)
    zgrada = serializers.IntegerField(source="vodomjer.stan.zgrada_id", read_only=True)
    ime_prezime = serializers.CharField(source="korisnik.get_full_name", read_only=True)
    razdoblje = serializers.DateField(format="%Y-%m", read_only=True)

    class Meta:
        model = Ocitanje
        fields = [
            "id", "vodomjer", "zgrada", "broj_stana", "ime_prezime", "razdoblje", "datum_ocitanja",
            "prethodno_stanje", "novo_stanje", "razlika", "ocr_vrijednost", "rucno_ispravljeno",
            "fotografija", "status", "za_provjeru", "napomena",
        ]
        read_only_fields = fields


class PredajaOcitanjaSerializer(serializers.Serializer):
    vodomjer = serializers.PrimaryKeyRelatedField(queryset=Vodomjer.objects.all())
    novo_stanje = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    ocr_vrijednost = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    datum_ocitanja = serializers.DateTimeField(required=False)
    fotografija = serializers.ImageField(required=False)
    napomena = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    potvrdi_manje = serializers.BooleanField(required=False, default=False)


class VodomjerSerializer(serializers.ModelSerializer):
    prethodno_stanje = serializers.SerializerMethodField()
    ocitanje_ovaj_mjesec = serializers.SerializerMethodField()

    class Meta:
        model = Vodomjer
        fields = ["id", "serijski_broj", "oznaka", "prethodno_stanje", "ocitanje_ovaj_mjesec"]

    def _razdoblje(self):
        return prvi_u_mjesecu(self.context["sada"])

    def get_prethodno_stanje(self, vodomjer):
        return str(prethodno_stanje(vodomjer, self._razdoblje()))

    def get_ocitanje_ovaj_mjesec(self, vodomjer):
        ocitanje = vodomjer.ocitanja.filter(razdoblje=self._razdoblje()).first()
        return OcitanjeSerializer(ocitanje, context=self.context).data if ocitanje else None


class ZgradaSerializer(serializers.ModelSerializer):
    podsjetnik = serializers.SerializerMethodField()

    class Meta:
        model = Zgrada
        fields = ["id", "uid", "oznaka", "ulica", "kucni_broj", "postanski_broj", "grad", "adresa", "podsjetnik"]

    def get_podsjetnik(self, zgrada):
        postavke = Postavke.ucitaj(zgrada)
        return {"dan": postavke.dan_ocitanja, "sat": postavke.sat_podsjetnika}


class StanSerializer(serializers.ModelSerializer):
    vodomjeri = serializers.SerializerMethodField()
    zgrada = serializers.PrimaryKeyRelatedField(read_only=True)
    oznaka = serializers.CharField(read_only=True)

    class Meta:
        model = Stan
        fields = ["id", "uid", "zgrada", "oznaka", "broj_stana", "kat", "vodomjeri"]

    def get_vodomjeri(self, stan):
        return VodomjerSerializer(stan.vodomjeri.filter(aktivan=True), many=True, context=self.context).data
