package hr.prijavavode.podsjetnik

import hr.prijavavode.podaci.Ja
import hr.prijavavode.podaci.Ocitanje
import hr.prijavavode.podaci.PostavkePodsjetnika
import hr.prijavavode.podaci.Stan
import hr.prijavavode.podaci.Vodomjer
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime

class PodsjetnikTest {
    private fun ocitanje(status: String) = Ocitanje(
        id = 1, vodomjer = 1, brojStana = "", razdoblje = "2026-10", datumOcitanja = "",
        prethodnoStanje = "1", novoStanje = "2", razlika = "1", status = status,
    )

    private fun stan(broj: String, ocitanje: Ocitanje?) =
        Stan(id = 1, brojStana = broj, vodomjeri = listOf(Vodomjer(id = 1, prethodnoStanje = "1", ocitanjeOvajMjesec = ocitanje)))

    private val ja = Ja(
        korisnickoIme = "ana", ime = "Ana", prezime = "Horvat",
        stanovi = listOf(stan("3", null), stan("4", ocitanje("predano")), stan("5", ocitanje("odbijeno"))),
        podsjetnik = PostavkePodsjetnika(dan = 26, sat = 9),
    )

    @Test
    fun prijeDanaOcitanjaNemaPodsjetnika() {
        assertEquals(emptyList<String>(), Podsjetnik.neocitaniStanovi(ja, LocalDate.of(2026, 10, 25)))
    }

    @Test
    fun odDanaOcitanjaNeocitaniIOdbijeni() {
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(ja, LocalDate.of(2026, 10, 26)))
        assertEquals(listOf("3", "5"), Podsjetnik.neocitaniStanovi(ja, LocalDate.of(2026, 10, 31)))
    }

    @Test
    fun sljedeciTermin() {
        val jutro = LocalDateTime.of(2026, 10, 26, 7, 30)
        assertEquals(Duration.ofMinutes(90), Podsjetnik.doSljedeceg(9, jutro))
        val upravoPokrenut = LocalDateTime.of(2026, 10, 26, 9, 0, 20)
        assertEquals(LocalDateTime.of(2026, 10, 27, 9, 0), upravoPokrenut.plus(Podsjetnik.doSljedeceg(9, upravoPokrenut)))
    }

    @Test
    fun tekstObavijesti() {
        assertEquals("Vodomjer stana 3 za ovaj mjesec još nije očitan.", Podsjetnik.tekst(listOf("3")))
        assertEquals("Vodomjeri stanova 3, 5 za ovaj mjesec još nisu očitani.", Podsjetnik.tekst(listOf("3", "5")))
    }
}
