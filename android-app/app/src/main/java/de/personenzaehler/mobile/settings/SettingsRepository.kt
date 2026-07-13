package de.personenzaehler.mobile.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import de.personenzaehler.mobile.data.ServerSettings
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore(name = "server_settings")

class SettingsRepository(context: Context) {
    private val store = context.settingsStore

    val settings: Flow<ServerSettings> = store.data.map { prefs ->
        ServerSettings(
            scheme = prefs[Keys.Scheme] ?: "https",
            host = prefs[Keys.Host] ?: "",
            port = prefs[Keys.Port] ?: 8766,
            refreshSeconds = prefs[Keys.RefreshSeconds] ?: 5,
            webSocketEnabled = prefs[Keys.WebSocketEnabled] ?: true,
            notificationsEnabled = prefs[Keys.NotificationsEnabled] ?: true,
            serverOfflineWarnSeconds = prefs[Keys.ServerOfflineWarnSeconds] ?: 30,
            temperatureLimitC = prefs[Keys.TemperatureLimitC] ?: 75.0,
            cameraOfflineWarnSeconds = prefs[Keys.CameraOfflineWarnSeconds] ?: 60,
            uncertainWarnLimit = prefs[Keys.UncertainWarnLimit] ?: 5,
        )
    }

    suspend fun save(settings: ServerSettings) {
        store.edit { prefs ->
            prefs[Keys.Scheme] = "https"
            prefs[Keys.Host] = settings.host.trim()
            prefs[Keys.Port] = settings.port.coerceIn(1, 65_535)
            prefs[Keys.RefreshSeconds] = settings.refreshSeconds.coerceIn(1, 300)
            prefs[Keys.WebSocketEnabled] = settings.webSocketEnabled
            prefs[Keys.NotificationsEnabled] = settings.notificationsEnabled
            prefs[Keys.ServerOfflineWarnSeconds] = settings.serverOfflineWarnSeconds.coerceIn(5, 3600)
            prefs[Keys.TemperatureLimitC] = settings.temperatureLimitC
            prefs[Keys.CameraOfflineWarnSeconds] = settings.cameraOfflineWarnSeconds.coerceAtLeast(5)
            prefs[Keys.UncertainWarnLimit] = settings.uncertainWarnLimit.coerceAtLeast(1)
        }
    }

    suspend fun clear() {
        store.edit { it.clear() }
    }

    private object Keys {
        val Scheme = stringPreferencesKey("scheme")
        val Host = stringPreferencesKey("host")
        val Port = intPreferencesKey("port")
        val RefreshSeconds = intPreferencesKey("refresh_seconds")
        val WebSocketEnabled = booleanPreferencesKey("websocket_enabled")
        val NotificationsEnabled = booleanPreferencesKey("notifications_enabled")
        val ServerOfflineWarnSeconds = intPreferencesKey("server_offline_warn_seconds")
        val TemperatureLimitC = doublePreferencesKey("temperature_limit_c")
        val CameraOfflineWarnSeconds = intPreferencesKey("camera_offline_warn_seconds")
        val UncertainWarnLimit = intPreferencesKey("uncertain_warn_limit")
    }
}
