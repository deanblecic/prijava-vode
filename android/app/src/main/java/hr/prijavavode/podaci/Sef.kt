package hr.prijavavode.podaci

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Zapamćeno korisničko ime i lozinka; lozinka je šifrirana ključem iz Android Keystorea. */
class Sef(context: Context) {
    private val postavke = context.getSharedPreferences("sef", Context.MODE_PRIVATE)

    val ime: String?
        get() = postavke.getString("ime", null)

    val lozinka: String?
        get() = postavke.getString("lozinka", null)?.let(::desifriraj)

    val zapamceno: Boolean
        get() = ime != null && lozinka != null

    /** Prijava otiskom prsta ili licem; ima smisla samo uz zapamćenu lozinku. */
    var biometrija: Boolean
        get() = postavke.getBoolean("biometrija", false) && zapamceno
        set(vrijednost) = postavke.edit().putBoolean("biometrija", vrijednost).apply()

    fun zapamti(ime: String, lozinka: String) {
        postavke.edit().putString("ime", ime).putString("lozinka", sifriraj(lozinka)).apply()
    }

    fun zaboravi() = postavke.edit().clear().apply()

    private fun kljuc(): SecretKey {
        val spremiste = KeyStore.getInstance(SPREMISTE).apply { load(null) }
        (spremiste.getKey(ALIAS, null) as SecretKey?)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, SPREMISTE)
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    private fun sifriraj(tekst: String): String {
        val sifra = Cipher.getInstance(ALGORITAM).apply { init(Cipher.ENCRYPT_MODE, kljuc()) }
        return Base64.encodeToString(sifra.iv + sifra.doFinal(tekst.toByteArray()), Base64.NO_WRAP)
    }

    /** Null ako se ne da dešifrirati (npr. ključ je obrisan), pa korisnik upiše lozinku ponovno. */
    private fun desifriraj(zapis: String): String? = runCatching {
        val bajtovi = Base64.decode(zapis, Base64.NO_WRAP)
        val sifra = Cipher.getInstance(ALGORITAM)
        sifra.init(Cipher.DECRYPT_MODE, kljuc(), GCMParameterSpec(128, bajtovi, 0, IV))
        String(sifra.doFinal(bajtovi, IV, bajtovi.size - IV))
    }.getOrNull()

    private companion object {
        const val SPREMISTE = "AndroidKeyStore"
        const val ALIAS = "prijava-vode-sef"
        const val ALGORITAM = "AES/GCM/NoPadding"
        const val IV = 12
    }
}
