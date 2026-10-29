package hr.prijavavode

import android.app.Application
import android.graphics.Bitmap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import hr.prijavavode.ocr.Prepoznavanje
import hr.prijavavode.podaci.Ja
import hr.prijavavode.podaci.Nadogradnja
import hr.prijavavode.podaci.Ocitanje
import hr.prijavavode.podaci.Repozitorij
import hr.prijavavode.podaci.Rezultat
import hr.prijavavode.podaci.Sef
import hr.prijavavode.podaci.Vodomjer
import hr.prijavavode.podsjetnik.Podsjetnik
import hr.prijavavode.ui.Biometrija
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal

sealed interface Ekran {
    data object Ucitavanje : Ekran
    data object Prijava : Ekran
    data object Pocetna : Ekran
    data class Kamera(val vodomjer: Vodomjer) : Ekran
    data class Potvrda(
        val vodomjer: Vodomjer,
        val fotografija: Bitmap,
        val kandidati: List<BigDecimal>,
        /** Slika iz galerije: brojilo ne mora biti u sredini, pa se ne izrezuje. */
        val izGalerije: Boolean = false,
    ) : Ekran
    data object Povijest : Ekran
}

class GlavniViewModel(private val app: Application) : AndroidViewModel(app) {
    private val repo = Repozitorij(app)
    private val sef = Sef(app)

    var ekran by mutableStateOf<Ekran>(Ekran.Ucitavanje)
        private set
    var ja by mutableStateOf<Ja?>(null)
        private set
    var povijest by mutableStateOf<List<Ocitanje>>(emptyList())
        private set
    var radi by mutableStateOf(false)
        private set
    var greska by mutableStateOf<String?>(null)
    var trazPotvrduManjeg by mutableStateOf<String?>(null)
        private set
    var poruka by mutableStateOf<String?>(null)

    /** Prijava otiskom prsta ili licem je uključena i mobitel je podržava. */
    val biometrija: Boolean = sef.biometrija && Biometrija.dostupna(app)
    /** Ekran prijave odmah pita za otisak prsta; samo jednom, pri pokretanju. */
    var pitajBiometriju by mutableStateOf(biometrija)
    val zapamcenoIme: String get() = sef.ime.orEmpty()
    val zapamcenaLozinka: String get() = sef.lozinka.orEmpty()
    val zapamceno: Boolean get() = sef.zapamceno
    val biometrijaUkljucena: Boolean get() = sef.biometrija

    /** Na serveru je novija verzija aplikacije. */
    val novaVerzija: Boolean get() = Nadogradnja.dostupna(ja)
    /** Postotak preuzimanja nove verzije; null kad se ne preuzima. */
    var preuzimanje by mutableStateOf<Int?>(null)
        private set
    /** Prozor s prijedlogom nadogradnje; pokazuje se jednom po pokretanju aplikacije. */
    var ponudiNadogradnju by mutableStateOf(false)
    private var nadogradnjaPonudena = false

    init {
        // Uz biometriju i prijavljen korisnik prvo vidi ekran prijave, koji otključava otiskom prsta.
        if (repo.token == null || biometrija) ekran = Ekran.Prijava else osvjezi()
    }

    fun prijava(ime: String, lozinka: String, zapamti: Boolean, biometrija: Boolean) = posao {
        when (val r = repo.prijava(ime, lozinka)) {
            is Rezultat.Uspjeh -> {
                if (zapamti) sef.zapamti(ime.trim(), lozinka) else sef.zaboravi()
                sef.biometrija = zapamti && biometrija
                osvjeziSada()
            }
            is Rezultat.Neuspjeh -> greska = r.poruka
        }
    }

    /** Otisak prsta je potvrđen: nastavlja postojeću prijavu ili se prijavljuje zapamćenom lozinkom. */
    fun biometrijaPotvrdena() = posao {
        if (repo.token != null) return@posao osvjeziSada()
        val ime = sef.ime
        val lozinka = sef.lozinka
        if (ime == null || lozinka == null) {
            greska = "Zapamćena lozinka nije dostupna. Upišite je ponovno."
            return@posao
        }
        when (val r = repo.prijava(ime, lozinka)) {
            is Rezultat.Uspjeh -> osvjeziSada()
            is Rezultat.Neuspjeh -> greska = r.poruka
        }
    }

    fun odjava() = posao {
        repo.odjava()
        Podsjetnik.otkazi(app)
        repo.satPodsjetnika = -1
        ja = null
        ekran = Ekran.Prijava
    }

