package com.avitobridge.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.avitobridge.App

/**
 * Starts the session monitor service on device boot
 */
class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i(TAG, "Boot completed, checking if should start service")

            val prefs = App.instance.prefs
            if (prefs.autoSyncEnabled) {
                Log.i(TAG, "Auto-sync enabled, starting service")
                startService(context)
            } else {
                Log.i(TAG, "Auto-sync disabled, not starting service")
            }
        }
    }

    private fun startService(context: Context) {
        val serviceIntent = Intent(context, SessionMonitorService::class.java).apply {
            action = SessionMonitorService.ACTION_START
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
