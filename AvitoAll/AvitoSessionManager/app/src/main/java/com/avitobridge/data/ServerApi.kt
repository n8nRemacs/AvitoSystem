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
     * Get current server-stored Avito session (xapi: GET /api/v1/sessions/current).
     */
    suspend fun getServerSession(): Result<ServerSessionInfo> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/v1/sessions/current")
                .header("X-Api-Key", apiKey)
                .header("X-Device-Key", apiKey)
                .get()
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val info = gson.fromJson(body, ServerSessionInfo::class.java)
                Log.d(TAG, "sessions/current: is_active=${info.is_active} ttl=${info.ttl_human}")
                Result.success(info)
            } else {
                Result.failure(Exception("sessions/current ${response.code}: ${body ?: ""}"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "getServerSession failed", e)
            Result.failure(e)
        }
    }

    /**
     * Forward an intercepted Android notification to xapi
     * `POST /api/v1/notifications`. Returns the persisted DB id and whether
     * an SSE subscriber received the broadcast.
     */
    suspend fun forwardNotification(payload: NotificationForwardRequest): Result<NotificationForwardResponse> =
        withContext(Dispatchers.IO) {
            try {
                val json = gson.toJson(payload)

                val httpRequest = Request.Builder()
                    .url("$baseUrl/api/v1/notifications")
                    .header("Content-Type", "application/json")
                    .header("X-Device-Key", apiKey)
                    .post(json.toRequestBody(JSON))
                    .build()

                val response = client.newCall(httpRequest).execute()
                val body = response.body?.string()

                if (response.isSuccessful && body != null) {
                    val parsed = gson.fromJson(body, NotificationForwardResponse::class.java)
                    Log.i(TAG, "notifications forwarded db_id=${parsed.dbId} broadcast=${parsed.broadcast}")
                    Result.success(parsed)
                } else {
                    val error = "notifications HTTP ${response.code}: ${body ?: "no body"}"
                    Log.w(TAG, error)
                    Result.failure(Exception(error))
                }
            } catch (e: Exception) {
                Log.e(TAG, "forwardNotification failed", e)
                Result.failure(e)
            }
        }

    /**
     * Get unread messenger count from xapi (proves JWT pipe works).
     */
    suspend fun getUnreadCount(): Result<Int> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/v1/messenger/unread-count")
                .header("X-Api-Key", apiKey)
                .header("X-Device-Key", apiKey)
                .get()
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val parsed = gson.fromJson(body, UnreadCountResponse::class.java)
                Log.d(TAG, "messenger/unread-count: ${parsed.count}")
                Result.success(parsed.count)
            } else {
                Result.failure(Exception("unread-count ${response.code}: ${body ?: ""}"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "getUnreadCount failed", e)
            Result.failure(e)
        }
    }
}

/**
 * GET /api/v1/sessions/current response.
 */
data class ServerSessionInfo(
    val is_active: Boolean = false,
    val user_id: Long? = null,
    val source: String? = null,
    val ttl_seconds: Int? = null,
    val ttl_human: String? = null,
    val expires_at: String? = null,
    val created_at: String? = null,
    val device_id: String? = null,
    val fingerprint_preview: String? = null
)

/**
 * GET /api/v1/messenger/unread-count response.
 */
data class UnreadCountResponse(
    val count: Int = 0
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
