package hr.prijavavode.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import hr.prijavavode.GlavniViewModel

/** Nakon prve prijave privremenom lozinkom od ovlaštenog predstavnika suvlasnika. */
@Composable
fun EkranPromjeneLozinke(vm: GlavniViewModel) {
    var nova by rememberSaveable { mutableStateOf("") }
    var ponovljena by rememberSaveable { mutableStateOf("") }
    val prekratka = nova.isNotEmpty() && nova.length < 8
    val razlicite = ponovljena.isNotEmpty() && nova != ponovljena
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.Lock, null, Modifier.height(48.dp), tint = MaterialTheme.colorScheme.primary)
        Text("Nova lozinka", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Lozinku ste dobili od ovlaštenog predstavnika suvlasnika. Sada upišite svoju lozinku, " +
                "koju znate samo vi. Neka ima barem 8 znakova i neka ne bude samo od brojki.",
            style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
        )
        OutlinedTextField(
            value = nova, onValueChange = { nova = it }, label = { Text("Nova lozinka") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = PasswordVisualTransformation(),
            isError = prekratka,
            supportingText = { if (prekratka) Text("Barem 8 znakova.") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
        )
        OutlinedTextField(
            value = ponovljena, onValueChange = { ponovljena = it }, label = { Text("Ponovite novu lozinku") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = PasswordVisualTransformation(),
            isError = razlicite,
            supportingText = { if (razlicite) Text("Lozinke se ne podudaraju.") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { vm.promijeniLozinku(nova) },
            enabled = !vm.radi && nova.length >= 8 && nova == ponovljena,
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            if (vm.radi) CircularProgressIndicator(Modifier.height(24.dp)) else Text("Spremi lozinku")
        }
        TextButton(onClick = vm::odjava, modifier = Modifier.padding(top = 8.dp)) { Text("Odjava") }
    }
}
