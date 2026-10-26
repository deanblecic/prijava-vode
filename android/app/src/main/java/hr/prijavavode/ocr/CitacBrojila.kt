package hr.prijavavode.ocr

import java.math.BigDecimal

/**
 * Iz teksta koji OCR pročita s brojila izvlači moguća stanja vodomjera.
 *
 * Vodomjer obično ima 5 crnih znamenki (m³) i 3 crvene (litre), često bez
 * decimalnog zareza, pa se svaki niz znamenki tumači na više načina, a
 * prednost dobiva tumačenje najbliže prethodnom stanju.
 */
object CitacBrojila {

    /** Najveća razumna mjesečna potrošnja jednog stana, u m³. */
    private val NAJVECA_RAZLIKA = BigDecimal(200)

    private val ZAMJENE = mapOf(
        'O' to '0', 'o' to '0', 'D' to '0', 'Q' to '0',
        'I' to '1', 'l' to '1', '|' to '1', 'i' to '1',
        'Z' to '2', 'z' to '2',
        'S' to '5', 's' to '5',
        'B' to '8',
        'G' to '6', 'b' to '6',
        'T' to '7',
    )

    private val DECIMALNI = Regex("""(\d{1,6})\s*[.,]\s*(\d{1,4})""")
    private val ZNAMENKE = Regex("""\d{3,}""")

    fun kandidati(linije: List<String>, prethodno: BigDecimal?): List<BigDecimal> {
        val svi = LinkedHashSet<BigDecimal>()
        val sZarezom = mutableSetOf<BigDecimal>()
        for (linija in linije) {
            val ocisceno = popraviZnakove(linija)
            DECIMALNI.findAll(ocisceno).forEach { m ->
                val broj = BigDecimal("${m.groupValues[1]}.${m.groupValues[2]}")
                svi += broj
                sZarezom += broj
            }
            // Kotačići brojila često se pročitaju kao znamenke odvojene razmacima.
            val zbijeno = ocisceno.replace(Regex("""(?<=\d)\s+(?=\d)"""), "")
            ZNAMENKE.findAll(zbijeno).forEach { m -> svi += tumacenja(m.value) }
        }
        // 184.12 i 184.120 su isti broj; zadržava se prvo pronađeno tumačenje.
        val jedinstveni = svi.distinctBy { normaliziraj(it.stripTrailingZeros()) }
        return poredaj(jedinstveni, prethodno, sZarezom)
    }

    private fun popraviZnakove(linija: String): String {
        val brojZnamenki = linija.count { it.isDigit() }
        if (brojZnamenki < 3) return linija
        return linija.map { ZAMJENE[it] ?: it }.joinToString("")
    }

    private fun tumacenja(niz: String): List<BigDecimal> {
        val rezultat = mutableListOf(BigDecimal(niz))
        for (decimala in listOf(3, 2, 4, 1)) {
            if (niz.length - decimala >= 2) {
                rezultat += BigDecimal(niz.substring(0, niz.length - decimala) + "." + niz.takeLast(decimala))
            }
        }
        return rezultat
    }

    private fun normaliziraj(broj: BigDecimal): BigDecimal =
        if (broj.scale() < 0) broj.setScale(0) else broj

    private fun poredaj(kandidati: List<BigDecimal>, prethodno: BigDecimal?, sZarezom: Set<BigDecimal>): List<BigDecimal> {
        if (prethodno == null || prethodno.signum() == 0) {
            // Bez prethodnog stanja: prednost imaju tumačenja s tri decimale (crvene znamenke).
            return kandidati.sortedWith(compareBy<BigDecimal> { if (it.scale() == 3) 0 else 1 }.thenByDescending { it.precision() })
        }
        val (moguci, ostali) = kandidati.partition {
            val razlika = it - prethodno
            razlika.signum() >= 0 && razlika <= NAJVECA_RAZLIKA
        }
        // Broj s pročitanim zarezom pouzdaniji je od broja kojem smo sami dodali decimale.
        return moguci.sortedWith(compareBy<BigDecimal> { if (it in sZarezom) 0 else 1 }.thenBy { it - prethodno }) + ostali.sortedBy { (it - prethodno).abs() }
    }
}
