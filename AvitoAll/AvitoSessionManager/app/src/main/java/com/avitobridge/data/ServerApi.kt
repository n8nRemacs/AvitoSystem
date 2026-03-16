package com.avitobridge.data

import android.util.Log
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * API client for syncing session data with server
 */
class ServerApi(
    private val baseUrl: String,
    private val apiKey: String
) {
    companion object {
        private const val TAG = "ServerApi"
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }

    private val gson = Gson()

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    /**
     * Sync session data to server
     */
    suspend fun syncSession(session: SessionData): Result<SessionSyncResponse> = withContext(Dispatchers.IO) {
        try {
            val request = SessionSyncRequest(
                sessionToken = session.sessionToken,
                refreshToken = session.refreshToken,
                fingerprint = session.fingerprint,
                deviceId = session.deviceId,
                remoteDeviceId = session.remoteDeviceId,
                userId = session.userId,
                userHash = session.userHash,
                expiresAt = session.expiresAt,
                cookies = session.cookies
            )

            val json = gson.toJson(request)
            Log.d(TAG, "Syncing session to $baseUrl")

            val httpRequest = Request.Builder()
                .url("$baseUrl/api/v1/sessions")
                .header("Content-Type", "application/json")
                .header("X-Device-Key", apiKey)
                .post(json.toRequestBody(JSON))
                .build()

            val response = client.newCall(httpRequest).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val syncResponse = gson.fromJson(body, SessionSyncResponse::class.java)
                Log.i(TAG, "Sync successful: ${syncResponse.message}")
                Result.success(syncResponse)
            } else {
                val error = "Server error: ${response.code} - ${body ?: "No body"}"
                Log.e(TAG, error)
                Result.failure(Exception(error))
            }

        } catch (e: Exception) {
            Log.e(TAG, "Sync failed", e)
            Result.failure(e)
        }
    }

    /**
     * Check server health
     */
    suspend fun healthCheck(): Boolean = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/health")
                .get()
                .build()

            val response = client.newCall(request).execute()
            response.isSuccessful
        } catch (e: Exception) {
            Log.e(TAG, "Health check failed", e)
            false
        }
    }

    /**
     * Send device ping to server
     */
    suspend fun sendPing(
        batteryLevel: Int,
        avitoRunning: Boolean,
        lastSessionUpdate: Long
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            val pingData = mapOf(
                "battery_level" to batteryLevel,
                "avito_app_running" to avitoRunning,
                "last_session_update" to lastSessionUpdate,
                "timestamp" to System.currentTimeMillis() / 1000
            )

            val json = gson.toJson(pingData)

            val request = Request.Builder()
                .url("$baseUrl/api/v1/devices/ping")
                .header("Content-Type", "application/json")
                .header("X-Device-Key", apiKey)
                .post(json.toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            response.isSuccessful
        } catch (e: Exception) {
            Log.e(TAG, "Ping failed", e)
            false
        }
    }

    /**
     * Get full server status (session + MCP)
     */
    suspend fun getFullStatus(): Result<FullStatusResponse> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/v1/full-status")
                .get()
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val status = gson.fromJson(body, FullStatusResponse::class.java)
                Result.success(status)
            } else {
                Result.failure(Exception("Server error: ${response.code}"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get status failed", e)
            Result.failure(e)
        }
    }

    /**
     * Restart MCP (Telegram bot) service
     */
    suspend fun restartMcp(): Result<McpRestartResponse> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/v1/mcp/restart")
                .header("X-Device-Key", apiKey)
                .post("".toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val result = gson.fromJson(body, McpRestartResponse::class.java)
                Result.success(result)
            } else {
                Result.failure(Exception("Restart failed: ${response.code}"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "MCP restart failed", e)
            Result.failure(e)
        }
    }
}

// Response classes for new endpoints
data class FullStatusResponse(
    val server: ServerStatus,
    val session: SessionStatus?,
    val mcp: McpStatus?
)

data class ServerStatus(
    val status: String,
    val timestamp: Long
)

data class SessionStatus(
    val exists: Boolean,
    val expires_at: Long = 0,
    val hours_left: Double = 0.0,
    val is_valid: Boolean = false,
    val updated_at: Long = 0,
    val token_preview: String = ""
)

data class McpStatus(
    val service: String,
    val is_running: Boolean,
    val status: String
)

data class McpRestartResponse(
    val success: Boolean,
    val message: String = "",
    val error: String = ""
)

/**
 * Telegram notification sender
 */
