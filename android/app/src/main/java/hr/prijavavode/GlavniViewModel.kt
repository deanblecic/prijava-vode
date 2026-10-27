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
import hr.prijavavode.podaci.Ocitanje
import hr.prijavavode.podaci.Repozitorij
import hr.prijavavode.podaci.Rezultat
import hr.prijavavode.podaci.Vodomjer
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

class GlavniViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = Repozitorij(app)

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

    init {
        if (repo.token == null) ekran = Ekran.Prijava else osvjezi()
    }

    fun prijava(ime: String, lozinka: String) = posao {
        when (val r = repo.prijava(ime, lozinka)) {
            is Rezultat.Uspjeh -> osvjeziSada()
            is Rezultat.Neuspjeh -> greska = r.poruka
        }
    }

    fun odjava() = posao {
        repo.odjava()
        ja = null
        ekran = Ekran.Prijava
    }

    fun osvjezi() = posao { osvjeziSada() }

    private suspend fun osvjeziSada() {
        when (val r = repo.ja()) {
            is Rezultat.Uspjeh -> {
                ja = r.podaci
                ekran = Ekran.Pocetna
            }
            is Rezultat.Neuspjeh -> obradiGresku(r)
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
