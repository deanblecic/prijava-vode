package hr.prijavavode

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import hr.prijavavode.ui.EkranKamere
import hr.prijavavode.ui.EkranPocetna
import hr.prijavavode.ui.EkranPotvrde
import hr.prijavavode.ui.EkranPovijesti
import hr.prijavavode.ui.EkranPrijave
import hr.prijavavode.ui.EkranPromjeneLozinke

// FragmentActivity jer ga traži BiometricPrompt.
class MainActivity : FragmentActivity() {
    private val vm: GlavniViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Color(0xFF1F6FEB))) {
                Aplikacija(vm)
            }
        }
    }
}

@Composable
private fun Aplikacija(vm: GlavniViewModel) {
    val ekran = vm.ekran
    BackHandler(enabled = ekran is Ekran.Kamera || ekran is Ekran.Potvrda || ekran is Ekran.Povijest) {
        vm.natrag()
    }
    if (ekran == Ekran.Pocetna && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        val context = LocalContext.current
        val trazi = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
        LaunchedEffect(Unit) {
            val dopusteno = ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
            if (!dopusteno && vm.trebaTrazitiObavijesti()) trazi.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    when (ekran) {
        Ekran.Ucitavanje -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        Ekran.Prijava -> EkranPrijave(vm)
        Ekran.Pocetna -> EkranPocetna(vm)
        is Ekran.Kamera -> EkranKamere(ekran.vodomjer, onSnimljeno = vm::snimljeno, onNatrag = vm::natrag)
        is Ekran.Potvrda -> EkranPotvrde(ekran, vm)
        Ekran.Povijest -> EkranPovijesti(vm)
        Ekran.PromjenaLozinke -> EkranPromjeneLozinke(vm)
    }
    vm.greska?.let { tekst ->
        AlertDialog(
            onDismissRequest = { vm.greska = null },
            confirmButton = { TextButton(onClick = { vm.greska = null }) { Text("U redu") } },
            title = { Text("Greška") },
            text = { Text(tekst) },
        )
    }
}