class TelegramNotifier(
    private val botToken: String,
    private val chatId: String
) {
    companion object {
        private const val TAG = "TelegramNotifier"
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()

    /**
     * Send token expiry notification to Telegram
     */
    suspend fun sendExpiryNotification(
        hoursLeft: Float,
        userId: Long?,
        isExpired: Boolean = false
    ): Boolean = withContext(Dispatchers.IO) {
        if (botToken.isBlank() || chatId.isBlank()) {
            Log.w(TAG, "Telegram not configured")
            return@withContext false
        }

        val emoji = if (isExpired) "\u26A0\uFE0F" else "\u23F0"
        val status = if (isExpired) "EXPIRED" else "EXPIRING"

        val message = buildString {
            appendLine("$emoji <b>Avito Session $status</b>")
            appendLine()
            if (isExpired) {
                appendLine("\u274C Token has expired!")
            } else {
                appendLine("\u23F1 Time left: <b>${String.format("%.1f", hoursLeft)}h</b>")
            }
            userId?.let { appendLine("\uD83D\uDC64 User ID: $it") }
            appendLine()
            appendLine("\uD83D\uDCF1 Please open Avito app to refresh the token")
        }

        try {
            val url = "https://api.telegram.org/bot$botToken/sendMessage"
            val payload = mapOf(
                "chat_id" to chatId,
                "text" to message,
                "parse_mode" to "HTML"
            )

            val request = Request.Builder()
                .url(url)
                .post(gson.toJson(payload).toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            val success = response.isSuccessful

            if (success) {
                Log.i(TAG, "Telegram notification sent")
            } else {
                Log.e(TAG, "Telegram error: ${response.code} - ${response.body?.string()}")
            }

            success
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send Telegram notification", e)
            false
        }
    }

    /**
     * Send sync success notification
     */
    suspend fun sendSyncNotification(hoursLeft: Float, userId: Long?): Boolean = withContext(Dispatchers.IO) {
        if (botToken.isBlank() || chatId.isBlank()) return@withContext false

        val message = buildString {
            appendLine("\u2705 <b>Avito Session Synced</b>")
            appendLine()
            appendLine("\u23F1 Token valid for: <b>${String.format("%.1f", hoursLeft)}h</b>")
            userId?.let { appendLine("\uD83D\uDC64 User ID: $it") }
        }

        try {
            val url = "https://api.telegram.org/bot$botToken/sendMessage"
            val payload = mapOf(
                "chat_id" to chatId,
                "text" to message,
                "parse_mode" to "HTML"
            )

            val request = Request.Builder()
                .url(url)
                .post(gson.toJson(payload).toRequestBody(JSON))
                .build()

            client.newCall(request).execute().isSuccessful
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send sync notification", e)
            false
        }
    }

    /**
     * Test connection by sending a test message
     */
    suspend fun testConnection(): Result<String> = withContext(Dispatchers.IO) {
        if (botToken.isBlank() || chatId.isBlank()) {
            return@withContext Result.failure(Exception("Bot token or chat ID not configured"))
        }

        try {
            val url = "https://api.telegram.org/bot$botToken/sendMessage"
            val payload = mapOf(
                "chat_id" to chatId,
                "text" to "\uD83D\uDD14 Test notification from Avito Session Manager",
                "parse_mode" to "HTML"
            )

            val request = Request.Builder()
                .url(url)
                .post(gson.toJson(payload).toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful) {
                Result.success("Message sent successfully!")
            } else {
                Result.failure(Exception("Error ${response.code}: $body"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

/**
 * Simple server API for testing without full backend
 * Saves session to a simple HTTP endpoint or file server
 */
class SimpleServerApi(
    private val webhookUrl: String
) {
    companion object {
        private const val TAG = "SimpleServerApi"
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }

    private val gson = Gson()

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    /**
     * Send session to webhook (Telegram, Discord, etc.)
     */
    suspend fun sendToWebhook(session: SessionData): Boolean = withContext(Dispatchers.IO) {
        try {
            val message = buildString {
                appendLine("Session Update")
                appendLine("==============")
                appendLine("User ID: ${session.userId}")
                appendLine("Expires: ${session.hoursUntilExpiry()} hours")
                appendLine("Token: ${session.sessionToken.take(50)}...")
                appendLine("Fingerprint: ${session.fingerprint.take(50)}...")
            }

            // For Telegram Bot API
            if (webhookUrl.contains("telegram")) {
                val payload = mapOf(
                    "text" to message,
                    "parse_mode" to "HTML"
                )
                val json = gson.toJson(payload)

                val request = Request.Builder()
                    .url(webhookUrl)
                    .post(json.toRequestBody(JSON))
                    .build()

                val response = client.newCall(request).execute()
                return@withContext response.isSuccessful
            }

            // Generic webhook
            val payload = mapOf(
                "session_token" to session.sessionToken,
                "fingerprint" to session.fingerprint,
                "expires_at" to session.expiresAt,
                "user_id" to session.userId,
                "device_id" to session.deviceId
            )
            val json = gson.toJson(payload)

            val request = Request.Builder()
                .url(webhookUrl)
                .post(json.toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            response.isSuccessful

        } catch (e: Exception) {
            Log.e(TAG, "Webhook failed", e)
            false
        }
    }
}
