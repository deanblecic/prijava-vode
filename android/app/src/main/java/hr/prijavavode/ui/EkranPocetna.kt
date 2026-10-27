package hr.prijavavode.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.History
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import hr.prijavavode.GlavniViewModel
import hr.prijavavode.podaci.Stan

@Composable
fun EkranPocetna(vm: GlavniViewModel) {
    val ja = vm.ja
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (ja != null) "Pozdrav, ${ja.ime.ifBlank { ja.korisnickoIme }}" else "Očitanje vode",
                style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f),
            )
            TextButton(onClick = vm::odjava) { Text("Odjava") }
        }
        vm.poruka?.let {
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
                    Text(it, Modifier.padding(start = 12.dp).weight(1f))
                    TextButton(onClick = { vm.poruka = null }) { Text("OK") }
                }
            }
        }
        when {
            vm.radi && ja == null -> CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
            ja == null -> Button(onClick = vm::osvjezi) { Text("Pokušaj ponovno") }
            ja.stanovi.isEmpty() -> Text("Niste upisani kao vlasnik nijednog stana. Javite se upravitelju zgrade.")
            else -> ja.stanovi.forEach { KarticaStana(it, vm) }
        }
        if (ja != null) {
            OutlinedButton(onClick = vm::otvoriPovijest, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Filled.History, null)
                Spacer(Modifier.padding(4.dp))
                Text("Povijest očitanja")
            }
        }
    }
}

@Composable
private fun KarticaStana(stan: Stan, vm: GlavniViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Stan ${stan.brojStana}", style = MaterialTheme.typography.titleLarge)
            val vodomjer = stan.vodomjeri.firstOrNull()
            if (vodomjer == null) {
                Text("Stan nema upisan vodomjer. Javite se upravitelju zgrade.")
                return@Column
            }
            Text("Prethodno stanje: ${hr(vodomjer.prethodnoStanje)} m³")
            val ovaj = vodomjer.ocitanjeOvajMjesec
            Text("Očitanje za ${nazivMjeseca()}", style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp))
            if (ovaj == null || ovaj.status == "odbijeno") {
                if (ovaj != null) Text("Prethodno predano očitanje je odbijeno. Snimite vodomjer ponovno.",
                    color = MaterialTheme.colorScheme.error)
                else Text("Još niste predali očitanje.")
                Button(
                    onClick = { vm.otvoriKameru(vodomjer) },
                    modifier = Modifier.fillMaxWidth().height(56.dp).padding(top = 4.dp),
                ) {
                    Icon(Icons.Filled.CameraAlt, null)
                    Spacer(Modifier.padding(4.dp))
                    Text("Očitaj vodomjer")
                }
            } else {
                Text("Novo stanje: ${hr(ovaj.novoStanje)} m³")
                Text("Potrošnja: ${hr(ovaj.razlika)} m³", style = MaterialTheme.typography.titleMedium)
                Text(ovaj.statusTekst, color = MaterialTheme.colorScheme.primary)
                if (ovaj.status == "predano") {
                    TextButton(onClick = { vm.otvoriKameru(vodomjer) }) { Text("Ispravi očitanje") }
                }
            }
        }
    }
}
