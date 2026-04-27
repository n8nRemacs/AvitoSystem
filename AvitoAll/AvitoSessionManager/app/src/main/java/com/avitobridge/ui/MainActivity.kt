package com.avitobridge.ui

import android.Manifest
import android.content.*
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.avitobridge.App
import com.avitobridge.R
import com.avitobridge.data.AvitoSessionReader
import com.avitobridge.data.McpApi
import com.avitobridge.data.McpHealth
import com.avitobridge.data.ServerApi
import com.avitobridge.data.ServerSessionInfo
import com.avitobridge.data.SessionData
import com.avitobridge.databinding.ActivityMainBinding
import com.avitobridge.service.SessionMonitorService
import com.topjohnwu.superuser.Shell
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
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

    // In-memory ring buffer for last action log
    private val actionLog: ArrayDeque<String> = ArrayDeque()
    private val ACTION_LOG_MAX = 5

    // Last refresh state (used to compute Stack Health badge)
    private var lastRootOk: Boolean = false
    private var lastServerReachable: Boolean = false
    private var lastSyncOk: Boolean? = null
    private var lastSyncEpoch: Long = 0
    private var lastServerSession: ServerSessionInfo? = null
    private var lastMcpReachable: Boolean = false
    private var mcpEverChecked: Boolean = false

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
        refreshMcpStatus()
        refreshNotificationListenerStatus()
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
        refreshMcpStatus()
        refreshNotificationListenerStatus()
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

        // avito-mcp buttons
        binding.btnMcpRefresh.setOnClickListener { refreshMcpStatus() }
        binding.btnMcpRestart.setOnClickListener { confirmAndRestartMcp() }
        binding.tvMcpUrl.text = prefs.mcpUrl

        // V2.1 Notification Listener card wiring
        binding.btnNotifRefresh.setOnClickListener { refreshNotificationListenerStatus() }
        binding.btnNotifGrant.setOnClickListener {
            try {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            } catch (e: Exception) {
                Toast.makeText(
                    this,
                    "Не удалось открыть настройки уведомлений",
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
        binding.switchNotifEnabled.isChecked = prefs.notificationListenerEnabled
        binding.switchNotifEnabled.setOnCheckedChangeListener { _, isChecked ->
            prefs.notificationListenerEnabled = isChecked
            refreshNotificationListenerStatus()
        }

        // Show configured server URL inside the server card
        binding.tvServerUrl2.text = prefs.serverUrl

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

            lastRootOk = hasRoot
            if (hasRoot) {
                binding.tvRootStatus.text = "OK"
            } else {
                binding.tvRootStatus.text = "NO ROOT"
                Toast.makeText(this@MainActivity, "Root access required!", Toast.LENGTH_LONG).show()
            }
            updateStackHealth()
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
        binding.tvServerUrl2.text = prefs.serverUrl
        binding.tvServerReachable.text = "..."
        binding.tvServerTokenStatus.text = "Loading..."
        binding.tvServerExpiresIn.text = "-"
        binding.tvServerLastUpdate.text = "-"
        binding.tvServerSource.text = "-"
        binding.tvServerUserId.text = "-"
        binding.tvServerCreatedAt.text = "-"
        binding.tvUnreadCount.text = "..."
        binding.tvServerLastSync.text = prefs.lastSyncStatus

        val started = System.currentTimeMillis()

        lifecycleScope.launch {
            val api = ServerApi(prefs.serverUrl, prefs.serverApiKey)

            val healthDeferred = async { api.healthCheck() }
            val sessionDeferred = async { api.getServerSession() }
            val unreadDeferred = async { api.getUnreadCount() }

            val reachable = healthDeferred.await()
            val sessionResult = sessionDeferred.await()
            val unreadResult = unreadDeferred.await()

            val elapsed = System.currentTimeMillis() - started
            lastServerReachable = reachable

            // Reachability dot
            if (reachable) {
                binding.tvServerReachable.text = "ONLINE"
                binding.tvServerReachable.setTextColor(getColor(R.color.green))
                binding.viewServerDot.setBackgroundColor(getColor(R.color.green))
            } else {
                binding.tvServerReachable.text = "OFFLINE"
                binding.tvServerReachable.setTextColor(getColor(R.color.red))
                binding.viewServerDot.setBackgroundColor(getColor(R.color.red))
            }

            // Server-stored session
            sessionResult.onSuccess { info ->
                lastServerSession = info
                if (info.is_active) {
                    binding.tvServerTokenStatus.text = "ACTIVE"
                    binding.tvServerTokenStatus.setTextColor(getColor(R.color.green))
                } else {
                    binding.tvServerTokenStatus.text = "NO SESSION"
                    binding.tvServerTokenStatus.setTextColor(getColor(R.color.red))
                }
                binding.tvServerExpiresIn.text = info.ttl_human ?: "-"
                binding.tvServerLastUpdate.text = info.expires_at ?: "-"
                binding.tvServerSource.text = info.source ?: "-"
                binding.tvServerUserId.text = info.user_id?.toString() ?: "-"
                binding.tvServerCreatedAt.text = info.created_at ?: "-"
            }
            sessionResult.onFailure { e ->
                lastServerSession = null
                binding.tvServerTokenStatus.text = if (reachable) "ERROR" else "OFFLINE"
                binding.tvServerTokenStatus.setTextColor(getColor(R.color.red))
                Log.w("MainActivity", "sessions/current failed: ${e.message}")
            }

            // Unread count
            unreadResult.onSuccess { count ->
                binding.tvUnreadCount.text = count.toString()
                binding.tvUnreadCount.setTextColor(getColor(R.color.green))
            }
            unreadResult.onFailure { e ->
                binding.tvUnreadCount.text = "-"
                binding.tvUnreadCount.setTextColor(getColor(R.color.gray))
                Log.w("MainActivity", "unread-count failed: ${e.message}")
            }

            val outcome = when {
                !reachable -> "offline"
                sessionResult.isSuccess -> "ok"
                else -> "error"
            }
            appendActionLog("refresh_status", outcome, elapsed)
            updateStackHealth()
        }
    }

    /**
     * Compute green/yellow/red badge based on full stack state.
     */
    private fun updateStackHealth() {
        val now = System.currentTimeMillis() / 1000
        val expiresAt = prefs.cachedExpiresAt
        val ttlHours = if (expiresAt > 0) (expiresAt - now) / 3600f else -1f
        val syncAgeMin = if (lastSyncEpoch > 0) (now - lastSyncEpoch) / 60 else Long.MAX_VALUE

        val problems = mutableListOf<String>()
        if (!lastRootOk) problems += "no-root"
        if (expiresAt <= 0) problems += "no-local-session"
        else if (ttlHours < 0) problems += "local-expired"
        if (!lastServerReachable) problems += "server-offline"
        if (lastSyncOk == false) problems += "sync-failed"

        val warnings = mutableListOf<String>()
        if (ttlHours in 0f..4f) warnings += "ttl<4h"
        if (lastSyncEpoch > 0 && syncAgeMin > 60) warnings += "stale-sync"
        if (lastServerSession?.is_active == false && lastServerReachable) warnings += "no-server-session"
        if (mcpEverChecked && !lastMcpReachable) warnings += "mcp-offline"

        when {
            problems.isNotEmpty() -> {
                binding.tvStackHealthBadge.text = "STACK: PROBLEM (${problems.joinToString(", ")})"
                binding.tvStackHealthBadge.setBackgroundColor(getColor(R.color.red))
            }
            warnings.isNotEmpty() -> {
                binding.tvStackHealthBadge.text = "STACK: WARN (${warnings.joinToString(", ")})"
                binding.tvStackHealthBadge.setBackgroundColor(getColor(R.color.orange))
            }
            else -> {
                binding.tvStackHealthBadge.text = "STACK: OK"
                binding.tvStackHealthBadge.setBackgroundColor(getColor(R.color.green))
            }
        }
    }

    private fun appendActionLog(action: String, outcome: String, latencyMs: Long, extra: String = "") {
        val ts = shortDateFormat.format(Date())
        val tail = if (extra.isNotEmpty()) " $extra" else ""
        val line = "$ts $action -> $outcome ${latencyMs}ms$tail"
        actionLog.addFirst(line)
        while (actionLog.size > ACTION_LOG_MAX) actionLog.removeLast()
        binding.tvActionLog.text = actionLog.joinToString("\n")
    }

    /**
     * Free-form log line (used by MCP card where we already have a composed message).
     */
    private fun appendActionLog(message: String) {
        val ts = shortDateFormat.format(Date())
        actionLog.addFirst("$ts $message")
        while (actionLog.size > ACTION_LOG_MAX) actionLog.removeLast()
        binding.tvActionLog.text = actionLog.joinToString("\n")
    }

    private fun refreshMcpStatus() {
        binding.tvMcpUrl.text = prefs.mcpUrl
        binding.tvMcpReachable.text = "Checking..."
        binding.tvMcpReachable.setTextColor(getColor(R.color.gray))

        val started = System.currentTimeMillis()
        lifecycleScope.launch {
            val api = McpApi(prefs.mcpUrl, prefs.mcpAuthToken)
            val res = api.healthCheck()
            val latency = System.currentTimeMillis() - started
            mcpEverChecked = true

            res.onSuccess { h ->
                lastMcpReachable = true
                binding.viewMcpDot.setBackgroundResource(R.drawable.dot_green)
                binding.tvMcpReachable.text = "ONLINE"
                binding.tvMcpReachable.setTextColor(getColor(R.color.green))
                binding.tvMcpVersion.text = if (h.version.isNotBlank()) h.version else "-"
                binding.tvMcpUptime.text = formatUptime(h.uptime_sec)
                binding.tvMcpTools.text = "${h.tools_registered} registered"
                binding.tvMcpStartedAt.text = if (h.started_at.isNotBlank()) h.started_at else "-"
                binding.tvMcpLastCheck.text = "OK ${latency}ms at ${shortDateFormat.format(Date())}"
                appendActionLog("mcp_health -> ok ${latency}ms")
            }
            res.onFailure { e ->
                lastMcpReachable = false
                binding.viewMcpDot.setBackgroundResource(R.drawable.dot_red)
                binding.tvMcpReachable.text = "OFFLINE"
                binding.tvMcpReachable.setTextColor(getColor(R.color.red))
                val msg = e.message?.take(60) ?: "unknown"
                binding.tvMcpLastCheck.text = "FAIL: $msg"
                appendActionLog("mcp_health -> err ${e.message?.take(40) ?: "?"}")
            }
            updateStackHealth()
        }
    }

    private fun refreshNotificationListenerStatus() {
        val granted = NotificationManagerCompat
            .getEnabledListenerPackages(this)
            .contains(packageName)
        val forwardEnabled = prefs.notificationListenerEnabled

        binding.tvNotifAccess.text = when {
            !granted -> "NOT GRANTED"
            !forwardEnabled -> "GRANTED (forward off)"
            else -> "GRANTED"
        }
        binding.tvNotifAccess.setTextColor(
            getColor(if (granted && forwardEnabled) R.color.green else R.color.red)
        )
        binding.viewNotifDot.setBackgroundResource(
            when {
                !granted -> R.drawable.dot_red
                !forwardEnabled -> R.drawable.dot_gray
                else -> R.drawable.dot_green
            }
        )
        binding.btnNotifGrant.text = if (granted) "Open settings" else "Grant access"

        binding.tvNotifTotal.text = prefs.notificationsForwardedTotal.toString()

        val lastAt = prefs.notificationsLastForwardedAt
        binding.tvNotifLastAt.text = if (lastAt > 0) {
            shortDateFormat.format(Date(lastAt))
        } else {
            "never"
        }

        val lastStatus = prefs.notificationsLastStatus
        binding.tvNotifLastStatus.text = lastStatus.ifEmpty { "-" }
    }

    private fun confirmAndRestartMcp() {
        AlertDialog.Builder(this)
            .setTitle("Restart avito-mcp")
            .setMessage("Дёрнем POST /restart на ${prefs.mcpUrl}? Сервис уйдёт в ребут на ~5-10 сек.")
            .setPositiveButton("Restart") { _, _ -> doRestartMcp() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun doRestartMcp() {
        binding.btnMcpRestart.isEnabled = false
        binding.tvMcpLastCheck.text = "Restarting..."
        binding.tvMcpReachable.text = "RESTARTING"
        binding.tvMcpReachable.setTextColor(getColor(R.color.blue))
        binding.viewMcpDot.setBackgroundResource(R.drawable.dot_gray)

        lifecycleScope.launch {
            val api = McpApi(prefs.mcpUrl, prefs.mcpAuthToken)
            val r = api.restart()

            r.onSuccess {
                appendActionLog("mcp_restart -> sent")
                Toast.makeText(this@MainActivity, "Restart sent. Waiting…", Toast.LENGTH_SHORT).show()
                // Poll healthz every 1s for up to 15s
                var ok = false
                for (i in 1..15) {
                    delay(1000)
                    val h = api.healthCheck()
                    if (h.isSuccess) { ok = true; break }
                }
                if (ok) {
                    Toast.makeText(this@MainActivity, "Restart OK ✓", Toast.LENGTH_SHORT).show()
                    appendActionLog("mcp_restart -> respawn ok")
                } else {
                    Toast.makeText(this@MainActivity, "Restart sent but service not back in 15s", Toast.LENGTH_LONG).show()
                    appendActionLog("mcp_restart -> respawn TIMEOUT")
                }
                refreshMcpStatus()
            }
            r.onFailure { e ->
                Toast.makeText(this@MainActivity, "Restart failed: ${e.message}", Toast.LENGTH_LONG).show()
                appendActionLog("mcp_restart -> err ${e.message?.take(40) ?: "?"}")
                refreshMcpStatus()
            }
            binding.btnMcpRestart.isEnabled = true
        }
    }

    private fun formatUptime(sec: Int): String {
        if (sec <= 0) return "0s"
        val h = sec / 3600
        val m = (sec % 3600) / 60
        val s = sec % 60
        return when {
            h > 0 -> "${h}h ${m}m"
            m > 0 -> "${m}m ${s}s"
            else -> "${s}s"
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

        // Run our own sync so we can measure latency + log + then refresh server panel.
        val started = System.currentTimeMillis()
        lifecycleScope.launch {
            val session = withContext(Dispatchers.IO) { sessionReader.readSession() }
            if (session == null) {
                lastSyncOk = false
                lastSyncEpoch = System.currentTimeMillis() / 1000
                prefs.lastSyncStatus = "Local read failed @ ${shortDateFormat.format(Date())}"
                binding.tvLastSync.text = prefs.lastSyncStatus
                binding.tvServerLastSync.text = prefs.lastSyncStatus
                appendActionLog("sync_now", "no_session", System.currentTimeMillis() - started)
                updateStackHealth()
                Toast.makeText(this@MainActivity, "No local session to sync", Toast.LENGTH_SHORT).show()
                return@launch
            }

            // Cache locally so loadDeviceState() reflects the freshest read.
            prefs.cachedSessionToken = session.sessionToken
            prefs.cachedFingerprint = session.fingerprint
            prefs.cachedExpiresAt = session.expiresAt

            val api = ServerApi(prefs.serverUrl, prefs.serverApiKey)
            val result = api.syncSession(session)
            val elapsed = System.currentTimeMillis() - started

            result.onSuccess { resp ->
                lastSyncOk = true
                lastSyncEpoch = System.currentTimeMillis() / 1000
                prefs.lastSyncTime = lastSyncEpoch
                prefs.lastSyncStatus = "OK ${elapsed}ms @ ${shortDateFormat.format(Date())}"
                binding.tvStatus.text = "OK"
                binding.tvStatus.setTextColor(getColor(R.color.green))
                binding.tvLastSync.text = prefs.lastSyncStatus
                binding.tvServerLastSync.text = prefs.lastSyncStatus
                binding.tvLastMessage.text = resp.message ?: "synced"
                appendActionLog("sync_now", "ok", elapsed)
                Toast.makeText(this@MainActivity, "Synced", Toast.LENGTH_SHORT).show()
                refreshServerStatus()
                loadDeviceState()
            }
            result.onFailure { e ->
                lastSyncOk = false
                lastSyncEpoch = System.currentTimeMillis() / 1000
                prefs.lastSyncStatus = "FAIL ${elapsed}ms @ ${shortDateFormat.format(Date())}"
                binding.tvStatus.text = "FAILED"
                binding.tvStatus.setTextColor(getColor(R.color.red))
                binding.tvLastSync.text = prefs.lastSyncStatus
                binding.tvServerLastSync.text = prefs.lastSyncStatus
                binding.tvLastMessage.text = e.message ?: "error"
                appendActionLog("sync_now", "fail", elapsed)
                Log.w("MainActivity", "syncNow failed: ${e.message}")
                Toast.makeText(this@MainActivity, "Sync failed: ${e.message}", Toast.LENGTH_SHORT).show()
                updateStackHealth()
            }
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
        val started = System.currentTimeMillis()
        lifecycleScope.launch {
            binding.tvDeviceStatus.text = "READING..."

            val session = withContext(Dispatchers.IO) {
                sessionReader.readSession()
            }

            val elapsed = System.currentTimeMillis() - started
            if (session != null) {
                // Update cache
                prefs.cachedSessionToken = session.sessionToken
                prefs.cachedFingerprint = session.fingerprint
                prefs.cachedExpiresAt = session.expiresAt

                // Update UI
                loadDeviceState()

                binding.tvDeviceStatus.text = "READ OK"
                appendActionLog("read_session", "ok", elapsed,
                    "(${session.sessionToken.length} chars)")
                updateStackHealth()

                Toast.makeText(
                    this@MainActivity,
                    "Session read! Expires in ${session.formatTimeLeft()}",
                    Toast.LENGTH_LONG
                ).show()
            } else {
                binding.tvDeviceStatus.text = "READ FAILED"
                appendActionLog("read_session", "fail", elapsed)
                updateStackHealth()
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
        val etMcpUrl = view.findViewById<android.widget.EditText>(R.id.etMcpUrl)
        val etMcpAuthToken = view.findViewById<android.widget.EditText>(R.id.etMcpAuthToken)

        etServerUrl.setText(prefs.serverUrl)
        etApiKey.setText(prefs.serverApiKey)
        etCheckInterval.setText(prefs.checkIntervalMinutes.toString())
        etSyncBefore.setText(prefs.syncBeforeExpiryHours.toString())
        etMcpUrl.setText(prefs.mcpUrl)
        etMcpAuthToken.setText(prefs.mcpAuthToken)

        AlertDialog.Builder(this)
            .setTitle("Settings")
            .setView(view)
            .setPositiveButton("Save") { _, _ ->
                prefs.serverUrl = etServerUrl.text.toString()
                prefs.serverApiKey = etApiKey.text.toString()
                prefs.checkIntervalMinutes = etCheckInterval.text.toString().toIntOrNull() ?: 30
                prefs.syncBeforeExpiryHours = etSyncBefore.text.toString().toIntOrNull() ?: 2
                prefs.mcpUrl = etMcpUrl.text.toString()
                prefs.mcpAuthToken = etMcpAuthToken.text.toString()

                // Update UI
                binding.tvServerUrl.text = prefs.serverUrl
                binding.tvServerUrl2.text = prefs.serverUrl
                binding.tvCheckInterval.text = "${prefs.checkIntervalMinutes} min"
                binding.tvSyncBefore.text = "${prefs.syncBeforeExpiryHours}h before expiry"
                binding.tvMcpUrl.text = prefs.mcpUrl

                Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
                refreshMcpStatus()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
