package hr.prijavavode.ocr

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Iz teksta koji OCR pročita s brojila izvlači moguća stanja vodomjera.
 *
 * Vodomjer obično ima 5 crnih znamenki (m³) i 3 crvene (litre), često bez
 * decimalnog zareza, pa se svaki niz znamenki tumači na više načina. Prednost
 * ima cijelo brojilo (7 i više znamenki ili pročitani zarez) pred kraćim nizovima
 * s natpisa na kućištu, a među jednako pouzdanima tumačenje najbliže prethodnom stanju.
 */
object CitacBrojila {

    /** Najveća razumna mjesečna potrošnja jednog stana, u m³ (i uz curenje vode). */
    private val NAJVECA_RAZLIKA = BigDecimal(100)

    /** Najveći skok koji se još nudi ako je pročitano cijelo brojilo (više neočitanih mjeseci). */
    private val NAJVECI_SKOK = BigDecimal(300)

    /**
     * Stanje stanskog vodomjera praktički nikad ne prelazi 10 000 m³, a serijski broj
     * protumačen kao stanje (npr. 60700247 → 60 700,247) gotovo uvijek prelazi.
     */
    private val NAJVECE_STANJE = BigDecimal(10000)

    /** Server i stanje čuvaju na litru (tri decimale); četvrta crvena znamenka se odbacuje. */
    private const val DECIMALE = 3

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
    /**
     * Brojilo ima barem 5 kotačića; kraći niz ("D92" → 092, "9222", "Z-14-1016") je natpis ili
     * komadić brojila i ne smije se ponuditi kao stanje.
     */
    private val ZNAMENKE = Regex("""\d{5,}""")
    private val GODINA = Regex("""(19[5-9]\d|20[0-3]\d)""")
    private val SAMO_ZNAMENKE = Regex("""\d+""")

    /** Toliko znamenki ima cijelo brojilo (5 crnih + 3 crvene, ponekad 4 + 4 ili 6 + 2). */
    private const val CIJELO_BROJILO = 7

    /**
     * Kandidat i koliko mu vjerujemo: 0 = cijelo brojilo ili izričiti zarez,
     * 1 = kraći niz znamenki (dio brojila ili natpis s kućišta).
     */
    private class Kandidat(
        val broj: BigDecimal,
        val razina: Int,
        val vodecaNula: Boolean,
        /** Decimale su točno tri pročitane znamenke (crveni kotačići), a ne naše nagađanje. */
        val triDecimale: Boolean = false,
    )

    fun kandidati(linije: List<String>, prethodno: BigDecimal?): List<BigDecimal> {
        val svi = mutableListOf<Kandidat>()
        val ocisceneLinije = linije.map(::popraviZnakove)
        for (ocisceno in ocisceneLinije) {
            // "6.131.92" (oznaka odobrenja) nije broj sa zarezom.
            DECIMALNI.findAll(ocisceno).filterNot { dioOznake(ocisceno, it.range) || ocisceno.getOrNull(it.range.last + 1) in listOf('.', ',') }.forEach { m ->
                val broj = BigDecimal("${m.groupValues[1]}.${m.groupValues[2]}")
                // "x 0,0001" s kućišta je oznaka, a ne stanje; stanje manje od 1 m³ ima samo nov vodomjer.
                svi += Kandidat(broj, if (broj < BigDecimal.ONE) 1 else 0, m.groupValues[1].startsWith("0"), m.groupValues[2].length == 3)
            }
            // Kotačići brojila često se pročitaju kao znamenke odvojene razmacima ili dvotočkama
            // (pregrade između kotačića, npr. "1:9:9:3").
            val zbijeno = ocisceno.replace(Regex("""(?<=\d)[\s:]+(?=\d)"""), "")
            ZNAMENKE.findAll(zbijeno)
                .filter { it.value.length >= CIJELO_BROJILO || !dioOznake(zbijeno, it.range) }
                // Godina proizvodnje ispod serijskog broja ("2006") nije stanje.
                .filterNot { GODINA.matches(it.value) }
                .forEach { m -> svi += tumacenja(m.value) }
        }
        // Crne i crvene znamenke ponekad se prepoznaju kao dva zasebna retka (npr. "00784" i "806").
        ocisceneLinije.zipWithNext().forEach { (crne, crvene) ->
            val c = crne.replace(Regex("""\s+"""), "")
            val r = crvene.replace(Regex("""\s+"""), "")
            if (SAMO_ZNAMENKE.matches(c) && SAMO_ZNAMENKE.matches(r) && c.length in 4..6 && r.length in 2..4) {
                svi += Kandidat(BigDecimal("$c.$r"), 0, c.startsWith("0"), r.length == 3)
            }
        }
        // 184.12 i 184.120 su isti broj; zadržava se najpouzdanije tumačenje.
        val jedinstveni = svi
            .map { if (it.broj.scale() > DECIMALE) Kandidat(it.broj.setScale(DECIMALE, RoundingMode.DOWN), it.razina, it.vodecaNula, it.triDecimale) else it }
            .sortedWith(compareBy<Kandidat> { it.razina }.thenBy { if (it.triDecimale) 0 else 1 })
            .distinctBy { normaliziraj(it.broj.stripTrailingZeros()) }
        return poredaj(jedinstveni, prethodno)
    }

