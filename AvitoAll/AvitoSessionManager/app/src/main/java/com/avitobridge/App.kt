package com.avitobridge

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.avitobridge.data.PrefsManager
import com.topjohnwu.superuser.Shell

class App : Application() {

    lateinit var prefs: PrefsManager
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PrefsManager(this)
        createNotificationChannel()

        // Initialize libsu Shell
        Shell.enableVerboseLogging = true
        Shell.setDefaultBuilder(Shell.Builder.create()
            .setFlags(Shell.FLAG_REDIRECT_STDERR)
            .setTimeout(10)
        )
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Session Monitor",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Monitors Avito session and syncs tokens"
            }

            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    companion object {
        const val CHANNEL_ID = "session_monitor"
        lateinit var instance: App
            private set
    }
}
