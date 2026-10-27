package hr.prijavavode.ui

import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

private val MJESECI = listOf(
    "siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj",
    "srpanj", "kolovoz", "rujan", "listopad", "studeni", "prosinac",
)

fun nazivMjeseca(datum: LocalDate = LocalDate.now()): String = "${MJESECI[datum.monthValue - 1]} ${datum.year}."

/** "2026-10" → "listopad 2026." */
fun nazivRazdoblja(razdoblje: String): String =
    runCatching { nazivMjeseca(LocalDate.parse("$razdoblje-01")) }.getOrDefault(razdoblje)

fun datumIVrijeme(iso: String): String =
    runCatching {
        OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("d.M.yyyy. HH:mm"))
    }.getOrDefault(iso)

/** Prikaz broja s decimalnim zarezom, kako smo navikli. */
fun hr(broj: String): String = broj.replace('.', ',')
