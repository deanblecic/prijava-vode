package hr.prijavavode.ocr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await
import java.io.ByteArrayOutputStream
import java.math.BigDecimal

/** ML Kit prepoznavanje teksta na samom mobitelu; slika ne odlazi nikome osim našem serveru. */
object Prepoznavanje {
    private val prepoznavac by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

    suspend fun procitaj(slika: Bitmap, prethodno: BigDecimal?, izrezi: Boolean = true): List<BigDecimal> {
        if (!izrezi) return CitacBrojila.kandidati(linije(slika), prethodno)
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

    /** Fotografija iz galerije, uspravna i najviše 3000 px po duljoj strani. */
    fun izGalerije(context: Context, uri: Uri): Bitmap {
        val najvise = 3000
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val izvor = ImageDecoder.createSource(context.contentResolver, uri)
            return ImageDecoder.decodeBitmap(izvor) { dekoder, info, _ ->
                // Softverska slika: ML Kit i izrezivanje trebaju pristup pikselima.
                dekoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                val dulja = maxOf(info.size.width, info.size.height)
                if (dulja > najvise) {
                    val omjer = najvise.toFloat() / dulja
                    dekoder.setTargetSize((info.size.width * omjer).toInt(), (info.size.height * omjer).toInt())
                }
            }
        }
        val granice = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri).use { BitmapFactory.decodeStream(it, null, granice) }
        var korak = 1
        while (maxOf(granice.outWidth, granice.outHeight) / korak > najvise) korak *= 2
        val opcije = BitmapFactory.Options().apply { inSampleSize = korak }
        return context.contentResolver.openInputStream(uri).use { BitmapFactory.decodeStream(it, null, opcije) }
            ?: error("Slika se ne može otvoriti")
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
