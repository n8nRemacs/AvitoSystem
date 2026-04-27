package com.avitobridge.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.avitobridge.App
import com.avitobridge.R
import com.avitobridge.data.AvitoSessionReader
import com.avitobridge.data.ServerApi
import com.avitobridge.data.SessionData
import com.avitobridge.ui.MainActivity
import com.topjohnwu.superuser.Shell
import kotlinx.coroutines.*
import java.text.SimpleDateFormat
import java.util.*

/**
 * Background service for monitoring Avito session and auto-syncing
 *
 * Two modes:
 * 1. Manual sync - triggered by ACTION_SYNC_NOW
 * 2. Auto sync - runs periodically and syncs when token expires soon
 */
class SessionMonitorService : Service() {

    companion object {
        private const val TAG = "SessionMonitorService"
        private const val NOTIFICATION_ID = 1

        // Actions
        const val ACTION_START = "com.avitobridge.START"
        const val ACTION_STOP = "com.avitobridge.STOP"
        const val ACTION_SYNC_NOW = "com.avitobridge.SYNC_NOW"

        // Broadcast actions for UI updates
        const val BROADCAST_STATUS_UPDATE = "com.avitobridge.STATUS_UPDATE"
        const val EXTRA_STATUS = "status"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_SESSION_DATA = "session_data"
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var monitorJob: Job? = null

    private lateinit var sessionReader: AvitoSessionReader
    private var serverApi: ServerApi? = null

    private val prefs by lazy { App.instance.prefs }
    private val dateFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    // Current state
    private var lastSession: SessionData? = null
    private var isMonitoring = false
    private var lastNotificationTime = 0L
    private val NOTIFICATION_COOLDOWN_MS = 60 * 60 * 1000L // 1 hour between notifications

    override fun onCreate() {
        super.onCreate()
        sessionReader = AvitoSessionReader()
        updateServerApi()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Always start foreground immediately to avoid ANR
        startForeground(NOTIFICATION_ID, createNotification("Ready"))

        when (intent?.action) {
            ACTION_START -> startMonitoring()
            ACTION_STOP -> stopMonitoring()
            ACTION_SYNC_NOW -> syncNow()
            else -> {} // Just keep running in foreground
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopMonitoring()
        scope.cancel()
        super.onDestroy()
    }

    /**
     * Start foreground service and begin monitoring
     */
    private fun startMonitoring() {
        if (isMonitoring) return

        Log.i(TAG, "Starting session monitor")
        updateNotification("Starting...")
        isMonitoring = true

        // Initial check
        scope.launch {
            checkAndSync(force = false)
        }

        // Start periodic monitoring
        monitorJob = scope.launch {
            while (isActive) {
                delay(prefs.checkIntervalMinutes * 60 * 1000L)
                checkAndSync(force = false)
            }
        }

        broadcastStatus("running", "Monitor started")
    }

    /**
     * Stop monitoring
     */
    private fun stopMonitoring() {
        Log.i(TAG, "Stopping session monitor")
        isMonitoring = false
        monitorJob?.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        broadcastStatus("stopped", "Monitor stopped")
    }

    /**
     * Force sync now (manual trigger)
     */
    private fun syncNow() {
        Log.i(TAG, "Manual sync triggered")
        scope.launch {
            checkAndSync(force = true)
        }
    }

    /**
     * Check session and sync if needed
     */
    private suspend fun checkAndSync(force: Boolean) {
        try {
            updateNotification("Checking session...")
            broadcastStatus("checking", "Reading session...")

            // Check root access
            if (!sessionReader.hasRootAccess()) {
                val msg = "No root access!"
                updateNotification(msg)
                broadcastStatus("error", msg)
                return
            }

            // Check Avito installed
            if (!sessionReader.isAvitoInstalled()) {
                val msg = "Avito not installed!"
                updateNotification(msg)
                broadcastStatus("error", msg)
                return
            }

            // Read session
            val session = sessionReader.readSession()
            if (session == null) {
                val msg = "Failed to read session"
                updateNotification(msg)
                broadcastStatus("error", msg)
                return
            }

            lastSession = session

            // Cache locally
            prefs.cachedSessionToken = session.sessionToken
            prefs.cachedFingerprint = session.fingerprint
            prefs.cachedExpiresAt = session.expiresAt

            // Check expiration
            val hoursLeft = session.hoursUntilExpiry()
            val expiresText = "${session.formatTimeLeft()} left"

            if (session.isExpired()) {
                val msg = "Session EXPIRED!"
                updateNotification(msg)
                broadcastStatus("expired", msg)

                // Send notification if enabled
                if (prefs.notifyOnExpiry) {
                    sendExpiryNotification("Token expired!", "Open Avito app to refresh")
                }

                // Launch Avito if enabled
                if (prefs.autoLaunchAvito) {
                    Log.i(TAG, "Token expired, launching Avito to refresh")
                    launchAvito()
                }
                return
            }

            // If token expires soon, handle auto-refresh
            if (hoursLeft < prefs.syncBeforeExpiryHours && hoursLeft > 0) {
                Log.i(TAG, "Token expiring soon ($expiresText)")

                // Send notification if enabled
                if (prefs.notifyOnExpiry) {
                    sendExpiryNotification("Token expiring!", "$expiresText - Open Avito to refresh")
                }

                // Launch Avito if enabled
                if (prefs.autoLaunchAvito) {
                    Log.i(TAG, "Launching Avito to refresh token")
                    launchAvito()
                    // Wait for Avito to refresh token
                    delay(5000)
                    // Re-read session after Avito launch
                    val refreshedSession = sessionReader.readSession()
                    if (refreshedSession != null && refreshedSession.expiresAt > session.expiresAt) {
                        Log.i(TAG, "Token refreshed! New expiry: ${refreshedSession.formatTimeLeft()}")
                        lastSession = refreshedSession
                        prefs.cachedSessionToken = refreshedSession.sessionToken
                        prefs.cachedFingerprint = refreshedSession.fingerprint
                        prefs.cachedExpiresAt = refreshedSession.expiresAt

                        // IMPORTANT: Sync refreshed token to server immediately
                        Log.i(TAG, "Syncing refreshed token to server...")
                        val syncResult = syncToServer(refreshedSession)
                        if (syncResult) {
                            prefs.lastSyncTime = System.currentTimeMillis()
                            prefs.lastSyncStatus = "Refreshed & synced at ${dateFormat.format(Date())}"
                            Log.i(TAG, "Refreshed token synced successfully!")
                            broadcastStatus("synced", "Token refreshed & synced!")
                        } else {
                            Log.e(TAG, "Failed to sync refreshed token")
                            prefs.lastSyncStatus = "Refresh OK, sync FAILED at ${dateFormat.format(Date())}"
                            broadcastStatus("error", "Token refreshed but sync failed!")
                        }
                    }
                }
            }

            // Decide if we need to sync
            val currentSession = lastSession ?: session
            val shouldSync = force ||
                    (prefs.autoSyncEnabled && currentSession.shouldSync(prefs.syncBeforeExpiryHours))

            if (shouldSync) {
                updateNotification("Syncing to server...")
                broadcastStatus("syncing", "Syncing...")

                val result = syncToServer(session)

                if (result) {
                    prefs.lastSyncTime = System.currentTimeMillis()
                    prefs.lastSyncStatus = "OK at ${dateFormat.format(Date())}"

                    val msg = "Synced! $expiresText"
                    updateNotification(msg)
                    broadcastStatus("synced", msg)
                } else {
                    prefs.lastSyncStatus = "FAILED at ${dateFormat.format(Date())}"

                    val msg = "Sync failed! $expiresText"
                    updateNotification(msg)
                    broadcastStatus("error", msg)
                }
            } else {
                val msg = "OK - $expiresText"
                updateNotification(msg)
                broadcastStatus("ok", msg)
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error in checkAndSync", e)
            val msg = "Error: ${e.message}"
            updateNotification(msg)
            broadcastStatus("error", msg)
        }
    }

    /**
     * Sync session to server
     */
    private suspend fun syncToServer(session: SessionData): Boolean {
        updateServerApi()

        val api = serverApi
        if (api == null) {
            Log.w(TAG, "Server not configured")
            return false
        }

        return try {
            val result = api.syncSession(session)
            result.isSuccess
        } catch (e: Exception) {
            Log.e(TAG, "Sync error", e)
            false
        }
    }

    /**
     * Update ServerApi instance if settings changed
     */
    private fun updateServerApi() {
        val url = prefs.serverUrl
        val key = prefs.serverApiKey

        if (url.isNotBlank() && key.isNotBlank()) {
            serverApi = ServerApi(url, key)
        }
    }

    /**
     * Create foreground notification
     */
    private fun createNotification(status: String): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Sync now action
        val syncIntent = Intent(this, SessionMonitorService::class.java).apply {
            action = ACTION_SYNC_NOW
        }
        val syncPendingIntent = PendingIntent.getService(
            this, 1, syncIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, App.CHANNEL_ID)
            .setContentTitle("Avito Session Monitor")
            .setContentText(status)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .addAction(R.drawable.ic_sync, "Sync Now", syncPendingIntent)
            .setOngoing(true)
            .build()
    }

    /**
     * Update notification text
     */
    private fun updateNotification(status: String) {
        val notification = createNotification(status)
        val manager = getSystemService(android.app.NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }

    /**
     * Broadcast status update to UI
     */
    private fun broadcastStatus(status: String, message: String) {
        val intent = Intent(BROADCAST_STATUS_UPDATE).apply {
            putExtra(EXTRA_STATUS, status)
            putExtra(EXTRA_MESSAGE, message)
            // Add session info if available
            lastSession?.let {
                putExtra("expires_at", it.expiresAt)
                putExtra("user_id", it.userId)
                putExtra("has_fingerprint", it.fingerprint.isNotEmpty())
            }
        }
        sendBroadcast(intent)
    }

    /**
     * Send notification about token expiry (with cooldown to prevent spam)
     */
    private fun sendExpiryNotification(title: String, message: String) {
        val now = System.currentTimeMillis()
        if (now - lastNotificationTime < NOTIFICATION_COOLDOWN_MS) {
            Log.d(TAG, "Skipping notification - cooldown active")
            return
        }
        lastNotificationTime = now

        val intent = packageManager.getLaunchIntentForPackage("com.avito.android")
        val pendingIntent = if (intent != null) {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            PendingIntent.getActivity(this, 2, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        } else {
            null
        }

        val notification = NotificationCompat.Builder(this, App.CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(message)
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .apply {
                if (pendingIntent != null) {
                    setContentIntent(pendingIntent)
                    addAction(R.drawable.ic_sync, "Open Avito", pendingIntent)
                }
            }
            .build()

        val manager = getSystemService(android.app.NotificationManager::class.java)
        manager.notify(2, notification)
    }

    /**
     * Launch Avito app to trigger token refresh.
     *
     * Android 10+ silently blocks startActivity() from a background service,
     * so a plain Intent launch is unreliable when the user is in another app
     * or the device is locked — exactly the cases where the token goes stale.
     *
     * Since the device is rooted (we already use libsu to read Avito's
     * SharedPrefs), we shell out to ``monkey`` as root, which is exempt from
     * the background-activity-start restriction. ``monkey`` resolves the
     * package's launcher activity itself, so we don't have to hard-code
     * com.avito.android's main Activity name (which would break across app
     * updates).
     *
     * Fallback path uses the original startActivity() so the feature still
     * works on a non-rooted device with the user actively using the phone.
     */
    private fun launchAvito() {
        Log.i(TAG, "Launching Avito app...")
        updateNotification("Launching Avito to refresh token...")

        // Preferred: root-based launch via monkey — works from background.
        try {
            val result = Shell.cmd(
                "monkey -p com.avito.android -c android.intent.category.LAUNCHER 1"
            ).exec()
            if (result.isSuccess) {
                Log.i(TAG, "Avito launched via root (monkey)")
                return
            }
            Log.w(TAG, "monkey launch failed: out=${result.out.take(2)} err=${result.err.take(2)}")
        } catch (e: Exception) {
            Log.w(TAG, "monkey launch threw — falling back to Intent", e)
        }

        // Fallback: Intent — only works on Android 10+ when the app
        // happens to be foreground or has a recently-clicked notification.
        try {
            val launchIntent = packageManager.getLaunchIntentForPackage("com.avito.android")
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(launchIntent)
                Log.i(TAG, "Avito launched via Intent (fallback)")
            } else {
                Log.e(TAG, "Could not get launch intent for Avito")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch Avito via Intent fallback", e)
        }
    }
}
