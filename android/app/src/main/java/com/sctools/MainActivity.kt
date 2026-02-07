package com.sctools

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var statusText: TextView
    private lateinit var decodeButton: Button
    private lateinit var encodeButton: Button

    private val decodePicker = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri?.let { handleFile(it, isDecode = true) }
    }

    private val encodePicker = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri?.let { handleFile(it, isDecode = false) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        decodeButton = findViewById(R.id.decodeButton)
        encodeButton = findViewById(R.id.encodeButton)

        decodeButton.setOnClickListener {
            decodePicker.launch(arrayOf("*/*"))
        }

        encodeButton.setOnClickListener {
            encodePicker.launch(arrayOf("application/zip"))
        }
    }

    private fun handleFile(uri: Uri, isDecode: Boolean) {
        statusText.text = "Подготовка файла..."
        val inputFile = copyToCache(uri)
        if (inputFile == null) {
            statusText.text = "Не удалось прочитать файл"
            return
        }

        Thread {
            try {
                val python = Python.getInstance()
                val module = python.getModule("bridge")
                val result: PyObject = if (isDecode) {
                    module.callAttr("decode_file", inputFile.absolutePath, inputFile.name)
                } else {
                    module.callAttr("encode_file", inputFile.absolutePath)
                }

                val outputPath = result.toString()
                runOnUiThread {
                    statusText.text = "Готово: ${File(outputPath).name}"
                    shareFile(File(outputPath))
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Ошибка: ${e.message}"
                }
            }
        }.start()
    }

    private fun copyToCache(uri: Uri): File? {
        return try {
            val name = queryName(uri) ?: "input"
            val target = File(cacheDir, name)
            contentResolver.openInputStream(uri)?.use { input ->
                target.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
            target
        } catch (_: Exception) {
            null
        }
    }

    private fun queryName(uri: Uri): String? {
        contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
            if (cursor.moveToFirst() && nameIndex != -1) {
                return cursor.getString(nameIndex)
            }
        }
        return null
    }

    private fun shareFile(file: File) {
        if (!file.exists()) return
        val uri = FileProvider.getUriForFile(this, "${BuildConfig.APPLICATION_ID}.fileprovider", file)
        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = "application/octet-stream"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(shareIntent, "Поделиться файлом"))
    }
}
