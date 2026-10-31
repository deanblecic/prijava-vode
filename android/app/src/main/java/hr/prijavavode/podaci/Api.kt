package hr.prijavavode.podaci

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.PartMap

@Serializable
data class PrijavaZahtjev(
    @SerialName("korisnicko_ime") val korisnickoIme: String,
    val lozinka: String,
)

@Serializable
data class PrijavaOdgovor(
    val token: String,
    @SerialName("mora_promijeniti_lozinku") val moraPromijenitiLozinku: Boolean = false,
)

@Serializable
data class LozinkaZahtjev(@SerialName("nova_lozinka") val novaLozinka: String)

@Serializable
data class Greska(val kod: String = "", val poruka: String = "")

@Serializable
data class Ocitanje(
    val id: Long,
    val vodomjer: Long,
    val zgrada: Long? = null,
    @SerialName("broj_stana") val brojStana: String,
    val razdoblje: String,
    @SerialName("datum_ocitanja") val datumOcitanja: String,
    @SerialName("prethodno_stanje") val prethodnoStanje: String,
    @SerialName("novo_stanje") val novoStanje: String,
    val razlika: String,
    val status: String,
    @SerialName("za_provjeru") val zaProvjeru: Boolean = false,
) {
    val statusTekst: String
        get() = when (status) {
            "potvrdeno" -> "Potvrđeno"
            "odbijeno" -> "Odbijeno, predajte ponovno"
            else -> "Predano, čeka potvrdu"
        }
}

@Serializable
data class Vodomjer(
    val id: Long,
    @SerialName("serijski_broj") val serijskiBroj: String = "",
    val oznaka: String = "",
    @SerialName("prethodno_stanje") val prethodnoStanje: String,
    @SerialName("ocitanje_ovaj_mjesec") val ocitanjeOvajMjesec: Ocitanje? = null,
)

@Serializable
data class Stan(
    val id: Long,
    /** Id zgrade; null kod servera starijeg od podrške za više zgrada. */
    val zgrada: Long? = null,
    /** Oznaka za ljude, npr. RI-ALB-2/17. */
    val oznaka: String = "",
    @SerialName("broj_stana") val brojStana: String,
    val vodomjeri: List<Vodomjer>,
)

/**
 * Kada mobitel podsjeća na očitanje; postavlja administrator zgrade. [dani] su dani ovog mjeseca
 * na koje stiže podsjetnik, a [rok] zadnji dan za očitanje (yyyy-MM-dd). Stariji server šalje samo
 * [dan], od kojeg se podsjeća do kraja mjeseca.
 */
@Serializable
data class PostavkePodsjetnika(
    val dan: Int = 26,
    val sat: Int = 9,
    val dani: List<Int>? = null,
    val rok: String? = null,
) {
    fun jeDanPodsjetnika(danUMjesecu: Int): Boolean = dani?.contains(danUMjesecu) ?: (danUMjesecu >= dan)
}

@Serializable
data class Zgrada(
    val id: Long,
    val oznaka: String = "",
    val ulica: String = "",
    @SerialName("kucni_broj") val kucniBroj: String = "",
    val grad: String = "",
    val podsjetnik: PostavkePodsjetnika = PostavkePodsjetnika(),
) {
    /** Kratka adresa za naslov, npr. "Moše Albaharija 2, Rijeka". */
    val naziv: String get() = "$ulica $kucniBroj, $grad"
}

/** Verzija APK-a na serveru (versionCode); null ako server još nema APK. */
@Serializable
data class VerzijaAplikacije(val verzija: Int? = null)

@Serializable
data class Ja(
    @SerialName("korisnicko_ime") val korisnickoIme: String,
    val ime: String,
    val prezime: String,
    val stanovi: List<Stan>,
    val zgrade: List<Zgrada> = emptyList(),
    val podsjetnik: PostavkePodsjetnika = PostavkePodsjetnika(),
    val aplikacija: VerzijaAplikacije = VerzijaAplikacije(),
    @SerialName("mora_promijeniti_lozinku") val moraPromijenitiLozinku: Boolean = false,
) {
    fun zgrada(stan: Stan): Zgrada? = zgrade.firstOrNull { it.id == stan.zgrada }

    /** Postavke podsjetnika zgrade u kojoj je stan. */
    fun podsjetnik(stan: Stan): PostavkePodsjetnika = zgrada(stan)?.podsjetnik ?: podsjetnik

    /** Stanovi grupirani po zgradama, redom kojim ih šalje server. */
    fun stanoviPoZgradama(): List<Pair<Zgrada?, List<Stan>>> =
        stanovi.groupBy { it.zgrada }.map { (id, stanovi) -> zgrade.firstOrNull { it.id == id } to stanovi }

    /** Sati u koje mobitel provjerava treba li podsjetiti, po jedan za svaku zgradu. */
    val satiPodsjetnika: List<Int>
        get() = (if (zgrade.isEmpty()) listOf(podsjetnik.sat) else zgrade.map { it.podsjetnik.sat }).distinct().sorted()
}

interface Api {
    @POST("api/prijava/")
    suspend fun prijava(@Body zahtjev: PrijavaZahtjev): Response<PrijavaOdgovor>

    @POST("api/odjava/")
    suspend fun odjava(): Response<Unit>

    @GET("api/ja/")
    suspend fun ja(): Response<Ja>

    @POST("api/lozinka/")
    suspend fun lozinka(@Body zahtjev: LozinkaZahtjev): Response<Unit>

    @GET("api/ocitanja/")
    suspend fun ocitanja(): Response<List<Ocitanje>>

    @Multipart
    @POST("api/ocitanja/")
    suspend fun predaj(
        @PartMap polja: Map<String, @JvmSuppressWildcards RequestBody>,
        @Part fotografija: MultipartBody.Part?,
    ): Response<Ocitanje>
}