    /** Na Androidu 13+ dozvolu za obavijesti tražimo jednom, s početnog ekrana. */
    fun trebaTrazitiObavijesti(): Boolean {
        if (repo.obavijestiTrazene) return false
        repo.obavijestiTrazene = true
        return true
    }

    fun osvjezi() = posao { osvjeziSada() }

    private suspend fun osvjeziSada() {
        when (val r = repo.ja()) {
            is Rezultat.Uspjeh -> {
                ja = r.podaci
                ekran = Ekran.Pocetna
                if (Nadogradnja.dostupna(r.podaci) && !nadogradnjaPonudena) {
                    nadogradnjaPonudena = true
                    ponudiNadogradnju = true
                }
                val sat = r.podaci.podsjetnik.sat
                Podsjetnik.zakazi(app, sat, zamijeni = sat != repo.satPodsjetnika)
                repo.satPodsjetnika = sat
            }
            is Rezultat.Neuspjeh -> obradiGresku(r)
        }
    }

    fun nadogradi() {
        ponudiNadogradnju = false
        if (preuzimanje != null) return
        if (!Nadogradnja.smijeInstalirati(app)) {
            poruka = "Uključite „Dopusti iz ovog izvora”, vratite se tipkom Natrag i ponovno dodirnite Nadogradi."
            Nadogradnja.otvoriDopustenje(app)
            return
        }
        viewModelScope.launch {
            preuzimanje = 0
            try {
                val apk = Nadogradnja.preuzmi(app) { preuzimanje = it }
                poruka = null
                Nadogradnja.instaliraj(app, apk)
            } catch (e: Exception) {
                greska = "Nova verzija se nije mogla preuzeti. Provjerite internet i pokušajte ponovno."
            } finally {
                preuzimanje = null
            }
        }
    }

    fun otvoriKameru(vodomjer: Vodomjer) {
        poruka = null
        ekran = Ekran.Kamera(vodomjer)
    }

    fun snimljeno(vodomjer: Vodomjer, slika: Bitmap, izGalerije: Boolean) = posao {
        val prethodno = vodomjer.prethodnoStanje.toBigDecimalOrNull()
        val kandidati = runCatching {
            Prepoznavanje.procitaj(slika, prethodno, izrezi = !izGalerije)
        }.getOrElse { emptyList() }
        if (kandidati.isEmpty()) {
            poruka = "Broj nije prepoznat. Upišite ga ručno ili snimite ponovno."
        }
        ekran = Ekran.Potvrda(vodomjer, slika, kandidati, izGalerije)
    }

    fun posalji(potvrda: Ekran.Potvrda, novoStanje: BigDecimal, potvrdiManje: Boolean = false) = posao {
        trazPotvrduManjeg = null
        val jpeg = withContext(Dispatchers.Default) { Prepoznavanje.zaSlanje(potvrda.fotografija) }
        val r = repo.predaj(
            vodomjerId = potvrda.vodomjer.id,
            novoStanje = novoStanje,
            ocrVrijednost = potvrda.kandidati.firstOrNull(),
            fotografijaJpeg = jpeg,
            potvrdiManje = potvrdiManje,
        )
        when (r) {
            is Rezultat.Uspjeh -> {
                poruka = "Očitanje je poslano. Potrošnja ovaj mjesec: ${r.podaci.razlika} m³."
                Podsjetnik.ukloniObavijest(app)
                osvjeziSada()
            }
            is Rezultat.Neuspjeh ->
                if (r.kod == "manje_od_prethodnog") trazPotvrduManjeg = r.poruka else obradiGresku(r)
        }
    }

    fun odustaniOdManjeg() {
        trazPotvrduManjeg = null
    }

    fun otvoriPovijest() = posao {
        when (val r = repo.ocitanja()) {
            is Rezultat.Uspjeh -> {
                povijest = r.podaci
                ekran = Ekran.Povijest
            }
            is Rezultat.Neuspjeh -> obradiGresku(r)
        }
    }

    fun natrag() {
        poruka = null
        ekran = if (repo.token == null) Ekran.Prijava else Ekran.Pocetna
    }

    private fun obradiGresku(r: Rezultat.Neuspjeh) {
        greska = r.poruka
        if (r.kod == "odjavljen") ekran = Ekran.Prijava
        else if (ekran == Ekran.Ucitavanje) ekran = Ekran.Pocetna
    }

    private fun posao(blok: suspend () -> Unit) {
        viewModelScope.launch {
            radi = true
            try {
                blok()
            } finally {
                radi = false
            }
        }
    }
}
