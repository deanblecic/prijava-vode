package hr.prijavavode.podaci

import android.content.Context
import hr.prijavavode.BuildConfig
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.math.BigDecimal
import java.util.concurrent.TimeUnit

sealed interface Rezultat<out T> {
    data class Uspjeh<T>(val podaci: T) : Rezultat<T>
    data class Neuspjeh(val kod: String, val poruka: String) : Rezultat<Nothing>
}

/** Jedino mjesto koje razgovara sa serverom i pamti prijavu. */
class Repozitorij(context: Context) {
    private val postavke = context.getSharedPreferences("prijava", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }

    var token: String?
        get() = postavke.getString("token", null)
        private set(vrijednost) = postavke.edit().putString("token", vrijednost).apply()

    /** Sat za koji je zakazan podsjetnik; -1 znači da nije zakazan. */
    var satPodsjetnika: Int
        get() = postavke.getInt("sat_podsjetnika", -1)
        set(vrijednost) = postavke.edit().putInt("sat_podsjetnika", vrijednost).apply()

    /** Dozvola za obavijesti traži se samo jednom; poslije je korisnik može uključiti u postavkama mobitela. */
    var obavijestiTrazene: Boolean
        get() = postavke.getBoolean("obavijesti_trazene", false)
        set(vrijednost) = postavke.edit().putBoolean("obavijesti_trazene", vrijednost).apply()

    private val api: Api by lazy {
        val klijent = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor { lanac ->
                val zahtjev = lanac.request().newBuilder()
                token?.let { zahtjev.header("Authorization", "Token $it") }
                lanac.proceed(zahtjev.build())
            }
            .build()
        Retrofit.Builder()
            .baseUrl(BuildConfig.SERVER_URL.trimEnd('/') + "/")
            .client(klijent)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(Api::class.java)
    }

    suspend fun prijava(korisnickoIme: String, lozinka: String): Rezultat<Unit> =
        when (val r = poziv { api.prijava(PrijavaZahtjev(korisnickoIme.trim(), lozinka)) }) {
            is Rezultat.Uspjeh -> {
                token = r.podaci.token
                Rezultat.Uspjeh(Unit)
            }
            is Rezultat.Neuspjeh -> r
        }

    suspend fun odjava() {
        runCatching { api.odjava() }
        token = null
    }

    suspend fun ja(): Rezultat<Ja> = poziv { api.ja() }

    suspend fun ocitanja(): Rezultat<List<Ocitanje>> = poziv { api.ocitanja() }

    suspend fun predaj(
        vodomjerId: Long,
        novoStanje: BigDecimal,
        ocrVrijednost: BigDecimal?,
        fotografijaJpeg: ByteArray?,
        potvrdiManje: Boolean,
    ): Rezultat<Ocitanje> {
        val tekst = "text/plain".toMediaType()
        val polja = buildMap {
            put("vodomjer", vodomjerId.toString().toRequestBody(tekst))
            put("novo_stanje", novoStanje.toPlainString().toRequestBody(tekst))
            ocrVrijednost?.let { put("ocr_vrijednost", it.toPlainString().toRequestBody(tekst)) }
            put("potvrdi_manje", potvrdiManje.toString().toRequestBody(tekst))
        }
        val foto = fotografijaJpeg?.let {
            MultipartBody.Part.createFormData(
                "fotografija", "vodomjer.jpg", it.toRequestBody("image/jpeg".toMediaType())
            )
        }
        return poziv { api.predaj(polja, foto) }
    }

    private suspend fun <T> poziv(blok: suspend () -> Response<T>): Rezultat<T> {
        val odgovor = try {
            blok()
        } catch (e: IOException) {
            return Rezultat.Neuspjeh("mreza", "Nema veze sa serverom. Provjerite internet i pokušajte ponovno.")
        } catch (e: Exception) {
            return Rezultat.Neuspjeh("nepoznato", "Neočekivana greška: ${e.message}")
        }
        if (odgovor.isSuccessful) {
            @Suppress("UNCHECKED_CAST")
            return Rezultat.Uspjeh(odgovor.body() ?: Unit as T)
        }
        if (odgovor.code() == 401) {
            token = null
            return Rezultat.Neuspjeh("odjavljen", "Prijava je istekla. Prijavite se ponovno.")
        }
        val greska = odgovor.errorBody()?.string()?.let {
            runCatching { json.decodeFromString<Greska>(it) }.getOrNull()
        }
        return Rezultat.Neuspjeh(
            greska?.kod?.ifEmpty { null } ?: "http_${odgovor.code()}",
            greska?.poruka?.ifEmpty { null } ?: "Server je vratio grešku ${odgovor.code()}.",
        )
    }
}
