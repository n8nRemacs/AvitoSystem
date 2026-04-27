package com.avitobridge.data

import com.google.gson.annotations.SerializedName

/**
 * Payload sent to xapi `POST /api/v1/notifications` whenever
 * [com.avitobridge.service.AvitoNotificationListener] picks up a notification
 * from a watched package.
 *
 * Field names use snake_case via [SerializedName] to match the FastAPI
 * Pydantic model on the backend (which accepts both `text` and `body`).
 */
data class NotificationForwardRequest(
    @SerializedName("source") val source: String = "android_notification",
    @SerializedName("package_name") val packageName: String?,
    @SerializedName("notification_id") val notificationId: Int?,
    @SerializedName("tag") val tag: String?,
    @SerializedName("title") val title: String?,
    @SerializedName("text") val body: String?,
    @SerializedName("big_text") val bigText: String?,
    @SerializedName("sub_text") val subText: String?,
    @SerializedName("posted_at") val postedAt: String?,
    @SerializedName("extras") val extras: Map<String, String>?,
)

data class NotificationForwardResponse(
    @SerializedName("status") val status: String? = null,
    @SerializedName("notification_id") val dbId: Long = 0,
    @SerializedName("broadcast") val broadcast: Boolean = false,
)
