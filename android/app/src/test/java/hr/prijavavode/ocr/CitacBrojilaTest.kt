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
}
