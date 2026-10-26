package hr.prijavavode.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import hr.prijavavode.Ekran
import hr.prijavavode.GlavniViewModel
import hr.prijavavode.ocr.Prepoznavanje
import java.math.BigDecimal

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EkranPotvrde(potvrda: Ekran.Potvrda, vm: GlavniViewModel) {
    val prethodno = potvrda.vodomjer.prethodnoStanje.toBigDecimalOrNull()
    var unos by remember(potvrda) { mutableStateOf(potvrda.kandidati.firstOrNull()?.toPlainString()?.let(::hr) ?: "") }
    val broj = unos.trim().replace(',', '.').toBigDecimalOrNull()
    val razlika = if (broj != null && prethodno != null) broj - prethodno else null
    val izrez = remember(potvrda) { Prepoznavanje.izrezSredine(potvrda.fotografija).asImageBitmap() }

    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = vm::natrag) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Natrag") }
            Text("Provjerite broj", style = MaterialTheme.typography.titleLarge)
        }
        Image(izrez, "Snimljeno brojilo", Modifier.fillMaxWidth().height(140.dp), contentScale = ContentScale.Fit)
        vm.poruka?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Text(
            if (potvrda.kandidati.isEmpty()) "Upišite stanje sa slike."
            else "Usporedite broj sa slikom. Ako nije točan, ispravite ga.",
        )
        OutlinedTextField(
            value = unos,
            onValueChange = { novi -> unos = novi.filter { it.isDigit() || it == ',' || it == '.' } },
            label = { Text("Novo stanje (m³)") },
            singleLine = true,
            textStyle = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.SemiBold, fontSize = 30.sp),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        if (potvrda.kandidati.size > 1) {
            Text("Drugi mogući brojevi:", style = MaterialTheme.typography.bodySmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                potvrda.kandidati.drop(1).take(4).forEach { k ->
                    SuggestionChip(onClick = { unos = hr(k.toPlainString()) }, label = { Text(hr(k.toPlainString())) })
                }
            }
        }
        Text("Prethodno stanje: ${hr(potvrda.vodomjer.prethodnoStanje)} m³")
        if (razlika != null) {
            Text(
                "Potrošnja: ${hr(razlika.toPlainString())} m³",
                style = MaterialTheme.typography.titleLarge,
                color = if (razlika.signum() < 0) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
            )
            if (razlika.signum() < 0) {
                Text("Novo stanje je manje od prethodnog. Provjerite jeste li dobro upisali broj.",
                    color = MaterialTheme.colorScheme.error)
            }
        }
        Button(
            onClick = { broj?.let { vm.posalji(potvrda, it) } },
            enabled = broj != null && !vm.radi,
            modifier = Modifier.fillMaxWidth().height(56.dp),
        ) {
            if (vm.radi) CircularProgressIndicator(Modifier.height(24.dp)) else Text("Pošalji očitanje")
        }
        OutlinedButton(
            onClick = { vm.poruka = null; vm.otvoriKameru(potvrda.vodomjer) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Snimi ponovno") }
    }

    vm.trazPotvrduManjeg?.let { tekst ->
        AlertDialog(
            onDismissRequest = vm::odustaniOdManjeg,
            title = { Text("Jeste li sigurni?") },
            text = { Text("$tekst\n\nAko je broj točan (npr. vodomjer je zamijenjen), pošaljite ga i upravitelj će ga provjeriti.") },
            confirmButton = {
                TextButton(onClick = { broj?.let { vm.posalji(potvrda, it, potvrdiManje = true) } }) {
                    Text("Pošalji svejedno")
                }
            },
            dismissButton = { TextButton(onClick = vm::odustaniOdManjeg) { Text("Ispravit ću broj") } },
        )
    }
}
