package hr.prijavavode.ocr

import android.graphics.Bitmap
import android.graphics.Matrix
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await
import java.io.ByteArrayOutputStream
import java.math.BigDecimal

/** ML Kit prepoznavanje teksta na samom mobitelu; slika ne odlazi nikome osim našem serveru. */
object Prepoznavanje {
    private val prepoznavac by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    suspend fun procitaj(slika: Bitmap, prethodno: BigDecimal?): List<BigDecimal> {
        val izrez = izrezSredine(slika)
        val izIzreza = CitacBrojila.kandidati(linije(izrez), prethodno)
        if (izIzreza.isNotEmpty()) return izIzreza
        return CitacBrojila.kandidati(linije(slika), prethodno)
    }

    private suspend fun linije(slika: Bitmap): List<String> {
        val tekst = prepoznavac.process(InputImage.fromBitmap(slika, 0)).await()
        return tekst.textBlocks.flatMap { blok -> blok.lines.map { it.text } }
    }

    /** Okvir na zaslonu pokriva sredinu slike; izrez je malo veći da brojilo sigurno stane. */
    fun izrezSredine(slika: Bitmap): Bitmap {
        val sirina = (slika.width * 0.9f).toInt()
        val visina = minOf((sirina * 0.45f).toInt(), slika.height)
        val x = (slika.width - sirina) / 2
        val y = (slika.height - visina) / 2
        return Bitmap.createBitmap(slika, x, y, sirina, visina)
    }

    fun okreni(slika: Bitmap, stupnjevi: Int): Bitmap {
        if (stupnjevi == 0) return slika
        val matrica = Matrix().apply { postRotate(stupnjevi.toFloat()) }
        return Bitmap.createBitmap(slika, 0, 0, slika.width, slika.height, matrica, true)
    }

    /** Fotografija za server: najviše 1600 px po duljoj strani, JPEG. */
    fun zaSlanje(slika: Bitmap): ByteArray {
        val omjer = 1600f / maxOf(slika.width, slika.height)
        val manja = if (omjer < 1f) {
            Bitmap.createScaledBitmap(slika, (slika.width * omjer).toInt(), (slika.height * omjer).toInt(), true)
        } else slika
        return ByteArrayOutputStream().use { izlaz ->
            manja.compress(Bitmap.CompressFormat.JPEG, 85, izlaz)
            izlaz.toByteArray()
        }
    }
}
