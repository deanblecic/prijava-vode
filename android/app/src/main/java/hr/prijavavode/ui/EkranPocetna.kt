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
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import hr.prijavavode.BuildConfig
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
        if (vm.novaVerzija) KarticaNadogradnje(vm)
        when {
            vm.radi && ja == null -> CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
            ja == null -> Button(onClick = vm::osvjezi) { Text("Pokušaj ponovno") }
            ja.stanovi.isEmpty() -> Text("Niste upisani kao vlasnik nijednog stana. Javite se ovlaštenom predstavniku suvlasnika.")
            // Stanovi u više zgrada: naslov sa adresom iznad stanova svake zgrade.
            ja.zgrade.size > 1 -> ja.stanoviPoZgradama().forEach { (zgrada, stanovi) ->
                Text(
                    zgrada?.naziv ?: "Ostali stanovi",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 8.dp),
                )
                stanovi.forEach { KarticaStana(it, vm) }
            }
            else -> ja.stanovi.forEach { KarticaStana(it, vm) }
        }
        if (ja != null) {
            OutlinedButton(onClick = vm::otvoriPovijest, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Filled.History, null)
                Spacer(Modifier.padding(4.dp))
                Text("Povijest očitanja")
            }
        }
        Text(
            "Verzija ${BuildConfig.VERSION_NAME}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
    }
}

@Composable
private fun KarticaStana(stan: Stan, vm: GlavniViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Stan ${stan.brojStana}", style = MaterialTheme.typography.titleLarge)
            val vodomjer = stan.vodomjeri.firstOrNull()
            if (vodomjer == null) {
                Text("Stan nema upisan vodomjer. Javite se ovlaštenom predstavniku suvlasnika.")
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

@Composable
private fun KarticaNadogradnje(vm: GlavniViewModel) {
    val nova = vm.ja?.aplikacija?.verzija
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.SystemUpdate, null, tint = MaterialTheme.colorScheme.primary)
                Text("Dostupna je nova verzija aplikacije (1.$nova).", Modifier.padding(start = 12.dp))
            }
            val postotak = vm.preuzimanje
            if (postotak != null) {
                Text("Preuzimanje… $postotak %")
                LinearProgressIndicator(progress = { postotak / 100f }, modifier = Modifier.fillMaxWidth())
            } else {
                Button(onClick = vm::nadogradi, modifier = Modifier.fillMaxWidth().height(52.dp)) { Text("Nadogradi") }
            }
        }
    }
    if (vm.ponudiNadogradnju) {
        AlertDialog(
            onDismissRequest = { vm.ponudiNadogradnju = false },
            title = { Text("Nova verzija") },
            text = { Text("Dostupna je nova verzija aplikacije Očitanje vode. Želite li je sada instalirati? Vaša prijava i podaci ostaju.") },
            confirmButton = { TextButton(onClick = vm::nadogradi) { Text("Nadogradi") } },
            dismissButton = { TextButton(onClick = { vm.ponudiNadogradnju = false }) { Text("Kasnije") } },
        )
    }
}
