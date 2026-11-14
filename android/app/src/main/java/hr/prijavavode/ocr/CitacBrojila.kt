package hr.prijavavode.ocr

import java.math.BigDecimal

/**
 * Iz teksta koji OCR pročita s brojila izvlači moguća stanja vodomjera.
 *
 * Vodomjer obično ima 5 crnih znamenki (m³) i 3 crvene (litre), često bez
 * decimalnog zareza, pa se svaki niz znamenki tumači na više načina. Prednost
 * ima cijelo brojilo (7 i više znamenki ili pročitani zarez) pred kraćim nizovima
 * s natpisa na kućištu, a među jednako pouzdanima tumačenje najbliže prethodnom stanju.
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
    private val SAMO_ZNAMENKE = Regex("""\d+""")

    /** Toliko znamenki ima cijelo brojilo (5 crnih + 3 crvene, ponekad 4 + 4 ili 6 + 2). */
    private const val CIJELO_BROJILO = 7

    /**
     * Kandidat i koliko mu vjerujemo: 0 = cijelo brojilo ili izričiti zarez,
     * 1 = kraći niz znamenki (dio brojila ili natpis s kućišta).
     */
    private class Kandidat(val broj: BigDecimal, val razina: Int, val vodecaNula: Boolean)

    fun kandidati(linije: List<String>, prethodno: BigDecimal?): List<BigDecimal> {
        val svi = mutableListOf<Kandidat>()
        val ocisceneLinije = linije.map(::popraviZnakove)
        for (ocisceno in ocisceneLinije) {
            DECIMALNI.findAll(ocisceno).forEach { m ->
                svi += Kandidat(BigDecimal("${m.groupValues[1]}.${m.groupValues[2]}"), 0, m.groupValues[1].startsWith("0"))
            }
            // Kotačići brojila često se pročitaju kao znamenke odvojene razmacima.
            val zbijeno = ocisceno.replace(Regex("""(?<=\d)\s+(?=\d)"""), "")
            ZNAMENKE.findAll(zbijeno).forEach { m -> svi += tumacenja(m.value) }
        }
        // Crne i crvene znamenke ponekad se prepoznaju kao dva zasebna retka (npr. "00784" i "806").
        ocisceneLinije.zipWithNext().forEach { (crne, crvene) ->
            val c = crne.replace(Regex("""\s+"""), "")
            val r = crvene.replace(Regex("""\s+"""), "")
            if (SAMO_ZNAMENKE.matches(c) && SAMO_ZNAMENKE.matches(r) && c.length in 4..6 && r.length in 1..4) {
                svi += Kandidat(BigDecimal("$c.$r"), 0, c.startsWith("0"))
            }
        }
        // 184.12 i 184.120 su isti broj; zadržava se najpouzdanije tumačenje.
        val jedinstveni = svi
            .sortedBy { it.razina }
            .distinctBy { normaliziraj(it.broj.stripTrailingZeros()) }
        return poredaj(jedinstveni, prethodno)
    }

    /**
     * OCR zna pročitati 0 kao O, 1 kao l itd. Slova se mijenjaju samo u riječima koje izgledaju
     * kao broj (samo znamenke i takva slova), a ne u oznakama s kućišta: "PTB018" bi inače
     * postao "P78018" i dao lažno stanje 780,18.
     */
    private fun popraviZnakove(linija: String): String =
        linija.split(" ").joinToString(" ") { rijec ->
            val izgledaKaoBroj = rijec.any { it.isDigit() } && rijec.all { it.isDigit() || it in ZAMJENE }
            if (izgledaKaoBroj) rijec.map { ZAMJENE[it] ?: it }.joinToString("") else rijec
        }

    private fun tumacenja(niz: String): List<Kandidat> {
        val razina = if (niz.length >= CIJELO_BROJILO) 0 else 1
        val nula = niz.startsWith("0")
        val rezultat = mutableListOf(Kandidat(BigDecimal(niz), razina, nula))
        for (decimala in listOf(3, 2, 4, 1)) {
            if (niz.length - decimala >= 2) {
                rezultat += Kandidat(BigDecimal(niz.substring(0, niz.length - decimala) + "." + niz.takeLast(decimala)), razina, nula)
            }
        }
        return rezultat
    }

    private fun normaliziraj(broj: BigDecimal): BigDecimal =
        if (broj.scale() < 0) broj.setScale(0) else broj

    private fun poredaj(kandidati: List<Kandidat>, prethodno: BigDecimal?): List<BigDecimal> {
        if (prethodno == null || prethodno.signum() == 0) {
            // Bez prethodnog stanja: prednost ima cijelo brojilo s vodećim nulama (serijski broj
            // ih obično nema), zatim tumačenja s tri decimale (crvene znamenke).
            return kandidati.sortedWith(
                compareBy<Kandidat> { it.razina }
                    .thenBy { if (it.vodecaNula) 0 else 1 }
                    .thenBy { if (it.broj.scale() == 3) 0 else 1 }
                    .thenByDescending { it.broj.precision() }
            ).map { it.broj }
        }
        val (moguci, ostali) = kandidati.partition {
            val razlika = it.broj - prethodno
            razlika.signum() >= 0 && razlika <= NAJVECA_RAZLIKA
        }
        // Cijelo brojilo ili pročitani zarez pouzdaniji su od kratkog niza kojem smo sami dodali
        // decimale; tek među jednako pouzdanima prednost ima stanje najbliže prethodnom.
        return moguci.sortedWith(compareBy<Kandidat> { it.razina }.thenBy { it.broj - prethodno }).map { it.broj } +
            ostali.sortedBy { (it.broj - prethodno).abs() }.map { it.broj }
    }
}
