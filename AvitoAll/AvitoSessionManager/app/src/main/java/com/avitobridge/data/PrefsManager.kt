package com.avitobridge.data

import android.content.Context
import android.content.SharedPreferences

/**
 * Manages app preferences
 */
class PrefsManager(context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // Server settings
    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value).apply()

    var serverApiKey: String
        get() = prefs.getString(KEY_API_KEY, DEFAULT_API_KEY) ?: DEFAULT_API_KEY
        set(value) = prefs.edit().putString(KEY_API_KEY, value).apply()

    // Auto-sync settings
    var autoSyncEnabled: Boolean
        get() = prefs.getBoolean(KEY_AUTO_SYNC, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_SYNC, value).apply()

    // Auto-launch Avito when token expiring
    var autoLaunchAvito: Boolean
        get() = prefs.getBoolean(KEY_AUTO_LAUNCH, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_LAUNCH, value).apply()

    // Show local notification when token expiring
    var notifyOnExpiry: Boolean
        get() = prefs.getBoolean(KEY_NOTIFY_EXPIRY, true)
        set(value) = prefs.edit().putBoolean(KEY_NOTIFY_EXPIRY, value).apply()

    var syncBeforeExpiryHours: Int
        get() = prefs.getInt(KEY_SYNC_BEFORE_HOURS, DEFAULT_SYNC_BEFORE_HOURS)
        set(value) = prefs.edit().putInt(KEY_SYNC_BEFORE_HOURS, value).apply()

    var checkIntervalMinutes: Int
        get() = prefs.getInt(KEY_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)
        set(value) = prefs.edit().putInt(KEY_CHECK_INTERVAL, value).apply()

    // Last sync info
    var lastSyncTime: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0)
        set(value) = prefs.edit().putLong(KEY_LAST_SYNC, value).apply()

    var lastSyncStatus: String
        get() = prefs.getString(KEY_LAST_SYNC_STATUS, "Never") ?: "Never"
        set(value) = prefs.edit().putString(KEY_LAST_SYNC_STATUS, value).apply()

    // Cached session data
    var cachedSessionToken: String
        get() = prefs.getString(KEY_SESSION_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_SESSION_TOKEN, value).apply()

    var cachedFingerprint: String
        get() = prefs.getString(KEY_FINGERPRINT, "") ?: ""
        set(value) = prefs.edit().putString(KEY_FINGERPRINT, value).apply()

    var cachedExpiresAt: Long
        get() = prefs.getLong(KEY_EXPIRES_AT, 0)
        set(value) = prefs.edit().putLong(KEY_EXPIRES_AT, value).apply()

    // Telegram notification settings
    var telegramEnabled: Boolean
        get() = prefs.getBoolean(KEY_TELEGRAM_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_TELEGRAM_ENABLED, value).apply()

    var telegramBotToken: String
        get() = prefs.getString(KEY_TELEGRAM_BOT_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TELEGRAM_BOT_TOKEN, value).apply()

    var telegramChatId: String
        get() = prefs.getString(KEY_TELEGRAM_CHAT_ID, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TELEGRAM_CHAT_ID, value).apply()

    // Track last telegram notification to avoid spam
    var lastTelegramNotifyTime: Long
        get() = prefs.getLong(KEY_LAST_TELEGRAM_NOTIFY, 0)
        set(value) = prefs.edit().putLong(KEY_LAST_TELEGRAM_NOTIFY, value).apply()

    // V2.1 NotificationListener settings
    var notificationListenerEnabled: Boolean
        get() = prefs.getBoolean(KEY_NOTIF_LISTENER_ENABLED, true)
        set(value) = prefs.edit().putBoolean(KEY_NOTIF_LISTENER_ENABLED, value).apply()

    var notificationsForwardedTotal: Long
        get() = prefs.getLong(KEY_NOTIF_TOTAL, 0L)
        set(value) = prefs.edit().putLong(KEY_NOTIF_TOTAL, value).apply()

    var notificationsLastForwardedAt: Long
        get() = prefs.getLong(KEY_NOTIF_LAST_AT, 0L)
        set(value) = prefs.edit().putLong(KEY_NOTIF_LAST_AT, value).apply()

    var notificationsLastStatus: String
        get() = prefs.getString(KEY_NOTIF_LAST_STATUS, "") ?: ""
        set(value) = prefs.edit().putString(KEY_NOTIF_LAST_STATUS, value).apply()

    // avito-mcp service settings
    var mcpUrl: String
        get() = prefs.getString(KEY_MCP_URL, DEFAULT_MCP_URL) ?: DEFAULT_MCP_URL
        set(value) = prefs.edit().putString(KEY_MCP_URL, value).apply()

    var mcpAuthToken: String
        get() = prefs.getString(KEY_MCP_AUTH_TOKEN, DEFAULT_MCP_AUTH_TOKEN) ?: DEFAULT_MCP_AUTH_TOKEN
        set(value) = prefs.edit().putString(KEY_MCP_AUTH_TOKEN, value).apply()

    companion object {
        private const val PREFS_NAME = "avito_session_manager"

        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_AUTO_SYNC = "auto_sync"
        private const val KEY_AUTO_LAUNCH = "auto_launch_avito"
        private const val KEY_NOTIFY_EXPIRY = "notify_on_expiry"
        private const val KEY_SYNC_BEFORE_HOURS = "sync_before_hours"
        private const val KEY_CHECK_INTERVAL = "check_interval"
        private const val KEY_LAST_SYNC = "last_sync"
        private const val KEY_LAST_SYNC_STATUS = "last_sync_status"
        private const val KEY_SESSION_TOKEN = "session_token"
        private const val KEY_FINGERPRINT = "fingerprint"
        private const val KEY_EXPIRES_AT = "expires_at"
        private const val KEY_TELEGRAM_ENABLED = "telegram_enabled"
        private const val KEY_TELEGRAM_BOT_TOKEN = "telegram_bot_token"
        private const val KEY_TELEGRAM_CHAT_ID = "telegram_chat_id"
        private const val KEY_LAST_TELEGRAM_NOTIFY = "last_telegram_notify"
        private const val KEY_MCP_URL = "mcp_url"
        private const val KEY_MCP_AUTH_TOKEN = "mcp_auth_token"
        private const val KEY_NOTIF_LISTENER_ENABLED = "notification_listener_enabled"
        private const val KEY_NOTIF_TOTAL = "notifications_forwarded_total"
        private const val KEY_NOTIF_LAST_AT = "notifications_last_forwarded_at"
        private const val KEY_NOTIF_LAST_STATUS = "notifications_last_status"

        private const val DEFAULT_SERVER_URL = "http://155.212.221.189:8080"
        private const val DEFAULT_API_KEY = "avito_sync_key_2026"
        private const val DEFAULT_SYNC_BEFORE_HOURS = 2
        private const val DEFAULT_CHECK_INTERVAL = 30 // minutes
        private const val DEFAULT_MCP_URL = "http://192.168.31.97:9000"
        private const val DEFAULT_MCP_AUTH_TOKEN = "dev-mcp-token-change-me"
    }
}
