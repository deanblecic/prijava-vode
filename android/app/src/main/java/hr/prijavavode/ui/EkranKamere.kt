package hr.prijavavode.ui

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import hr.prijavavode.ocr.Prepoznavanje
import hr.prijavavode.podaci.Vodomjer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun EkranKamere(
    vodomjer: Vodomjer,
    onSnimljeno: (Vodomjer, Bitmap, Boolean) -> Unit,
    onNatrag: () -> Unit,
) {
    val context = LocalContext.current
    var dozvola by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        )
    }
    val trazi = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { dozvola = it }
    LaunchedEffect(Unit) { if (!dozvola) trazi.launch(Manifest.permission.CAMERA) }

    // Fotografija vodomjera snimljena ranije; Android-ov birač slika ne traži dozvolu.
    val opseg = rememberCoroutineScope()
    var ucitava by remember { mutableStateOf(false) }
    var greskaGalerije by remember { mutableStateOf<String?>(null) }
    val galerija = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        ucitava = true
        opseg.launch {
            val slika = withContext(Dispatchers.IO) { runCatching { Prepoznavanje.izGalerije(context, uri) } }
            ucitava = false
            slika.onSuccess { onSnimljeno(vodomjer, it, true) }
                .onFailure { greskaGalerije = "Slika se ne može otvoriti. Odaberite drugu." }
        }
    }
    val otvoriGaleriju = {
        greskaGalerije = null
        galerija.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
    }

    if (!dozvola) {
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Za očitanje vodomjera aplikaciji treba pristup kameri.")
            Button(onClick = { trazi.launch(Manifest.permission.CAMERA) }, Modifier.padding(top = 16.dp)) {
                Text("Dopusti kameru")
            }
            Button(onClick = otvoriGaleriju, enabled = !ucitava, modifier = Modifier.padding(top = 8.dp)) {
                Text("Odaberi sliku iz galerije")
            }
            greskaGalerije?.let { Text(it, Modifier.padding(top = 8.dp)) }
            Button(onClick = onNatrag, Modifier.padding(top = 8.dp)) { Text("Natrag") }
        }
        return
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    val snimanje = remember {
        ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY).build()
    }
    var kamera by remember { mutableStateOf<Camera?>(null) }
    var svjetlo by remember { mutableStateOf(false) }
    var snima by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                val prikaz = PreviewView(ctx).apply { scaleType = PreviewView.ScaleType.FILL_CENTER }
                val buduci = ProcessCameraProvider.getInstance(ctx)
                buduci.addListener({
                    val pruzatelj = buduci.get()
                    val preview = Preview.Builder().build().also { it.setSurfaceProvider(prikaz.surfaceProvider) }
                    pruzatelj.unbindAll()
                    kamera = pruzatelj.bindToLifecycle(
                        lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, snimanje
                    )
                }, ContextCompat.getMainExecutor(ctx))
                prikaz
            },
        )
        DisposableEffect(Unit) {
            onDispose { runCatching { ProcessCameraProvider.getInstance(context).get().unbindAll() } }
        }

        // Okvir u koji korisnik smjesti brojilo; odgovara izrezu u Prepoznavanje.izrezSredine.
        Canvas(Modifier.fillMaxSize()) {
            val sirina = size.width * 0.92f
            val visina = sirina * 0.75f
            val vrh = Offset((size.width - sirina) / 2, (size.height - visina) / 2)
            drawRect(Color.Black.copy(alpha = 0.45f), size = Size(size.width, vrh.y))
            drawRect(Color.Black.copy(alpha = 0.45f), topLeft = Offset(0f, vrh.y + visina),
                size = Size(size.width, size.height - vrh.y - visina))
            drawRoundRect(Color.White, topLeft = vrh, size = Size(sirina, visina),
                cornerRadius = CornerRadius(24f), style = Stroke(width = 6f))
        }

        Row(
            Modifier.fillMaxWidth().safeDrawingPadding().padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onNatrag) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Natrag", tint = Color.White)
            }
            Text("Brojilo smjestite u okvir", color = Color.White, modifier = Modifier.weight(1f))
            IconButton(onClick = {
                svjetlo = !svjetlo
                kamera?.cameraControl?.enableTorch(svjetlo)
            }) {
                Icon(if (svjetlo) Icons.Filled.FlashOn else Icons.Filled.FlashOff, "Svjetlo", tint = Color.White)
            }
        }

        Column(
            Modifier.align(Alignment.BottomCenter).safeDrawingPadding().padding(bottom = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Prethodno stanje: ${hr(vodomjer.prethodnoStanje)} m³", color = Color.White,
                modifier = Modifier.padding(bottom = 16.dp))
            greskaGalerije?.let { Text(it, color = Color.White, modifier = Modifier.padding(bottom = 8.dp)) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Lijevo galerija, u sredini okidač; desno prazno mjesto iste širine radi simetrije.
                FilledIconButton(
                    onClick = otvoriGaleriju,
                    enabled = !snima && !ucitava,
                    modifier = Modifier.size(56.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.White.copy(alpha = 0.85f)),
                ) {
                    if (ucitava) CircularProgressIndicator(Modifier.size(24.dp))
                    else Icon(Icons.Filled.PhotoLibrary, "Odaberi sliku iz galerije", tint = Color.Black)
                }
                Box(Modifier.size(32.dp))
                FilledIconButton(
                    onClick = {
                        snima = true
                        snimanje.takePicture(ContextCompat.getMainExecutor(context),
                            object : ImageCapture.OnImageCapturedCallback() {
                                override fun onCaptureSuccess(slika: ImageProxy) {
                                    val bitmap = Prepoznavanje.okreni(slika.toBitmap(), slika.imageInfo.rotationDegrees)
                                    slika.close()
                                    kamera?.cameraControl?.enableTorch(false)
                                    onSnimljeno(vodomjer, bitmap, false)
                                }

                                override fun onError(greska: ImageCaptureException) {
                                    snima = false
                                }
                            })
                    },
                    enabled = !snima && !ucitava,
                    modifier = Modifier.size(76.dp),
                    colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.White),
                ) {
                    if (snima) CircularProgressIndicator() else Box(Modifier.size(60.dp))
                }
                Box(Modifier.size(88.dp))
            }
        }
    }
}
