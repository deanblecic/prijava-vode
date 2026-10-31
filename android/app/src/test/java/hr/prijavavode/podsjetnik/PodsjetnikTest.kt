package hr.prijavavode.podsjetnik

import hr.prijavavode.podaci.Ja
import hr.prijavavode.podaci.Ocitanje
import hr.prijavavode.podaci.PostavkePodsjetnika
import hr.prijavavode.podaci.Stan
import hr.prijavavode.podaci.Vodomjer
import hr.prijavavode.podaci.Zgrada
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Duration
import java.time.LocalDateTime

class PodsjetnikTest {
    private fun ocitanje(status: String) = Ocitanje(
        id = 1, vodomjer = 1, brojStana = "", razdoblje = "2026-10", datumOcitanja = "",
        prethodnoStanje = "1", novoStanje = "2", razlika = "1", status = status,
    )

    private fun stan(broj: String, ocitanje: Ocitanje?, zgrada: Long? = null) = Stan(
        id = 1, zgrada = zgrada, brojStana = broj,
        vodomjeri = listOf(Vodomjer(id = 1, prethodnoStanje = "1", ocitanjeOvajMjesec = ocitanje)),
    )

    private val ja = Ja(
        korisnickoIme = "ana", ime = "Ana", prezime = "Horvat",
        stanovi = listOf(stan("3", null), stan("4", ocitanje("predano")), stan("5", ocitanje("odbijeno"))),
        podsjetnik = PostavkePodsjetnika(dan = 26, sat = 9),
    )

    private fun u(dan: Int, sat: Int = 9) = LocalDateTime.of(2026, 10, dan, sat, 0)

    @Test
    fun prijeDanaOcitanjaNemaPodsjetnika() {
        assertEquals(emptyList<String>(), Podsjetnik.neocitaniStanovi(ja, u(25)))
    }

    @Test
    fun odDanaOcitanjaNeocitaniIOdbijeni() {
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(ja, u(26)))
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(ja, u(31)))
    }

    @Test
    fun stanoviURazlicitimZgradamaPoPravilimaSvojeZgrade() {
        val rijeka = Zgrada(id = 1, ulica = "Moše Albaharija", kucniBroj = "2", grad = "Rijeka",
            podsjetnik = PostavkePodsjetnika(dan = 26, sat = 9))
        val zagreb = Zgrada(id = 2, ulica = "Ilica", kucniBroj = "10", grad = "Zagreb",
            podsjetnik = PostavkePodsjetnika(dan = 20, sat = 11))
        val sanja = Ja(
            korisnickoIme = "sanja", ime = "Sanja", prezime = "Njirić",
            stanovi = listOf(stan("17", null, zgrada = 1), stan("3", null, zgrada = 2)),
            zgrade = listOf(rijeka, zagreb),
        )
        assertEquals(listOf(9, 11), sanja.satiPodsjetnika)
        assertEquals(emptyList<String>(), Podsjetnik.neocitaniStanovi(sanja, u(20, 9)))
        assertEquals(listOf("3 (Ilica 10)"), Podsjetnik.neocitaniStanovi(sanja, u(21, 11)))
        assertEquals(listOf("17 (Moše Albaharija 2)", "3 (Ilica 10)"), Podsjetnik.neocitaniStanovi(sanja, u(26, 12)))
        assertEquals(listOf(rijeka to listOf(sanja.stanovi[0]), zagreb to listOf(sanja.stanovi[1])),
            sanja.stanoviPoZgradama())
    }

    @Test
    fun samoNaDanePodsjetnikaKojeJeOdabraoAdministrator() {
        val prviIRok = ja.copy(podsjetnik = PostavkePodsjetnika(dan = 1, sat = 9, dani = listOf(1, 20), rok = "2026-10-20"))
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(prviIRok, u(1)))
        assertEquals(emptyList<String>(), Podsjetnik.neocitaniStanovi(prviIRok, u(2)))
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(prviIRok, u(20)))
        assertEquals(emptyList<String>(), Podsjetnik.neocitaniStanovi(prviIRok, u(26)))
    }

    @Test
    fun sljedeciTermin() {
        val jutro = LocalDateTime.of(2026, 10, 26, 7, 30)
        assertEquals(Duration.ofMinutes(90), Podsjetnik.doSljedeceg(9, jutro))
        val upravoPokrenut = LocalDateTime.of(2026, 10, 26, 9, 0, 20)
        assertEquals(LocalDateTime.of(2026, 10, 27, 9, 0), upravoPokrenut.plus(Podsjetnik.doSljedeceg(9, upravoPokrenut)))
        assertEquals(Duration.ofMinutes(119), Podsjetnik.doSljedeceg(listOf(9, 11), LocalDateTime.of(2026, 10, 26, 9, 1)))
    }

    @Test
    fun tekstObavijesti() {
        assertEquals("Vodomjer stana 3 za ovaj mjesec još nije očitan.", Podsjetnik.tekst(listOf("3")))
        assertEquals("Vodomjeri stanova 3, 5 za ovaj mjesec još nisu očitani.", Podsjetnik.tekst(listOf("3", "5")))
    }
}
