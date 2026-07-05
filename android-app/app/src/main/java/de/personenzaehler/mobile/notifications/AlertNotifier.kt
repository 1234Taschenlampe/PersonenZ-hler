package de.personenzaehler.mobile.notifications

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import de.personenzaehler.mobile.R
import de.personenzaehler.mobile.data.ServerSettings
import de.personenzaehler.mobile.data.ServerStatus

class AlertNotifier(private val context: Context) {
    private val lastSent = mutableMapOf<String, Long>()

    init {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Personenzaehler Warnungen", NotificationManager.IMPORTANCE_DEFAULT)
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    fun evaluate(status: ServerStatus?, settings: ServerSettings, serverOnline: Boolean) {
        if (!settings.notificationsEnabled || !canNotify()) return
        if (!serverOnline) {
            notifyOnce("server_offline", "Server nicht erreichbar", "Keine Verbindung zum Raspberry Pi.")
            return
        }
        if (status == null) return
        if (status.hailo.deviceDetected == false) {
            notifyOnce("hailo_missing", "Hailo nicht verfuegbar", "Der Server meldet kein Hailo-Geraet.")
        }
        val temp = status.host.temperatureC
        if (temp != null && temp >= settings.temperatureLimitC) {
            notifyOnce("temp_high", "Temperaturwarnung", "CPU-Temperatur: %.1f C".format(temp))
        }
        val uncertain = status.counts.uncertain
        if (uncertain != null && uncertain >= settings.uncertainWarnLimit) {
            notifyOnce("uncertain_high", "Viele unsichere Ereignisse", "Uncertain-Zaehler: $uncertain")
        }
        status.cameras.filter { it.isWarning }.forEach { camera ->
            notifyOnce("camera_${camera.cameraId}_${camera.status}", "Kamerawarnung", "${camera.name ?: camera.cameraId}: ${camera.status}")
        }
    }

    private fun notifyOnce(key: String, title: String, text: String) {
        val now = System.currentTimeMillis()
        val previous = lastSent[key] ?: 0L
        if (now - previous < COOLDOWN_MILLIS) return
        lastSent[key] = now
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        NotificationManagerCompat.from(context).notify(key.hashCode(), notification)
    }

    private fun canNotify(): Boolean {
        return Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }

    private companion object {
        const val CHANNEL_ID = "personenzaehler_alerts"
        const val COOLDOWN_MILLIS = 15 * 60 * 1000L
    }
}
