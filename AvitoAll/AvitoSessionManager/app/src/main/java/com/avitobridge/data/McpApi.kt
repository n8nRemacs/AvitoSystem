package com.avitobridge.data

import android.util.Log
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Lightweight client for the avito-mcp service.
 *
 * Differs from [ServerApi] in:
 *   - Different base URL (homelab :9000)
 *   - Bearer auth scheme on /restart (vs X-Device-Key on xapi)
 *   - Tight 5s timeouts so the dashboard doesn't hang on a wedged service
 */
class McpApi(
    private val baseUrl: String,
    private val authToken: String
) {
    companion object {
        private const val TAG = "McpApi"
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }

    private val gson = Gson()

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    /**
     * GET /healthz — no auth. Returns service health snapshot.
     */
    suspend fun healthCheck(): Result<McpHealth> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/healthz")
                .get()
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val health = gson.fromJson(body, McpHealth::class.java)
                Log.d(TAG, "healthz: status=${health.status} v=${health.version} uptime=${health.uptime_sec}s tools=${health.tools_registered}")
                Result.success(health)
            } else {
                val msg = "healthz ${response.code}: ${body ?: ""}"
                Log.w(TAG, msg)
                Result.failure(Exception(msg))
            }
        } catch (e: Exception) {
            Log.e(TAG, "healthCheck failed: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * POST /restart — Bearer-protected. Service respawns ~3-7s after 200.
     */
    suspend fun restart(): Result<McpRestartResponse> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/restart")
                .header("Authorization", "Bearer $authToken")
                .post("".toRequestBody(JSON))
                .build()

            val response = client.newCall(request).execute()
            val body = response.body?.string()

            if (response.isSuccessful && body != null) {
                val parsed = gson.fromJson(body, McpRestartResponse::class.java)
                Log.i(TAG, "restart: ok ts=${parsed.ts}")
                Result.success(parsed)
            } else {
                val msg = "restart ${response.code}: ${body ?: ""}"
                Log.w(TAG, msg)
                Result.failure(Exception(msg))
            }
        } catch (e: Exception) {
            Log.e(TAG, "restart failed: ${e.message}")
            Result.failure(e)
        }
    }
}

/**
 * GET /healthz response payload.
 */
data class McpHealth(
    val status: String = "",
    val version: String = "",
    val uptime_sec: Int = 0,
    val tools_registered: Int = 0,
    val started_at: String = ""
)

/**
 * POST /restart response payload.
 */
data class McpRestartResponse(
    val restarting: Boolean = false,
    val ts: String = ""
)
