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
data class PrijavaOdgovor(val token: String)

@Serializable
data class Greska(val kod: String = "", val poruka: String = "")

@Serializable
data class Ocitanje(
    val id: Long,
    val vodomjer: Long,
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
    @SerialName("broj_stana") val brojStana: String,
    val vodomjeri: List<Vodomjer>,
)

/** Od kojeg dana u mjesecu i u koliko sati mobitel podsjeća na očitanje; postavlja administrator. */
@Serializable
data class PostavkePodsjetnika(val dan: Int = 26, val sat: Int = 9)

/** Verzija APK-a na serveru (versionCode); null ako server još nema APK. */
@Serializable
data class VerzijaAplikacije(val verzija: Int? = null)

@Serializable
data class Ja(
    @SerialName("korisnicko_ime") val korisnickoIme: String,
    val ime: String,
    val prezime: String,
    val stanovi: List<Stan>,
    val podsjetnik: PostavkePodsjetnika = PostavkePodsjetnika(),
    val aplikacija: VerzijaAplikacije = VerzijaAplikacije(),
)

interface Api {
    @POST("api/prijava/")
    suspend fun prijava(@Body zahtjev: PrijavaZahtjev): Response<PrijavaOdgovor>

    @POST("api/odjava/")
    suspend fun odjava(): Response<Unit>

    @GET("api/ja/")
    suspend fun ja(): Response<Ja>

    @GET("api/ocitanja/")
    suspend fun ocitanja(): Response<List<Ocitanje>>

    @Multipart
    @POST("api/ocitanja/")
    suspend fun predaj(
        @PartMap polja: Map<String, @JvmSuppressWildcards RequestBody>,
        @Part fotografija: MultipartBody.Part?,
    ): Response<Ocitanje>
}
