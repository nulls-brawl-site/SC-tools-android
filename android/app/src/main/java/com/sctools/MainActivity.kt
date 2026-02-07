package com.sctools

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var statusText: TextView
    private lateinit var decodeButton: Button
    private lateinit var encodeButton: Button
    private lateinit var progressBar: ProgressBar

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
        progressBar = findViewById(R.id.progressBar)
        val topAppBar: MaterialToolbar = findViewById(R.id.topAppBar)
        topAppBar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_help -> {
                    showDialog(R.string.dialog_help_title, R.string.dialog_help_message)
                    true
                }
                R.id.action_about -> {
                    showDialog(R.string.dialog_about_title, R.string.dialog_about_message)
                    true
                }
                else -> false
            }
        }

        decodeButton.setOnClickListener {
            decodePicker.launch(arrayOf("*/*"))
        }

        encodeButton.setOnClickListener {
            encodePicker.launch(arrayOf("application/zip"))
        }
    }

    private fun handleFile(uri: Uri, isDecode: Boolean) {
        statusText.text = getString(R.string.status_preparing)
        setBusy(true)
        val inputFile = copyToCache(uri)
        if (inputFile == null) {
            statusText.text = getString(R.string.status_read_failed)
            setBusy(false)
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
                    statusText.text = getString(R.string.status_done, File(outputPath).name)
                    shareFile(File(outputPath))
                    setBusy(false)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = getString(R.string.status_error, e.message ?: "unknown")
                    setBusy(false)
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

    private fun setBusy(isBusy: Boolean) {
        decodeButton.isEnabled = !isBusy
        encodeButton.isEnabled = !isBusy
        progressBar.visibility = if (isBusy) View.VISIBLE else View.GONE
    }

    private fun showDialog(titleRes: Int, messageRes: Int) {
        MaterialAlertDialogBuilder(this)
            .setTitle(titleRes)
            .setMessage(messageRes)
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }
}
