package hr.prijavavode.podsjetnik

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import hr.prijavavode.MainActivity
import hr.prijavavode.R
import hr.prijavavode.podaci.Ja
import hr.prijavavode.podaci.Repozitorij
import hr.prijavavode.podaci.Rezultat
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime

/**
 * Podsjetnik na očitanje: svaki dan u sat koji je postavio administrator mobitel pita server
 * je li vodomjer očitan i, od dana očitanja do kraja mjeseca, prikaže obavijest ako nije.
 */
object Podsjetnik {
    private const val POSAO = "podsjetnik-ocitanja"
    private const val KANAL = "podsjetnik"
    private const val OBAVIJEST = 1

    /** Zakazuje provjeru; [zamijeni] kad se sat promijenio, inače ostaje već zakazana. */
    fun zakazi(context: Context, sat: Int, zamijeni: Boolean) {
        val pravilo = if (zamijeni) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP
        WorkManager.getInstance(context).enqueueUniqueWork(POSAO, pravilo, zahtjev(sat))
    }

    /** Iz radnika koji upravo radi: sljedeća provjera kreće kad ova završi. */
    internal fun zakaziSljedeci(context: Context, sat: Int) {
        WorkManager.getInstance(context).enqueueUniqueWork(POSAO, ExistingWorkPolicy.APPEND_OR_REPLACE, zahtjev(sat))
    }

    fun otkazi(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(POSAO)
        ukloniObavijest(context)
    }

    fun ukloniObavijest(context: Context) = NotificationManagerCompat.from(context).cancel(OBAVIJEST)

    private fun zahtjev(sat: Int): OneTimeWorkRequest =
        OneTimeWorkRequestBuilder<RadnikPodsjetnika>()
            .setInitialDelay(doSljedeceg(sat, LocalDateTime.now()))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()

    /** Vrijeme do sljedećeg punog sata [sat]; ako je upravo prošao, sutra. */
    fun doSljedeceg(sat: Int, sada: LocalDateTime): Duration {
        var cilj = sada.toLocalDate().atTime(sat, 0)
        if (!cilj.isAfter(sada.plusMinutes(1))) cilj = cilj.plusDays(1)
        return Duration.between(sada, cilj)
    }

    /** Brojevi stanova čiji vodomjer treba očitati; prazno prije dana očitanja. */
    fun neocitaniStanovi(ja: Ja, danas: LocalDate): List<String> {
        if (danas.dayOfMonth < ja.podsjetnik.dan) return emptyList()
        return ja.stanovi
            .filter { stan ->
                stan.vodomjeri.any { it.ocitanjeOvajMjesec == null || it.ocitanjeOvajMjesec.status == "odbijeno" }
            }
            .map { it.brojStana }
    }

    fun tekst(stanovi: List<String>): String =
        if (stanovi.size == 1) "Vodomjer stana ${stanovi[0]} za ovaj mjesec još nije očitan."
        else "Vodomjeri stanova ${stanovi.joinToString(", ")} za ovaj mjesec još nisu očitani."

    @SuppressLint("MissingPermission")
    internal fun prikazi(context: Context, stanovi: List<String>) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val upravitelj = context.getSystemService(NotificationManager::class.java)
        upravitelj.createNotificationChannel(
            NotificationChannel(KANAL, "Podsjetnik na očitanje", NotificationManager.IMPORTANCE_DEFAULT)
        )
        val otvori = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val obavijest = NotificationCompat.Builder(context, KANAL)
            .setSmallIcon(R.drawable.ic_obavijest)
            .setContentTitle("Očitajte vodomjer")
            .setContentText(tekst(stanovi))
            .setStyle(NotificationCompat.BigTextStyle().bigText(tekst(stanovi)))
            .setContentIntent(otvori)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(OBAVIJEST, obavijest)
    }
}

class RadnikPodsjetnika(context: Context, parametri: WorkerParameters) : CoroutineWorker(context, parametri) {
    override suspend fun doWork(): Result {
        val repo = Repozitorij(applicationContext)
        if (repo.token == null) return Result.success()
        var sat = repo.satPodsjetnika.takeIf { it >= 0 } ?: 9
        when (val r = repo.ja()) {
            is Rezultat.Uspjeh -> {
                sat = r.podaci.podsjetnik.sat
                repo.satPodsjetnika = sat
                val stanovi = Podsjetnik.neocitaniStanovi(r.podaci, LocalDate.now())
                if (stanovi.isNotEmpty()) Podsjetnik.prikazi(applicationContext, stanovi)
            }
            // Odjavljen (token istekao): bez podsjetnika dok se ponovno ne prijavi.
            is Rezultat.Neuspjeh -> if (r.kod == "odjavljen") return Result.success()
        }
        Podsjetnik.zakaziSljedeci(applicationContext, sat)
        return Result.success()
    }
}
