package hr.prijavavode.podaci

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import hr.prijavavode.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Preuzimanje nove verzije aplikacije sa servera i predaja instalacijskom programu Androida. */
object Nadogradnja {
    private val klijent by lazy {
        OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
    }

    /** Je li na serveru novija verzija od instalirane. */
    fun dostupna(ja: Ja?): Boolean = (ja?.aplikacija?.verzija ?: 0) > BuildConfig.VERSION_CODE

    /** Smije li aplikacija pokrenuti instalaciju; korisnik to jednom dopušta u postavkama. */
    fun smijeInstalirati(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    fun otvoriDopustenje(context: Context) {
        context.startActivity(
            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    /** Preuzima APK u privremenu mapu; [napredak] dobiva postotak 0–100. */
    suspend fun preuzmi(context: Context, napredak: (Int) -> Unit): File = withContext(Dispatchers.IO) {
        val mapa = File(context.cacheDir, "nadogradnja").apply { mkdirs() }
        val datoteka = File(mapa, "ocitanje-vode.apk")
        val zahtjev = Request.Builder()
            .url(BuildConfig.SERVER_URL.trimEnd('/') + "/aplikacija/ocitanje-vode.apk")
            .build()
        klijent.newCall(zahtjev).execute().use { odgovor ->
            if (!odgovor.isSuccessful) throw IOException("Server je vratio ${odgovor.code}")
            val tijelo = odgovor.body ?: throw IOException("Prazan odgovor")
            val ukupno = tijelo.contentLength()
            tijelo.byteStream().use { ulaz ->
                datoteka.outputStream().use { izlaz ->
                    val spremnik = ByteArray(64 * 1024)
                    var procitano = 0L
                    var zadnji = -1
                    while (true) {
                        val n = ulaz.read(spremnik)
                        if (n < 0) break
                        izlaz.write(spremnik, 0, n)
                        procitano += n
                        if (ukupno > 0) {
                            val posto = (procitano * 100 / ukupno).toInt()
                            if (posto != zadnji) {
                                zadnji = posto
                                withContext(Dispatchers.Main) { napredak(posto) }
                            }
                        }
                    }
                }
            }
        }
        datoteka
    }

    fun instaliraj(context: Context, apk: File) {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.datoteke", apk)
        context.startActivity(
            Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}
