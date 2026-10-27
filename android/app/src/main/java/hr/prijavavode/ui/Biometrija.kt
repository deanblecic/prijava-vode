package hr.prijavavode.ui

import android.content.Context
import android.os.Build
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/** Otisak prsta ili lice, samo ako je na mobitelu postavljeno (Android 9 i noviji). */
object Biometrija {
    private const val VRSTA = BiometricManager.Authenticators.BIOMETRIC_WEAK

    fun dostupna(context: Context): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
            BiometricManager.from(context).canAuthenticate(VRSTA) == BiometricManager.BIOMETRIC_SUCCESS

    fun provjeri(aktivnost: FragmentActivity, onUspjeh: () -> Unit) {
        val upit = BiometricPrompt(
            aktivnost,
            ContextCompat.getMainExecutor(aktivnost),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(rezultat: BiometricPrompt.AuthenticationResult) = onUspjeh()
            },
        )
        upit.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Prijava u Očitanje vode")
                .setSubtitle("Potvrdite otiskom prsta ili licem")
                .setNegativeButtonText("Upiši lozinku")
                .setAllowedAuthenticators(VRSTA)
                .build()
        )
    }
}