    /**
     * Kratak niz znamenki koji je dio oznake s kućišta ("Z-14-1016", "PTB018", "05/240734",
     * "M150102", "6.131.92") nije stanje. Kotačići brojila stoje odvojeno od slova i crtica.
     */
    private fun dioOznake(tekst: String, raspon: IntRange): Boolean {
        val prije = tekst.getOrNull(raspon.first - 1)
        val poslije = tekst.getOrNull(raspon.last + 1)
        return (prije != null && (prije.isLetter() || prije in "-/.,")) || (poslije != null && poslije in "-/")
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
                rezultat += Kandidat(BigDecimal(niz.substring(0, niz.length - decimala) + "." + niz.takeLast(decimala)), razina, nula, decimala == 3)
            }
        }
        return rezultat
    }

    private fun normaliziraj(broj: BigDecimal): BigDecimal =
        if (broj.scale() < 0) broj.setScale(0) else broj

    /**
     * Redoslijed ponude; prvi kandidat se upisuje u polje za potvrdu. Kandidat koji ničim ne
     * izgleda kao stanje radije se izostavlja, pa suvlasnik upisuje broj sam, nego da se
     * ponudi uvjerljiv krivi broj.
     */
    private fun poredaj(kandidati: List<Kandidat>, prethodno: BigDecimal?): List<BigDecimal> {
        if (prethodno == null || prethodno.signum() == 0) {
            // Bez prethodnog stanja nema provjere razumnosti, pa se nudi samo cijelo brojilo s tri
            // pročitane crvene znamenke i razumne veličine; prednost ima ono s vodećim nulama
            // (serijski broj ih obično nema).
            return kandidati
                .filter { it.razina == 0 && it.triDecimale && it.broj >= BigDecimal.ONE && it.broj < NAJVECE_STANJE }
                .sortedWith(compareBy<Kandidat> { if (it.vodecaNula) 0 else 1 }.thenByDescending { it.broj.precision() })
                .map { it.broj }
        }
        val (moguci, ostali) = kandidati.partition {
            val razlika = it.broj - prethodno
            razlika.signum() >= 0 && razlika <= NAJVECA_RAZLIKA
        }
        // Cijelo brojilo ili pročitani zarez pouzdaniji su od kratkog niza kojem smo sami dodali
        // decimale; tek među jednako pouzdanima prednost ima stanje najbliže prethodnom.
        // Veći skok (npr. nakon više neočitanih mjeseci) nudi se samo ako je pročitano cijelo brojilo.
        val veciSkok = ostali.filter {
            val razlika = it.broj - prethodno
            it.razina == 0 && razlika.signum() > 0 && razlika <= NAJVECI_SKOK
        }
        return moguci.sortedWith(compareBy<Kandidat> { it.razina }.thenBy { it.broj - prethodno }).map { it.broj } +
            veciSkok.sortedBy { it.broj - prethodno }.map { it.broj }
    }
}
