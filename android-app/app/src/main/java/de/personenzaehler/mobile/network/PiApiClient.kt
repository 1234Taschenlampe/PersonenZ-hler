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

data class RestResponse<T>(
    val value: T,
    val endpoint: String,
    val httpStatus: Int,
    val responseTimeMs: Long,
)

enum class LiveSocketState(val label: String) {
    Connected("verbunden"),
    Unavailable("nicht verfuegbar"),
    Disconnected("getrennt"),
}

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
        fetchStatusWithMeta(settings).value
    }

    suspend fun fetchStatusWithMeta(settings: ServerSettings): RestResponse<ServerStatus> = withContext(Dispatchers.IO) {
        ensureAllowed(settings)
        val primary = runCatching { get(settings, "/api/v1/status") }
        val response = primary.getOrElse { get(settings, "/status") }
        RestResponse(
            value = StatusParser.parseStatus(response.body),
            endpoint = response.endpoint,
            httpStatus = response.httpStatus,
            responseTimeMs = response.responseTimeMs,
        )
    }

    suspend fun fetchEvents(settings: ServerSettings, limit: Int = 100): List<EventItem> = withContext(Dispatchers.IO) {
        ensureAllowed(settings)
        val response = get(settings, "/api/v1/events?limit=${limit.coerceIn(1, 200)}")
        StatusParser.parseEvents(response.body)
    }

    fun openLiveSocket(
        settings: ServerSettings,
        onStatus: (ServerStatus) -> Unit,
        onState: (LiveSocketState, String?) -> Unit,
    ): WebSocket? {
        if (!settings.webSocketEnabled || !settings.configured || !HostValidator.isAllowed(settings.scheme, settings.host)) return null
        if (tokenStore.readToken().isNullOrBlank()) return null
        val wsScheme = "wss"
        val request = requestBuilder("$wsScheme://${settings.host.trim()}:${settings.port}/api/v1/ws/live").build()
        return client.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    onState(LiveSocketState.Connected, null)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    runCatching { StatusParser.parseStatus(text) }
                        .onSuccess(onStatus)
                        .onFailure { onState(LiveSocketState.Disconnected, it.message ?: "WebSocket-Daten unlesbar") }
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    onState(LiveSocketState.Disconnected, reason.ifBlank { "WebSocket geschlossen" })
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    val status = response?.code
                    val state = if (status == 404 || status == 426) LiveSocketState.Unavailable else LiveSocketState.Disconnected
                    val message = when {
                        status != null -> "HTTP $status: ${response.message.ifBlank { t.message ?: "WebSocket fehlgeschlagen" }}"
                        else -> t.message ?: "WebSocket nicht verfuegbar"
                    }
                    onState(state, message)
                }
            },
        )
    }

    private fun ensureAllowed(settings: ServerSettings) {
        if (!settings.configured) error("Kein Server konfiguriert")
        if (!HostValidator.isAllowed(settings.scheme, settings.host)) {
            error("Nur HTTPS zu einem lokalen/privaten Server ist erlaubt")
        }
        if (tokenStore.readToken().isNullOrBlank()) error("Zugriffstoken fehlt")
    }

    private data class RawResponse(
        val body: String,
        val endpoint: String,
        val httpStatus: Int,
        val responseTimeMs: Long,
    )

    private fun get(settings: ServerSettings, path: String): RawResponse {
        val endpoint = settings.baseUrl + path
        val request = requestBuilder(endpoint).build()
        val started = System.nanoTime()
        client.newCall(request).execute().use { response ->
            val elapsed = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started).coerceAtLeast(0)
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code} von $endpoint")
            }
            if (body.isBlank()) throw IOException("Leere Serverantwort")
            return RawResponse(
                body = body,
                endpoint = endpoint,
                httpStatus = response.code,
                responseTimeMs = elapsed,
            )
        }
    }

    private fun requestBuilder(url: String): Request.Builder {
        val builder = Request.Builder().url(url)
        val token = tokenStore.readToken() ?: error("Zugriffstoken fehlt")
        builder.header("Authorization", "Bearer $token")
        return builder
    }
}
