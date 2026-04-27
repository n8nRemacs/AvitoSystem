package com.avitobridge.service

import android.app.Notification
import android.app.PendingIntent
import android.content.Intent
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.avitobridge.App
import com.avitobridge.data.NotificationForwardRequest
import com.avitobridge.data.PrefsManager
import com.avitobridge.data.ServerApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * V2.1 third channel for receiving Avito chat events.
 *
 * Android FCM push notifications from `com.avito.android` are intercepted as
 * they land on the phone's status bar and forwarded to xapi
 * `POST /api/v1/notifications`. This is independent of the xapi↔Avito
 * WebSocket — useful when that link is wedged but Avito still pushes via FCM.
 *
 * Setup (one-time, manual): user grants this app access via
 *   Settings → Notifications → Notification access → Avito Session Manager.
 * Until then `onNotificationPosted` is never called by Android.
 */
class AvitoNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val watchedPackages = setOf(
        "com.avito.android",
        // Add other Avito-affiliated packages here if needed (e.g. test build).
    )

    /**
     * In-memory dedup ring buffer. Android can re-post the same notification
     * (e.g. when the user reads it elsewhere) — we don't want to spam xapi.
     * Keyed by `(package, id, tag, title.hash)`.
     */
    private val recentKeys = ArrayDeque<String>()
    private val recentSet = HashSet<String>()
    private val maxRecent = 100

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.i(TAG, "AvitoNotificationListener connected")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Log.w(TAG, "AvitoNotificationListener disconnected — Android may have revoked access")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return
        val pkg = sbn.packageName ?: return
        if (pkg !in watchedPackages) return

        val prefs = try {
            App.instance.prefs
        } catch (_: Throwable) {
            // App not initialised yet (very early boot): fall back to a fresh prefs.
            PrefsManager(applicationContext)
        }
        if (!prefs.notificationListenerEnabled) {
            return
        }

        val extras: Bundle = sbn.notification?.extras ?: Bundle()
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()
        val subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString()

        val key = buildString {
            append(pkg); append('|'); append(sbn.id); append('|')
            append(sbn.tag ?: ""); append('|')
            append(title?.hashCode() ?: 0); append('|')
            append((bigText ?: text)?.hashCode() ?: 0)
        }
        if (!rememberKey(key)) {
            Log.d(TAG, "skip duplicate notification key=$key")
            return
        }

        val collected = collectExtras(extras).orEmpty()
        val deeplink = sbn.notification?.contentIntent?.let { collectPendingIntentExtras(it) }
            .orEmpty()
        val mergedExtras: Map<String, String>? =
            (collected + deeplink).takeIf { it.isNotEmpty() }

        val payload = NotificationForwardRequest(
            packageName = pkg,
            notificationId = sbn.id,
            tag = sbn.tag,
            title = title,
            body = text,
            bigText = bigText,
            subText = subText,
            postedAt = ISO_FORMATTER.format(Date(sbn.postTime)),
            extras = mergedExtras,
        )

        Log.i(TAG, "forwarding notification pkg=$pkg id=${sbn.id} tag=${sbn.tag} title=$title")

        val api = ServerApi(prefs.serverUrl, prefs.serverApiKey)
        scope.launch {
            val result = api.forwardNotification(payload)
            val now = System.currentTimeMillis()
            result.fold(
                onSuccess = { resp ->
                    prefs.notificationsForwardedTotal = prefs.notificationsForwardedTotal + 1
                    prefs.notificationsLastForwardedAt = now
                    prefs.notificationsLastStatus =
                        "ok db_id=${resp.dbId} broadcast=${resp.broadcast}"
                },
                onFailure = { exc ->
                    prefs.notificationsLastStatus = "error: ${exc.message?.take(80) ?: exc.javaClass.simpleName}"
                    Log.w(TAG, "forward failed: ${exc.message}")
                },
            )
        }
    }

    /** Returns true if the key was new and recorded; false if it was a duplicate. */
    @Synchronized
    private fun rememberKey(key: String): Boolean {
        if (key in recentSet) return false
        recentSet.add(key)
        recentKeys.addLast(key)
        while (recentKeys.size > maxRecent) {
            val oldest = recentKeys.removeFirst()
            recentSet.remove(oldest)
        }
        return true
    }

    /**
     * V2.1 Phase B: pull the chat deep-link out of the notification's
     * `contentIntent` PendingIntent.
     *
     * Avito's mobile app embeds the canonical channel id (`u2i-...`) inside
     * the deep-link Intent that launches when the user taps the notification.
     * That Intent's extras (and `data` Uri) are NOT exposed via Notification.EXTRA_*,
     * so we need reflection to pull them out:
     *
     * 1. `PendingIntent.getIntent()` is `@hide` but stable since API 23 — it
     *    returns the wrapped Intent without sending it.
     * 2. Walk Intent.action / Intent.dataString / Intent.extras and flatten
     *    string-ish values into a `deeplink_<key>` map. The bot regex scans
     *    every string in `extras` for `u2[iu]-...`, so as soon as the channel
     *    id is anywhere in the deep-link, we'll find it.
     *
     * Reflection failures (SDK changes, OEM patches) return an empty map —
     * the server-side fallback in messenger-bot still picks up the slack via
     * a `/messenger/channels` lookup.
     */
    private fun collectPendingIntentExtras(pi: PendingIntent): Map<String, String> {
        val out = mutableMapOf<String, String>()
        val intent: Intent? = try {
            val getIntent = PendingIntent::class.java.getDeclaredMethod("getIntent")
            getIntent.isAccessible = true
            getIntent.invoke(pi) as? Intent
        } catch (e: Throwable) {
            Log.w(TAG, "PendingIntent.getIntent() reflection failed: ${e.message}")
            null
        }
        if (intent == null) return out

        intent.action?.takeIf { it.isNotEmpty() }?.let {
            out["deeplink_action"] = it.take(500)
        }
        intent.dataString?.takeIf { it.isNotEmpty() }?.let {
            out["deeplink_uri"] = it.take(500)
        }
        intent.component?.flattenToShortString()?.let {
            out["deeplink_component"] = it.take(500)
        }
        val bundle: Bundle? = try {
            intent.extras
        } catch (_: Throwable) {
            null
        }
        if (bundle != null) {
            for (key in bundle.keySet()) {
                val v = try {
                    bundle.get(key)
                } catch (_: Throwable) {
                    continue
                } ?: continue
                if (v is String || v is CharSequence) {
                    val str = v.toString()
                    if (str.isNotEmpty()) {
                        out["deeplink_$key"] = str.take(500)
                    }
                }
            }
        }
        return out
    }

    /**
     * Pull a few high-signal entries from the notification extras Bundle into
     * a flat string map for the backend. We avoid serialising the whole Bundle
     * because it can carry binary blobs (Bitmap thumbnails, RemoteViews).
     */
    private fun collectExtras(extras: Bundle): Map<String, String>? {
        val keys = listOf(
            Notification.EXTRA_TEMPLATE,
            Notification.EXTRA_CHANNEL_ID,
            Notification.EXTRA_CHANNEL_GROUP_ID,
            Notification.EXTRA_CONVERSATION_TITLE,
            Notification.EXTRA_SUMMARY_TEXT,
            Notification.EXTRA_INFO_TEXT,
        )
        val out = mutableMapOf<String, String>()
        for (k in keys) {
            val v = extras.get(k) ?: continue
            out[k] = v.toString().take(500)
        }
        return if (out.isEmpty()) null else out
    }

    companion object {
        private const val TAG = "AvitoNotifListener"
        private val ISO_FORMATTER = SimpleDateFormat(
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
            Locale.US
        ).apply {
            timeZone = java.util.TimeZone.getTimeZone("UTC")
        }
    }
}
