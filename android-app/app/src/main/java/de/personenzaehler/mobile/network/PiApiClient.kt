package de.personenzaehler.mobile.network

import de.personenzaehler.mobile.data.EventItem
import de.personenzaehler.mobile.data.ServerSettings
import de.personenzaehler.mobile.data.ServerStatus
import de.personenzaehler.mobile.data.StatusParser
import de.personenzaehler.mobile.settings.SecureTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.io.IOException
import java.util.concurrent.TimeUnit

class PiApiClient(
    private val tokenStore: SecureTokenStore,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .writeTimeout(8, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build(),
) {
    suspend fun fetchStatus(settings: ServerSettings): ServerStatus = withContext(Dispatchers.IO) {
        ensureAllowed(settings)
        val primary = runCatching { get(settings, "/api/v1/status") }
        val body = primary.getOrElse { get(settings, "/status") }
        StatusParser.parseStatus(body)
    }

    suspend fun fetchEvents(settings: ServerSettings, limit: Int = 100): List<EventItem> = withContext(Dispatchers.IO) {
        ensureAllowed(settings)
        val body = get(settings, "/api/v1/events?limit=${limit.coerceIn(1, 200)}")
        StatusParser.parseEvents(body)
    }

    fun openLiveSocket(
        settings: ServerSettings,
        onStatus: (ServerStatus) -> Unit,
        onState: (Boolean, String?) -> Unit,
    ): WebSocket? {
        if (!settings.webSocketEnabled || !settings.configured || !HostValidator.isAllowed(settings.scheme, settings.host)) return null
        val wsScheme = if (settings.scheme == "https") "wss" else "ws"
        val request = requestBuilder("$wsScheme://${settings.host.trim()}:${settings.port}/api/v1/ws/live").build()
        return client.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    onState(true, null)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    runCatching { StatusParser.parseStatus(text) }.onSuccess(onStatus)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    onState(false, reason.ifBlank { "WebSocket geschlossen" })
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    onState(false, t.message ?: "WebSocket nicht verfuegbar")
                }
            },
        )
    }

    private fun ensureAllowed(settings: ServerSettings) {
        if (!settings.configured) error("Kein Server konfiguriert")
        if (!HostValidator.isAllowed(settings.scheme, settings.host)) {
            error("HTTP ist nur fuer lokale/private Server erlaubt")
        }
    }

    private fun get(settings: ServerSettings, path: String): String {
        val request = requestBuilder(settings.baseUrl + path).build()
        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (body.isBlank()) throw IOException("Leere Serverantwort")
            return body
        }
    }

    private fun requestBuilder(url: String): Request.Builder {
        val builder = Request.Builder().url(url)
        tokenStore.readToken()?.let { token -> builder.header("Authorization", "Bearer $token") }
        return builder
    }
}
