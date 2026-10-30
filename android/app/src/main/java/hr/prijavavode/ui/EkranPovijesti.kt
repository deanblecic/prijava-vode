package hr.prijavavode.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import hr.prijavavode.GlavniViewModel

@Composable
fun EkranPovijesti(vm: GlavniViewModel) {
    Column(Modifier.fillMaxSize().safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(8.dp)) {
            IconButton(onClick = vm::natrag) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Natrag") }
            Text("Povijest očitanja", style = MaterialTheme.typography.titleLarge)
        }
        if (vm.povijest.isEmpty()) {
            Text("Još nema očitanja.", Modifier.padding(20.dp))
        }
        LazyColumn(
            Modifier.padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(vm.povijest, key = { it.id }) { o ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row {
                            Text(nazivRazdoblja(o.razdoblje).replaceFirstChar { it.uppercase() },
                                style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            Text("${hr(o.razlika)} m³", style = MaterialTheme.typography.titleMedium)
                        }
                        val zgrada = vm.ja?.takeIf { it.zgrade.size > 1 }?.zgrade?.firstOrNull { it.id == o.zgrada }
                        val adresa = zgrada?.let { ", ${it.ulica} ${it.kucniBroj}" }.orEmpty()
                        Text("Stan ${o.brojStana}$adresa · ${datumIVrijeme(o.datumOcitanja)}",
                            style = MaterialTheme.typography.bodySmall)
                        Text("${hr(o.prethodnoStanje)} → ${hr(o.novoStanje)} m³")
                        Text(o.statusTekst, style = MaterialTheme.typography.bodySmall,
                            color = if (o.status == "odbijeno") MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
}
