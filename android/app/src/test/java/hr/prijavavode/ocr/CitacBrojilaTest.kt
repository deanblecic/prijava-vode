package hr.prijavavode.ocr

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class CitacBrojilaTest {
    private fun prvi(linije: List<String>, prethodno: String?) =
        CitacBrojila.kandidati(linije, prethodno?.let(::BigDecimal)).first()

    @Test
    fun osamZnamenkiBezZareza() {
        assertEquals(BigDecimal("184.120"), prvi(listOf("00184120"), "181.549"))
    }

    @Test
    fun znamenkeOdvojeneRazmacima() {
        assertEquals(BigDecimal("184.120"), prvi(listOf("0 0 1 8 4 1 2 0"), "181.549"))
    }

    @Test
    fun izricitiZarez() {
        assertEquals(BigDecimal("184.12"), prvi(listOf("00184,12 m3"), "181.549"))
    }

    @Test
    fun samoCrneZnamenke() {
        assertEquals(BigDecimal("184"), prvi(listOf("00184"), "181.549"))
    }

    @Test
    fun ocrZamjenaSlova() {
        assertEquals(BigDecimal("184.120"), prvi(listOf("OO184l2O"), "181.549"))
    }

    @Test
    fun ignoriraSerijskiBrojINatpise() {
        val linije = listOf("DN15 Q3 2,5", "Nr. 2019044781", "00184120", "m3")
        assertEquals(BigDecimal("184.120"), prvi(linije, "181.549"))
    }

    @Test
    fun bezPrethodnogPrednostTriDecimale() {
        assertEquals(BigDecimal("184.120"), prvi(listOf("00184120"), null))
    }

    @Test
    fun nistaKadNemaZnamenki() {
        assertTrue(CitacBrojila.kandidati(listOf("m3", "DN"), BigDecimal.ONE).isEmpty())
    }

    // Siemens vodomjer sa slike test/resources/vodomjeri/siemens-784806.png: crne 00784, crvene 806.
    // Natpis "PTB018" ispod brojila pretvarao se u "P78018" pa je aplikacija nudila 780,180.
    private val siemensNatpisi = listOf("CE M15 0102", "15686132", "Q3 2,5 DE-08-MI001-PTB018", "T30 R160 1,6 MPa", "m3", "SIEMENS")

    @Test
    fun siemensNatpisSKucistaNijeStanje() {
        val linije = siemensNatpisi.take(2) + "00784806" + siemensNatpisi.drop(2)
        assertEquals(BigDecimal("784.806"), prvi(linije, "770.512"))
    }

    @Test
    fun siemensBezPrethodnogNeUzimaSerijskiBroj() {
        val linije = siemensNatpisi.take(2) + "0 0 7 8 4 8 0 6" + siemensNatpisi.drop(2)
        assertEquals(BigDecimal("784.806"), prvi(linije, null))
    }

    @Test
    fun siemensCrneICrveneUZasebnimRedovima() {
        val linije = siemensNatpisi.take(2) + listOf("00784", "806") + siemensNatpisi.drop(2)
        assertEquals(BigDecimal("784.806"), prvi(linije, "770.512"))
    }

    @Test
    fun oznakaSKucistaNeDajeLaznoStanje() {
        // Ako brojilo uopće nije pročitano, bolje je ne ponuditi ništa nego 780,18.
        val kandidati = CitacBrojila.kandidati(siemensNatpisi, BigDecimal("770.512"))
        assertTrue(kandidati.none { it.compareTo(BigDecimal("780.18")) == 0 })
    }

    @Test
    fun cijeloBrojiloPrijeKratkogNizaBlizegPrethodnom() {
        assertEquals(BigDecimal("784.806"), prvi(listOf("7805", "00784806"), "770.512"))
    }
}
