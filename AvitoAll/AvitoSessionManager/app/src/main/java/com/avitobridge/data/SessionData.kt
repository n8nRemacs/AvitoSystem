package com.avitobridge.data

import android.util.Base64
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName

/**
 * Complete session data extracted from Avito app
 */
data class SessionData(
    val sessionToken: String,       // JWT token (sessid)
    val refreshToken: String?,      // Refresh token
    val fingerprint: String,        // Header 'f'
    val deviceId: String,           // X-DeviceId
    val remoteDeviceId: String?,    // X-RemoteDeviceId
    val userId: Long?,              // User ID from JWT
    val userHash: String?,          // User hash for WebSocket
    val expiresAt: Long,            // Unix timestamp
    val cookies: Map<String, String> = emptyMap()
) {
    /**
     * Check if session is expired
     */
    fun isExpired(): Boolean {
        return System.currentTimeMillis() / 1000 > expiresAt
    }

    /**
     * Get hours until expiration
     */
    fun hoursUntilExpiry(): Float {
        val now = System.currentTimeMillis() / 1000
        return (expiresAt - now) / 3600f
    }

    /**
     * Get formatted time until expiration (e.g. "2h 30m" or "45m")
     */
    fun formatTimeLeft(): String {
        return formatHoursMinutes(hoursUntilExpiry())
    }

    /**
     * Check if should sync (less than N hours until expiry)
     */
    fun shouldSync(hoursBeforeExpiry: Int): Boolean {
        return hoursUntilExpiry() < hoursBeforeExpiry
    }

    companion object {
        private val gson = Gson()

        /**
         * Format hours as "Xh Ym" string
         */
        fun formatHoursMinutes(hours: Float): String {
            if (hours <= 0) return "0m"
            val totalMinutes = (hours * 60).toInt()
            val h = totalMinutes / 60
            val m = totalMinutes % 60
            return when {
                h > 0 && m > 0 -> "${h}h ${m}m"
                h > 0 -> "${h}h"
                else -> "${m}m"
            }
        }

        /**
         * Format hours (Double) as "Xh Ym" string
         */
        fun formatHoursMinutes(hours: Double): String {
            return formatHoursMinutes(hours.toFloat())
        }

        /**
         * Parse JWT token to extract user info and expiration
         */
        fun parseJwt(token: String): JwtPayload? {
            return try {
                val parts = token.split(".")
                if (parts.size < 2) return null

                val payload = parts[1]
                // Add padding if needed
                val padded = when (payload.length % 4) {
                    2 -> "$payload=="
                    3 -> "$payload="
                    else -> payload
                }

                val decoded = Base64.decode(padded, Base64.URL_SAFE or Base64.NO_WRAP)
                gson.fromJson(String(decoded), JwtPayload::class.java)
            } catch (e: Exception) {
                null
            }
        }
    }
}

/**
 * JWT payload structure for Avito tokens
 */
data class JwtPayload(
    @SerializedName("exp") val exp: Long,           // Expiration timestamp
    @SerializedName("iat") val iat: Long,           // Issued at
    @SerializedName("u") val userId: Long,          // User ID
    @SerializedName("p") val profileId: Long?,      // Profile ID
    @SerializedName("s") val sessionHash: String?,  // Session hash
    @SerializedName("h") val h: String?,            // Hash
    @SerializedName("d") val deviceId: String?,     // Device ID
    @SerializedName("pl") val platform: String?     // Platform
)

/**
 * Request to send session to server
 */
data class SessionSyncRequest(
    @SerializedName("session_token") val sessionToken: String,
    @SerializedName("refresh_token") val refreshToken: String?,
    @SerializedName("fingerprint") val fingerprint: String,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("remote_device_id") val remoteDeviceId: String?,
    @SerializedName("user_id") val userId: Long?,
    @SerializedName("user_hash") val userHash: String?,
    @SerializedName("expires_at") val expiresAt: Long,
    @SerializedName("cookies") val cookies: Map<String, String>,
    @SerializedName("synced_at") val syncedAt: Long = System.currentTimeMillis() / 1000
)

/**
 * Response from server
 */
data class SessionSyncResponse(
    @SerializedName("success") val success: Boolean,
    @SerializedName("message") val message: String?,
    @SerializedName("session_id") val sessionId: String?
)
