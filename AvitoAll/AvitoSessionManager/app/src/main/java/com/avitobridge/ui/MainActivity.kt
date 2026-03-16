package com.avitobridge.ui

import android.Manifest
import android.content.*
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.avitobridge.App
import com.avitobridge.R
import com.avitobridge.data.AvitoSessionReader
import com.avitobridge.data.ServerApi
import com.avitobridge.data.SessionData
import com.avitobridge.databinding.ActivityMainBinding
import com.avitobridge.service.SessionMonitorService
import com.topjohnwu.superuser.Shell
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy { App.instance.prefs }
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    private val shortDateFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private val sessionReader = AvitoSessionReader()

    // Broadcast receiver for service updates
    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val status = intent.getStringExtra(SessionMonitorService.EXTRA_STATUS) ?: ""
            val message = intent.getStringExtra(SessionMonitorService.EXTRA_MESSAGE) ?: ""
            val expiresAt = intent.getLongExtra("expires_at", 0)

            updateSyncStatusUI(status, message)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupUI()
        checkPermissions()
        checkRootAccess()
        loadDeviceState()
        refreshServerStatus()
    }

    override fun onResume() {
        super.onResume()
        registerReceiver(
            statusReceiver,
            IntentFilter(SessionMonitorService.BROADCAST_STATUS_UPDATE),
            RECEIVER_NOT_EXPORTED
        )
        loadDeviceState()
        refreshServerStatus()
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(statusReceiver)
        } catch (e: Exception) {
            // Not registered
        }
    }

    private fun setupUI() {
        // Sync Now button
        binding.btnSyncNow.setOnClickListener {
            syncNow()
        }

        // Start/Stop Service button
        binding.btnToggleService.setOnClickListener {
            toggleService()
        }

        // Read Session button (for testing)
        binding.btnReadSession.setOnClickListener {
            readSessionNow()
        }

        // Settings button
        binding.btnSettings.setOnClickListener {
            showSettingsDialog()
        }

        // Copy Token button
        binding.btnCopyToken.setOnClickListener {
            copyTokenToClipboard()
        }

        // Refresh Server Status button
        binding.btnRefreshServerStatus.setOnClickListener {
            refreshServerStatus()
        }

        // Restart MCP button
        binding.btnRestartMcp.setOnClickListener {
            restartMcp()
        }

        // Auto-sync switch
        binding.switchAutoSync.isChecked = prefs.autoSyncEnabled
        binding.switchAutoSync.setOnCheckedChangeListener { _, isChecked ->
            prefs.autoSyncEnabled = isChecked
            if (isChecked) {
                startMonitorService()
            }
        }

        // Auto-launch switch
        binding.switchAutoLaunch.isChecked = prefs.autoLaunchAvito
        binding.switchAutoLaunch.setOnCheckedChangeListener { _, isChecked ->
            prefs.autoLaunchAvito = isChecked
            Toast.makeText(this, "Auto-launch: ${if (isChecked) "ON" else "OFF"}", Toast.LENGTH_SHORT).show()
        }

        // Notify on expiry switch
        binding.switchNotifyExpiry.isChecked = prefs.notifyOnExpiry
        binding.switchNotifyExpiry.setOnCheckedChangeListener { _, isChecked ->
            prefs.notifyOnExpiry = isChecked
            Toast.makeText(this, "Notifications: ${if (isChecked) "ON" else "OFF"}", Toast.LENGTH_SHORT).show()
        }

        // Load settings into UI
        binding.tvServerUrl.text = prefs.serverUrl
        binding.tvCheckInterval.text = "${prefs.checkIntervalMinutes} min"
        binding.tvSyncBefore.text = "${prefs.syncBeforeExpiryHours}h before expiry"
    }

    private fun checkPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    1001
                )
            }
        }
    }

    private fun checkRootAccess() {
        lifecycleScope.launch {
            val hasRoot = withContext(Dispatchers.IO) {
                Shell.getShell().isRoot
            }

            if (hasRoot) {
                binding.tvRootStatus.text = "OK"
            } else {
                binding.tvRootStatus.text = "NO ROOT"
                Toast.makeText(this@MainActivity, "Root access required!", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun loadDeviceState() {
        // Load cached session info
        val expiresAt = prefs.cachedExpiresAt
        if (expiresAt > 0) {
            val now = System.currentTimeMillis() / 1000
            val hoursLeft = (expiresAt - now) / 3600f

            binding.tvDeviceExpiresAt.text = dateFormat.format(Date(expiresAt * 1000))
            binding.tvDeviceTimeLeft.text = SessionData.formatHoursMinutes(hoursLeft)

            if (hoursLeft < 0) {
                binding.tvDeviceStatus.text = "EXPIRED"
            } else if (hoursLeft < prefs.syncBeforeExpiryHours) {
                binding.tvDeviceStatus.text = "EXPIRING"
            } else {
                binding.tvDeviceStatus.text = "OK"
            }
        } else {
            binding.tvDeviceStatus.text = "NO DATA"
        }

        // Last sync info
        binding.tvLastSync.text = prefs.lastSyncStatus

        // Token preview
        val token = prefs.cachedSessionToken
        if (token.isNotEmpty()) {
            binding.tvDeviceTokenPreview.text = "${token.take(50)}..."
        }

        val fp = prefs.cachedFingerprint
        if (fp.isNotEmpty()) {
            binding.tvDeviceFingerprintPreview.text = "${fp.take(50)}..."
        }
    }

    private fun refreshServerStatus() {
        binding.tvServerTokenStatus.text = "Loading..."
        binding.tvMcpStatus.text = "Loading..."

        lifecycleScope.launch {
            try {
                val api = ServerApi(prefs.serverUrl, prefs.serverApiKey)
                val result = api.getFullStatus()

                result.onSuccess { status ->
                    // Server token status
                    val session = status.session
                    if (session != null && session.exists) {
                        if (session.is_valid) {
                            binding.tvServerTokenStatus.text = "VALID"
                        } else {
                            binding.tvServerTokenStatus.text = "EXPIRED"
                        }
                        binding.tvServerExpiresIn.text = SessionData.formatHoursMinutes(session.hours_left)
                        if (session.updated_at > 0) {
                            binding.tvServerLastUpdate.text = shortDateFormat.format(Date(session.updated_at * 1000))
                        }
                    } else {
                        binding.tvServerTokenStatus.text = "NO SESSION"
                        binding.tvServerExpiresIn.text = "-"
                        binding.tvServerLastUpdate.text = "-"
                    }

                    // MCP status
                    val mcp = status.mcp
                    if (mcp != null) {
                        if (mcp.is_running) {
                            binding.tvMcpStatus.text = "RUNNING"
                        } else {
                            binding.tvMcpStatus.text = "STOPPED"
                        }
                    } else {
                        binding.tvMcpStatus.text = "UNKNOWN"
                    }
                }

                result.onFailure { e ->
                    binding.tvServerTokenStatus.text = "ERROR"
                    binding.tvMcpStatus.text = "ERROR"
                    Toast.makeText(this@MainActivity, "Server error: ${e.message}", Toast.LENGTH_SHORT).show()
                }

            } catch (e: Exception) {
                binding.tvServerTokenStatus.text = "OFFLINE"
                binding.tvMcpStatus.text = "OFFLINE"
            }
        }
    }

    private fun restartMcp() {
        AlertDialog.Builder(this)
            .setTitle("Restart MCP")
            .setMessage("Are you sure you want to restart the MCP bot?")
            .setPositiveButton("Restart") { _, _ ->
                doRestartMcp()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun doRestartMcp() {
        binding.tvMcpStatus.text = "Restarting..."
        binding.btnRestartMcp.isEnabled = false

        lifecycleScope.launch {
            try {
                val api = ServerApi(prefs.serverUrl, prefs.serverApiKey)
                val result = api.restartMcp()

                result.onSuccess { response ->
                    if (response.success) {
                        Toast.makeText(this@MainActivity, "MCP restarted!", Toast.LENGTH_SHORT).show()
                        binding.tvMcpStatus.text = "RESTARTED"
                        // Refresh status after a delay
                        kotlinx.coroutines.delay(2000)
                        refreshServerStatus()
                    } else {
                        Toast.makeText(this@MainActivity, "Failed: ${response.error}", Toast.LENGTH_SHORT).show()
                        binding.tvMcpStatus.text = "FAILED"
                    }
                }

                result.onFailure { e ->
                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    binding.tvMcpStatus.text = "ERROR"
                }

            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                binding.tvMcpStatus.text = "ERROR"
            } finally {
                binding.btnRestartMcp.isEnabled = true
            }
        }
    }

    private fun updateSyncStatusUI(status: String, message: String) {
        binding.tvStatus.text = status.uppercase()
        binding.tvLastMessage.text = message

        when (status.lowercase()) {
            "ok", "synced" -> binding.tvStatus.setTextColor(getColor(R.color.green))
            "checking", "syncing" -> binding.tvStatus.setTextColor(getColor(R.color.blue))
            "error", "expired", "failed" -> binding.tvStatus.setTextColor(getColor(R.color.red))
            else -> binding.tvStatus.setTextColor(getColor(R.color.gray))
        }
    }

    private fun syncNow() {
        Toast.makeText(this, "Syncing...", Toast.LENGTH_SHORT).show()
        binding.tvStatus.text = "SYNCING"
        binding.tvStatus.setTextColor(getColor(R.color.blue))

        val intent = Intent(this, SessionMonitorService::class.java).apply {
            action = SessionMonitorService.ACTION_SYNC_NOW
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun toggleService() {
        val intent = Intent(this, SessionMonitorService::class.java)

        // Toggle - if running stop, else start
        // For simplicity, we just start it
        intent.action = SessionMonitorService.ACTION_START

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }

        Toast.makeText(this, "Service started", Toast.LENGTH_SHORT).show()
    }

    private fun startMonitorService() {
        val intent = Intent(this, SessionMonitorService::class.java).apply {
            action = SessionMonitorService.ACTION_START
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun readSessionNow() {
        lifecycleScope.launch {
            binding.tvDeviceStatus.text = "READING..."

            val session = withContext(Dispatchers.IO) {
                sessionReader.readSession()
            }

            if (session != null) {
                // Update cache
                prefs.cachedSessionToken = session.sessionToken
                prefs.cachedFingerprint = session.fingerprint
                prefs.cachedExpiresAt = session.expiresAt

                // Update UI
                loadDeviceState()

                binding.tvDeviceStatus.text = "READ OK"

                Toast.makeText(
                    this@MainActivity,
                    "Session read! Expires in ${session.formatTimeLeft()}",
                    Toast.LENGTH_LONG
                ).show()
            } else {
                binding.tvDeviceStatus.text = "READ FAILED"
                Toast.makeText(this@MainActivity, "Failed to read session", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun copyTokenToClipboard() {
        val token = prefs.cachedSessionToken
        if (token.isEmpty()) {
            Toast.makeText(this, "No token cached", Toast.LENGTH_SHORT).show()
            return
        }

        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("Avito Session Token", token)
        clipboard.setPrimaryClip(clip)
        Toast.makeText(this, "Token copied!", Toast.LENGTH_SHORT).show()
    }

    private fun showSettingsDialog() {
        val view = layoutInflater.inflate(R.layout.dialog_settings, null)

        // Pre-fill with current values
        val etServerUrl = view.findViewById<android.widget.EditText>(R.id.etServerUrl)
        val etApiKey = view.findViewById<android.widget.EditText>(R.id.etApiKey)
        val etCheckInterval = view.findViewById<android.widget.EditText>(R.id.etCheckInterval)
        val etSyncBefore = view.findViewById<android.widget.EditText>(R.id.etSyncBefore)

        etServerUrl.setText(prefs.serverUrl)
        etApiKey.setText(prefs.serverApiKey)
        etCheckInterval.setText(prefs.checkIntervalMinutes.toString())
        etSyncBefore.setText(prefs.syncBeforeExpiryHours.toString())

        AlertDialog.Builder(this)
            .setTitle("Settings")
            .setView(view)
            .setPositiveButton("Save") { _, _ ->
                prefs.serverUrl = etServerUrl.text.toString()
                prefs.serverApiKey = etApiKey.text.toString()
                prefs.checkIntervalMinutes = etCheckInterval.text.toString().toIntOrNull() ?: 30
                prefs.syncBeforeExpiryHours = etSyncBefore.text.toString().toIntOrNull() ?: 2

                // Update UI
                binding.tvServerUrl.text = prefs.serverUrl
                binding.tvCheckInterval.text = "${prefs.checkIntervalMinutes} min"
                binding.tvSyncBefore.text = "${prefs.syncBeforeExpiryHours}h before expiry"

                Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
