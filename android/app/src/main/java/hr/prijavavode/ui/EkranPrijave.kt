package hr.prijavavode.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import hr.prijavavode.GlavniViewModel

@Composable
fun EkranPrijave(vm: GlavniViewModel) {
    val aktivnost = LocalContext.current as FragmentActivity
    val imaBiometriju = remember { Biometrija.dostupna(aktivnost) }
    var ime by rememberSaveable { mutableStateOf(vm.zapamcenoIme) }
    var lozinka by rememberSaveable { mutableStateOf(vm.zapamcenaLozinka) }
    var zapamti by rememberSaveable { mutableStateOf(vm.zapamceno) }
    var biometrija by rememberSaveable { mutableStateOf(vm.biometrijaUkljucena) }
    val otisak = { Biometrija.provjeri(aktivnost) { vm.biometrijaPotvrdena() } }
    LaunchedEffect(Unit) {
        if (vm.pitajBiometriju) {
            vm.pitajBiometriju = false
            otisak()
        }
    }
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.WaterDrop, null, Modifier.height(56.dp), tint = MaterialTheme.colorScheme.primary)
        Text("Očitanje vode", style = MaterialTheme.typography.headlineMedium)
        Text("Prijavite se podacima koje ste dobili od upravitelja zgrade.",
            style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 8.dp, bottom = 24.dp))
        OutlinedTextField(
            value = ime, onValueChange = { ime = it }, label = { Text("Korisničko ime") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = lozinka, onValueChange = { lozinka = it }, label = { Text("Lozinka") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
        )
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = zapamti, onCheckedChange = { zapamti = it })
            Text("Zapamti ime i lozinku")
        }
        if (imaBiometriju) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = zapamti && biometrija, onCheckedChange = { biometrija = it }, enabled = zapamti)
                Text("Prijava otiskom prsta ili licem")
            }
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.prijava(ime, lozinka, zapamti, biometrija) },
            enabled = !vm.radi && ime.isNotBlank() && lozinka.isNotEmpty(),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            if (vm.radi) CircularProgressIndicator(Modifier.height(24.dp)) else Text("Prijava")
        }
        if (imaBiometriju && vm.biometrijaUkljucena) {
            Spacer(Modifier.height(12.dp))
            OutlinedButton(
                onClick = otisak,
                enabled = !vm.radi,
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Icon(Icons.Filled.Fingerprint, null, Modifier.padding(end = 8.dp))
                Text("Otiskom prsta ili licem")
            }
        }
    }
}
