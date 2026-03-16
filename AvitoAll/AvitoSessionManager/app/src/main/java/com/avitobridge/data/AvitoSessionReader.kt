package com.avitobridge.data

import android.util.Log
import com.topjohnwu.superuser.Shell
import org.w3c.dom.Element
import org.xml.sax.InputSource
import java.io.StringReader
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Reads Avito session data from SharedPreferences using root access
 *
 * Avito stores session data in:
 * /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml
 *
 * Key fields:
 * - fpx: Fingerprint (header 'f')
 * - session: JWT token (sessid)
 * - fpx_calc_time: When fingerprint was calculated
 * - visitor_id: Visitor/device ID
 */
class AvitoSessionReader {

    companion object {
        private const val TAG = "AvitoSessionReader"

        // Avito package and prefs paths
        private const val AVITO_PACKAGE = "com.avito.android"
        private const val PREFS_FILE = "com.avito.android_preferences.xml"
        // Use /data/user/0/ for better Magisk compatibility
        private const val PREFS_PATH = "/data/user/0/$AVITO_PACKAGE/shared_prefs/$PREFS_FILE"
        private const val PREFS_PATH_ALT = "/data/data/$AVITO_PACKAGE/shared_prefs/$PREFS_FILE"

        // SharedPreferences keys we're interested in
        private const val KEY_SESSION = "session"           // JWT token
        private const val KEY_FINGERPRINT = "fpx"           // Fingerprint header
        private const val KEY_FP_CALC_TIME = "fpx_calc_time"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_USER_HASH = "user_hash_id"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_REMOTE_DEVICE_ID = "remote_device_id"
        private const val KEY_VISITOR_ID = "visitor_id"

        // Cookie keys
        private const val KEY_COOKIE_1F_UID = "1f_uid"
        private const val KEY_COOKIE_U = "u_cookie"
        private const val KEY_COOKIE_V = "v_cookie"
    }

    /**
     * Check if root access is available
     */
    fun hasRootAccess(): Boolean {
        return Shell.getShell().isRoot
    }

    /**
     * Check if Avito app is installed
     */
    fun isAvitoInstalled(): Boolean {
        val result = Shell.cmd("pm list packages | grep $AVITO_PACKAGE").exec()
        return result.isSuccess && result.out.isNotEmpty()
    }

    /**
     * Read full session data from Avito SharedPreferences
     */
    fun readSession(): SessionData? {
        Log.d(TAG, "readSession() called")

        // Try libsu first
        var xml: String? = readWithLibsu()

        // Fallback to Runtime.exec
        if (xml == null) {
            Log.d(TAG, "Trying Runtime.exec fallback")
            xml = readWithRuntime()
        }

        if (xml == null) {
            Log.e(TAG, "Failed to read prefs with both methods")
            return null
        }

        Log.d(TAG, "Read ${xml.length} chars of XML")
        val session = parsePrefsXml(xml)
        if (session != null) {
            Log.i(TAG, "Session parsed: token=${session.sessionToken.take(30)}..., fp=${session.fingerprint.take(30)}...")
        }
        return session
    }

    private fun readWithLibsu(): String? {
        try {
            if (!hasRootAccess()) {
                Log.e(TAG, "No root access (libsu)")
                return null
            }
            Log.d(TAG, "Root access confirmed (libsu)")

            // Try multiple paths
            val paths = listOf(
                PREFS_PATH,
                PREFS_PATH_ALT,
                "/data/user_de/0/$AVITO_PACKAGE/shared_prefs/$PREFS_FILE"
            )

            for (path in paths) {
                Log.d(TAG, "Trying path: $path")
                val result = Shell.cmd("cat '$path'").exec()
                Log.d(TAG, "Result for $path: outSize=${result.out.size}")

                if (result.out.isNotEmpty()) {
                    val output = result.out.joinToString("\n")
                    if (output.contains("<?xml") || output.contains("<map>")) {
                        Log.i(TAG, "Success with path: $path")
                        return output
                    }
                    Log.d(TAG, "Output preview: ${output.take(80)}")
                }
            }

            // Debug: list what we can see
            Log.d(TAG, "Listing /data/user/0/...")
            val lsResult = Shell.cmd("ls /data/user/0/ | head -20").exec()
            Log.d(TAG, "Packages: ${lsResult.out.take(10).joinToString(", ")}")

            Log.e(TAG, "Could not read prefs from any path")
            return null
        } catch (e: Exception) {
            Log.e(TAG, "Error with libsu", e)
            return null
        }
    }

