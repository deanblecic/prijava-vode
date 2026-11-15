package hr.prijavavode.ui

import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation

/** Polje za lozinku s ikonom oka desno: dodir prikazuje ili skriva upisani tekst. */
@Composable
fun PoljeLozinke(
    vrijednost: String,
    promjena: (String) -> Unit,
    oznaka: String,
    imeAction: ImeAction,
    modifier: Modifier = Modifier,
    isError: Boolean = false,
    supportingText: (@Composable () -> Unit)? = null,
) {
    var vidljiva by rememberSaveable { mutableStateOf(false) }
    OutlinedTextField(
        value = vrijednost, onValueChange = promjena, label = { Text(oznaka) },
        singleLine = true, modifier = modifier,
        visualTransformation = if (vidljiva) VisualTransformation.None else PasswordVisualTransformation(),
        isError = isError,
        supportingText = supportingText,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = imeAction),
        trailingIcon = {
            IconButton(onClick = { vidljiva = !vidljiva }) {
                Icon(
                    if (vidljiva) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                    contentDescription = if (vidljiva) "Sakrij lozinku" else "Prikaži lozinku",
                )
            }
        },
    )
}
