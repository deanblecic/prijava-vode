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

    // Retci u nastavku su ono što OCR stvarno pročita s fotografija u test/resources/vodomjeri
    // (provjereno OCR-om na računalu; ML Kit na mobitelu daje slične retke, često s razmacima).

    private val elster = listOf(
        "D92", "B-H A-V", "613192", "Qn15mm", "1993426", "ELSTER", "ELSTERMesstechnik",
        "HAZ-141016", "X0.0001", "Tmax+30c", "60700247", "2006",
    )

    @Test
    fun elsterSPrethodnim() {
        assertEquals(BigDecimal("1993.426"), prvi(elster, "1981.004"))
    }

    @Test
    fun elsterBezPrethodnogNeUzimaSerijskiBrojNiOznakuMnozitelja() {
        // Serijski 60700247 i "x 0,0001" ranije su dolazili prije stvarnog stanja.
        assertEquals(BigDecimal("1993.426"), prvi(elster, null))
    }

    @Test
    fun elsterPregradeIzmeduKotacica() {
        assertEquals(BigDecimal("1993.426"), prvi(listOf("1:9:9:3:4 2 6", "x 0,0001", "60700247"), "1981.004"))
    }

    @Test
    fun cetvrtaCrvenaZnamenkaSeOdbacuje() {
        // Elster ima i četvrti, poluzakrenuti crveni kotačić; stanje se sprema na litru.
        assertEquals(BigDecimal("1993.426"), prvi(listOf("19934266"), "1981.004"))
    }

    private val unimag = listOf(
        "Unimag", "ACTARIS", "TUA", "00001元", "HRZ-14-109830COn1516baB-A", "02473273", "05/240734",
    )

    @Test
    fun unimagSPrethodnim() {
        assertEquals(BigDecimal("2473.273"), prvi(unimag, "2460.118"))
    }

    @Test
    fun unimagBezPrethodnog() {
        assertEquals(BigDecimal("2473.273"), prvi(unimag, null))
    }

    @Test
    fun unimagRazmaciIOznakeSKucista() {
        val linije = listOf("x0,0001 m3", "HR Z-14-1098 30°C Qn1,5 16bar BH-A", "0 2 4 7 3 2 7 3", "05/240734")
        assertEquals(BigDecimal("2473.273"), prvi(linije, "2460.118"))
    }

    private val siemensOdsjaj = listOf(
        "CE", "M140102", "14004945", "00497139", "m3", "Q32,5DE-08-MI001.PTB018", "SIEMENS",
    )

    @Test
    fun siemensOdsjajSPrethodnim() {
        assertEquals(BigDecimal("497.139"), prvi(siemensOdsjaj, "489.870"))
    }

    @Test
    fun siemensOdsjajBezPrethodnog() {
        assertEquals(BigDecimal("497.139"), prvi(siemensOdsjaj, null))
    }

    private val abb = listOf(
        "C92", "BHAV", "6.131.92", "Qn2.5m/h", "0595604", "ABB", "ABBKentMesstechnik",
        "2-14-1016", "X0,000", "nax", "30403515", "2003",
    )

    @Test
    fun abbSPrethodnim() {
        assertEquals(BigDecimal("595.604"), prvi(abb, "588.310"))
    }

    @Test
    fun abbBezPrethodnog() {
        assertEquals(BigDecimal("595.604"), prvi(abb, null))
    }

    @Test
    fun mutnaFotografijaBezBrojilaNeNudiLaznoStanje() {
        // Na mutnoj fotografiji (887,084) OCR pročita samo natpise; nijedan ne smije izgledati kao stanje.
        val linije = listOf("CE", "M150102", "15959824", "130R50HR")
        val prethodno = BigDecimal("880.215")
        val moguci = CitacBrojila.kandidati(linije, prethodno).filter {
            it >= prethodno && it - prethodno <= BigDecimal(200)
        }
        assertTrue(moguci.isEmpty())
    }

    @Test
    fun mutnaFotografijaKadSeBrojiloProcita() {
        val linije = listOf("CE M15 0102", "15959824", "0 0 8 8 7 0 8 4", "2,5 DE-08-MI001-PTB018")
        assertEquals(BigDecimal("887.084"), prvi(linije, "880.215"))
    }

    private val siemens781 = listOf(
        "M15", "0102", "15686132", "00781885", "Q32,5DE-08-MI001-PTB018", "T30R80H/R40V16MPa", "SIEMENS",
    )

    @Test
    fun siemens781SPrethodnim() {
        assertEquals(BigDecimal("781.885"), prvi(siemens781, "775.020"))
    }

    @Test
    fun siemens781BezPrethodnog() {
        assertEquals(BigDecimal("781.885"), prvi(siemens781, null))
    }

    @Test
    fun istiVodomjerSljedeceOcitanje() {
        // Fotografije siemens-781885 i siemens-784806 su isti vodomjer (serijski 15686132).
        val linije = listOf("CE M15 0102", "15686132", "00784806", "Q3 2,5 DE-08-MI001-PTB018")
        assertEquals(BigDecimal("784.806"), prvi(linije, "781.885"))
    }

    @Test
    fun unimagSerifneJediniceKaoSlovoI() {
        // Na Unimagu (1301,391) jedinica ima serife pa je OCR čita kao "I" ili ne pročita brojilo.
        assertEquals(BigDecimal("1301.391"), prvi(listOf("x0.0001m3", "0I30I39I", "05/468527"), "1290.004"))
        val krivo = listOf("HRZ-14-109830°C Qn15 16barBH-A", "x0.0001m3", "16210210", "05/468527")
        val prethodno = BigDecimal("1290.004")
        assertTrue(CitacBrojila.kandidati(krivo, prethodno).none { it >= prethodno && it - prethodno <= BigDecimal(200) })
    }

    private val unimagNovine = listOf(
        "Nove Opel Cos", "Unimag", "ACTARIS", "TU", "7Z-10-1098 30°CQn1515bal", "BM-A", "0.0001m",
        "01666930", "05/240433", "G2program", "Cd pocetka 2006.godinekod", "nas je prodano 54.988 vozilo.U",
        "dlucilo374Hrvata,azaVectru", "321 kupac.Opel u Hrvaiskoj evr-", "jeprodano 4508Aay", "u/2005Corsl",
    )

    @Test
    fun unimagNovineUPozadiniSPrethodnim() {
        assertEquals(BigDecimal("1666.930"), prvi(unimagNovine, "1655.402"))
    }

    @Test
    fun unimagNovineUPozadiniBezPrethodnog() {
        assertEquals(BigDecimal("1666.930"), prvi(unimagNovine, null))
    }

    @Test
    fun stariVodomjerSKazaljkama() {
        // Samo 5 kotačića (02565); decimale su na kazaljkama koje OCR ne čita, pa se nudi cijeli broj.
        val linije = listOf(
            "Qn 2,5 m3/h", "PN 16 bar", "Δp 0,6 bar", "02565", "M100", "HR Z-14-1062", "x 0,1", "x 0,01", "x 0,001",
        )
        assertEquals(BigDecimal("2565"), prvi(linije, "2551.300"))
    }

    @Test
    fun itronUnimag() {
        val linije = listOf("D11CB014097", "01039982", "G13110", "HRZ-14-1098", "Unimag", "TU4BH-A", "30°cQn2.516bar", "Itron")
        assertEquals(BigDecimal("1039.982"), prvi(linije, "1031.250"))
        assertEquals(BigDecimal("1039.982"), prvi(linije, null))
    }

    @Test
    fun elster1577() {
        val linije = listOf(
            "①92", "BH A-V", "@6131.92", "Qn2.5m／h", "1577014", "ELSTER", "ELSTERMesstechnik", "EV-K",
            "HRZ-14-1016", "Tmax+30c", "X0.0001", "63602318", "2006",
        )
        assertEquals(BigDecimal("1577.014"), prvi(linije, "1569.700"))
        assertEquals(BigDecimal("1577.014"), prvi(linije, null))
    }

    // elster-1510133 i elster-1524218 su isti vodomjer (serijski 53700912), dva uzastopna očitanja.

    @Test
    fun elsterPregradeKaoDvotocke() {
        assertEquals(BigDecimal("1510.133"), prvi(listOf("1:5:1:0:1 3 3", "x 0,0001", "53700912", "2005"), "1497.020"))
    }

    @Test
    fun elsterCetvrtiCrveniKotacic() {
        assertEquals(BigDecimal("1510.133"), prvi(listOf("15101333", "x 0,0001", "53700912"), "1497.020"))
    }

    @Test
    fun elsterMutnaNakosenaNeNudiLaznoStanje() {
        // Na mutnoj, nakošenoj fotografiji (1524,218) OCR pregrade između kotačića čita kao znamenke.
        val linije = listOf("331", "1512341218", "STER", "00001", "esstechni", "53700912", "2005")
        val prethodno = BigDecimal("1510.133")
        assertTrue(CitacBrojila.kandidati(linije, prethodno).none { it >= prethodno && it - prethodno <= BigDecimal(200) })
    }

    @Test
    fun elsterSljedeceOcitanje() {
        assertEquals(BigDecimal("1524.218"), prvi(listOf("1 5 2 4 2 1 8", "x 0,0001", "53700912"), "1510.133"))
    }

    private fun nistaUvjerljivo(linije: List<String>, prethodno: String) {
        val p = BigDecimal(prethodno)
        val moguci = CitacBrojila.kandidati(linije, p).filter { it >= p && it - p <= BigDecimal(100) }
        assertTrue("Ponuđeno lažno stanje: $moguci", moguci.isEmpty())
    }

    @Test
    fun elsterUdaljenaMutnaNeNudiLaznoStanje() {
        // elster-1970.jpg: isti vodomjer kao elster-1993426, raniji mjesec; OCR ne pročita brojilo.
        nistaUvjerljivo(listOf("ELSTER", "EuSTERMesstecmik", "xo0001", "Tmax-5oc", "80700247", "2008"), "1961.300")
    }

    @Test
    fun elsterKlasaOdobrenjaNijeStanje() {
        // elster-79079.jpg: OCR ne pročita brojilo, a "Z-14-1015" je davao 101,5.
        val linije = listOf("BHAV", "613192", "2On15mm", "ELSTER", "ELSTER Messtechnik", "EN-K", "HRZ:14-1015", "61800358", "X0.0001", "2008")
        nistaUvjerljivo(linije, "74.512")
    }

    @Test
    fun elsterKratkiNizSaStakla() {
        // elster-84230.jpg: OCR pročita samo "23:0" (230), predaleko od prethodnog stanja.
        nistaUvjerljivo(listOf("D92", "B-HA-V", "6.131.92", "Qn1.5mm", "23:0", "ELSTER", "HRZ-14-1016", "61800358", "X0.0001"), "79.079")
    }

    @Test
    fun elsterMaloStanjeSCetiriCrneZnamenke() {
        // elster-89222.jpg: 4 crne + 3 crvene znamenke (0089 222).
        val linije = listOf("D 92", "6.131.92", "Qn 1,5 m3/h", "0 0 8 9 2 2 2", "ELSTER", "Z-14-1016", "x 0,0001", "61800358")
        assertEquals(BigDecimal("89.222"), prvi(linije, "84.230"))
        assertEquals(BigDecimal("89.222"), prvi(linije, null))
    }

    @Test
    fun wehrleNakosenaNeNudiLaznoStanje() {
        // wehrle-319137.jpg: OCR pročita samo serijski broj i natpise.
        nistaUvjerljivo(listOf("2018", "ETK-EAX", "23617248", "EHRL", "6MPa", "2.5DE-08-MI001-PTB018", "R80HR50M"), "314.704")
    }

    @Test
    fun wehrleKadSeBrojiloProcita() {
        val linije = listOf("E. Wehrle GmbH", "M18 0102", "23617248", "00319137", "Q3 2,5 DE-08-MI001-PTB018", "2018", "ETK-EAX")
        assertEquals(BigDecimal("319.137"), prvi(linije, "314.704"))
        assertEquals(BigDecimal("319.137"), prvi(linije, null))
    }

    /**
     * Svih 20 fotografija: retci koje je OCR pročitao (ocr-retci.tsv: datoteka, točno stanje,
     * prethodno stanje, retci). Na ovim retcima stari je kod nudio krivo stanje u 13 slučajeva.
     */
    @Test
    fun zbirkaFotografija() {
        val redovi = javaClass.getResource("/vodomjeri/ocr-retci.tsv")!!.readText().lines().filter { it.isNotBlank() }
        var tocno = 0
        val krivo = mutableListOf<String>()
        for (red in redovi) {
            val d = red.split("\t")
            val stanje = BigDecimal(d[1])
            val prvi = CitacBrojila.kandidati(d.drop(3), BigDecimal(d[2])).firstOrNull() ?: continue
            val pogodak = if (stanje.scale() == 0) prvi.toBigInteger() == stanje.toBigInteger() else prvi.compareTo(stanje) == 0
            if (pogodak) tocno++ else krivo += "${d[0]}: $prvi"
        }
        assertEquals(20, redovi.size)
        assertTrue("Točno samo $tocno", tocno >= 8)
        // Preostale dvije pogreške su fotografije na kojima je OCR ispustio ili dodao znamenku brojila.
        assertTrue("Krivo ponuđeno: $krivo", krivo.size <= 2)
    }
}