    private fun readWithRuntime(): String? {
        // Try different su commands for Magisk compatibility
        val commands = listOf(
            arrayOf("su", "-mm", "-c", "cat '$PREFS_PATH'"),
            arrayOf("su", "-c", "cat '$PREFS_PATH'"),
            arrayOf("su", "-mm", "-c", "cat '$PREFS_PATH_ALT'"),
            arrayOf("su", "-c", "cat '$PREFS_PATH_ALT'")
        )

        for (cmd in commands) {
            try {
                Log.d(TAG, "Runtime trying: ${cmd.joinToString(" ")}")
                val process = Runtime.getRuntime().exec(cmd)
                val output = process.inputStream.bufferedReader().readText()
                val error = process.errorStream.bufferedReader().readText()
                val exitCode = process.waitFor()

                Log.d(TAG, "Runtime result: exitCode=$exitCode, outputLen=${output.length}")

                if (exitCode == 0 && output.isNotEmpty() && output.contains("<map>")) {
                    Log.i(TAG, "Runtime success with: ${cmd.joinToString(" ")}")
                    return output
                }

                if (error.isNotEmpty()) {
                    Log.d(TAG, "Error: ${error.take(100)}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error with Runtime cmd", e)
            }
        }

        Log.e(TAG, "All Runtime methods failed")
        return null
    }

    /**
     * Read only the fingerprint (for quick checks)
     */
    fun readFingerprint(): String? {
        if (!hasRootAccess()) return null

        return try {
            val result = Shell.cmd("cat $PREFS_PATH | grep fpx").exec()
            if (result.isSuccess && result.out.isNotEmpty()) {
                // Parse the line to extract value
                val line = result.out.first()
                extractStringValue(line)
            } else null
        } catch (e: Exception) {
            Log.e(TAG, "Error reading fingerprint", e)
            null
        }
    }

    /**
     * Read only the session token (for quick checks)
     */
    fun readSessionToken(): String? {
        if (!hasRootAccess()) return null

        return try {
            val result = Shell.cmd("cat $PREFS_PATH | grep '\"session\"'").exec()
            if (result.isSuccess && result.out.isNotEmpty()) {
                val line = result.out.first()
                extractStringValue(line)
            } else null
        } catch (e: Exception) {
            Log.e(TAG, "Error reading session token", e)
            null
        }
    }

    /**
     * Parse SharedPreferences XML to extract all relevant data
     */
    private fun parsePrefsXml(xml: String): SessionData? {
        try {
            val factory = DocumentBuilderFactory.newInstance()
            val builder = factory.newDocumentBuilder()
            val doc = builder.parse(InputSource(StringReader(xml)))

            val values = mutableMapOf<String, Any>()

            // Parse <string> elements
            val strings = doc.getElementsByTagName("string")
            for (i in 0 until strings.length) {
                val elem = strings.item(i) as Element
                val name = elem.getAttribute("name")
                val value = elem.textContent
                values[name] = value
            }

            // Parse <long> elements
            val longs = doc.getElementsByTagName("long")
            for (i in 0 until longs.length) {
                val elem = longs.item(i) as Element
                val name = elem.getAttribute("name")
                val value = elem.getAttribute("value").toLongOrNull() ?: 0L
                values[name] = value
            }

            // Extract required fields
            val sessionToken = values[KEY_SESSION] as? String
            if (sessionToken.isNullOrEmpty()) {
                Log.e(TAG, "No session token found in prefs")
                return null
            }

            // Fingerprint is important but not strictly required
            val fingerprint = values[KEY_FINGERPRINT] as? String ?: ""
            if (fingerprint.isEmpty()) {
                Log.w(TAG, "No fingerprint found, continuing without it")
            }

            // Parse JWT to get expiration
            val jwtPayload = SessionData.parseJwt(sessionToken)
            val expiresAt = jwtPayload?.exp ?: 0L

            // Build cookies map
            val cookies = mutableMapOf<String, String>()
            (values[KEY_COOKIE_1F_UID] as? String)?.let { cookies["1f_uid"] = it }
            (values[KEY_COOKIE_U] as? String)?.let { cookies["u"] = it }
            (values[KEY_COOKIE_V] as? String)?.let { cookies["v"] = it }

            return SessionData(
                sessionToken = sessionToken,
                refreshToken = values[KEY_REFRESH_TOKEN] as? String,
                fingerprint = fingerprint,
                deviceId = (values[KEY_DEVICE_ID] as? String)
                    ?: jwtPayload?.deviceId
                    ?: "",
                remoteDeviceId = values[KEY_REMOTE_DEVICE_ID] as? String
                    ?: values[KEY_VISITOR_ID] as? String,
                userId = jwtPayload?.userId,
                userHash = values[KEY_USER_HASH] as? String,
                expiresAt = expiresAt,
                cookies = cookies
            )

        } catch (e: Exception) {
            Log.e(TAG, "Error parsing prefs XML", e)
            return null
        }
    }

    /**
     * Extract string value from XML line like: <string name="key">value</string>
     */
    private fun extractStringValue(line: String): String? {
        return try {
            val start = line.indexOf(">") + 1
            val end = line.lastIndexOf("<")
            if (start > 0 && end > start) {
                line.substring(start, end)
            } else null
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Get Avito app info (version, last update)
     */
    fun getAvitoAppInfo(): AvitoAppInfo? {
        return try {
            val result = Shell.cmd("dumpsys package $AVITO_PACKAGE | grep -E 'versionName|lastUpdateTime'").exec()
            if (result.isSuccess) {
                var version: String? = null
                var lastUpdate: String? = null

                for (line in result.out) {
                    when {
                        line.contains("versionName=") -> {
                            version = line.substringAfter("versionName=").trim()
                        }
                        line.contains("lastUpdateTime=") -> {
                            lastUpdate = line.substringAfter("lastUpdateTime=").trim()
                        }
                    }
                }

                AvitoAppInfo(version, lastUpdate)
            } else null
        } catch (e: Exception) {
            null
        }
    }
}

data class AvitoAppInfo(
    val version: String?,
    val lastUpdate: String?
)
