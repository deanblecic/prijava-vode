package hr.prijavavode.ocr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.ImageDecoder
import android.graphics.Matrix
import android.graphics.Paint
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

    /**
     * Cijeli broj m³ s fotografije. Jedno čitanje često promaši brojilo (odsjaj, mutno, nakošeno),
     * pa se čita šest inačica slike i glasa: cijela slika, dva izreza sredine, izrez s pojačanim
     * kontrastom i izrez zakrenut za ±10°. Na 20 testnih fotografija to daje točan broj na 11
     * umjesto 9 (vidi test/resources/vodomjeri/README.md).
     */
    suspend fun procitaj(slika: Bitmap, prethodno: BigDecimal?, izrezi: Boolean = true): List<BigDecimal> {
        val citanja = inacice(slika, izrezi).map { linije(it) }
        return CitacBrojila.glasaj(citanja, prethodno)
    }

    private fun inacice(slika: Bitmap, izrezi: Boolean): List<Bitmap> {
        // Kamera: brojilo je u okviru na sredini. Galerija: fotografija nije nužno poravnata s okvirom.
        val cijela = if (izrezi) izrezSredine(slika) else slika
        val izrez80 = povecaj(izrez(cijela, 0.8f))
        val izrez60 = povecaj(izrez(cijela, 0.6f))
        return listOf(
            cijela,
            izrez80,
            izrez60,
            kontrast(izrez80),
            okreni(izrez80, -10),
            okreni(izrez80, 10),
        )
    }

    private fun izrez(slika: Bitmap, udio: Float): Bitmap {
        val sirina = (slika.width * udio).toInt()
        val visina = (slika.height * udio).toInt()
        return Bitmap.createBitmap(slika, (slika.width - sirina) / 2, (slika.height - visina) / 2, sirina, visina)
    }

    /** Mali izrez se poveća na 1600 px po duljoj strani da znamenke budu dovoljno velike. */
    private fun povecaj(slika: Bitmap): Bitmap {
        val omjer = 1600f / maxOf(slika.width, slika.height)
        if (omjer <= 1f) return slika
        return Bitmap.createScaledBitmap(slika, (slika.width * omjer).toInt(), (slika.height * omjer).toInt(), true)
    }

    /** Sivo s pojačanim kontrastom: pomaže kod tamnih i mutnih fotografija. */
    private fun kontrast(slika: Bitmap): Bitmap {
        val matrica = ColorMatrix().apply {
            setSaturation(0f)
            postConcat(ColorMatrix(floatArrayOf(
                1.6f, 0f, 0f, 0f, -77f,
                0f, 1.6f, 0f, 0f, -77f,
                0f, 0f, 1.6f, 0f, -77f,
                0f, 0f, 0f, 1f, 0f,
            )))
        }
        val rezultat = Bitmap.createBitmap(slika.width, slika.height, Bitmap.Config.ARGB_8888)
        Canvas(rezultat).drawBitmap(slika, 0f, 0f, Paint().apply { colorFilter = ColorMatrixColorFilter(matrica) })
        return rezultat
    }

    private suspend fun linije(slika: Bitmap): List<String> {
        val tekst = prepoznavac.process(InputImage.fromBitmap(slika, 0)).await()
        return tekst.textBlocks.flatMap { blok -> blok.lines.map { it.text } }
    }

    /** Okvir na zaslonu pokriva sredinu slike; izrez je malo veći da brojilo sigurno stane. */
    fun izrezSredine(slika: Bitmap): Bitmap {
        val sirina = (slika.width * 0.96f).toInt()
        val visina = minOf((sirina * 0.8f).toInt(), slika.height)
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
