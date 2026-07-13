package de.personenzaehler.mobile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import de.personenzaehler.mobile.data.DiscoveredServerInfo
import de.personenzaehler.mobile.data.EventFilter
import de.personenzaehler.mobile.data.MobileUiState
import de.personenzaehler.mobile.data.ServerSettings
import de.personenzaehler.mobile.data.ServerStatus
import de.personenzaehler.mobile.network.LiveSocketState
import de.personenzaehler.mobile.network.NetworkMonitor
import de.personenzaehler.mobile.network.PiApiClient
import de.personenzaehler.mobile.network.ReconnectBackoff
import de.personenzaehler.mobile.network.RestResponse
import de.personenzaehler.mobile.network.ServerDiscovery
import de.personenzaehler.mobile.notifications.AlertNotifier
import de.personenzaehler.mobile.settings.SecureTokenStore
import de.personenzaehler.mobile.settings.SettingsRepository
import de.personenzaehler.mobile.util.isStale
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.WebSocket

class MainViewModel(
    private val settingsRepository: SettingsRepository,
    private val tokenStore: SecureTokenStore,
    private val apiClient: PiApiClient,
    private val serverDiscovery: ServerDiscovery,
    private val networkMonitor: NetworkMonitor,
    private val notifier: AlertNotifier,
) : ViewModel() {
    private val _state = MutableStateFlow(MobileUiState())
    val state: StateFlow<MobileUiState> = _state.asStateFlow()

    private val backoff = ReconnectBackoff()
    private var pollJob: Job? = null
    private var discoveryJob: Job? = null
    private var reconnectJob: Job? = null
    private var webSocket: WebSocket? = null
    private var consecutiveFailures = 0

    init {
        viewModelScope.launch {
            settingsRepository.settings.collectLatest { settings ->
                _state.update { it.copy(settings = settings) }
                restartPolling(settings)
            }
        }
        viewModelScope.launch {
            networkMonitor.states().collectLatest { network ->
                _state.update { it.copy(network = network) }
                val settings = _state.value.settings
                if (network.available && settings.configured) {
                    reconnectJob?.cancel()
                    reconnectJob = launch {
                        delay(400L)
                        reconnectNow(settings)
                    }
                } else if (!network.available) {
                    _state.update {
                        it.copy(
                            connection = it.connection.copy(
                                stale = true,
                                message = "WLAN kurz weg, warte auf Wiederverbindung",
                                lastError = "Android meldet kein nutzbares Netzwerk",
                            ),
                        )
                    }
                }
            }
        }
    }

    fun saveSettings(settings: ServerSettings) {
        _state.update { it.copy(settings = settings) }
        restartPolling(settings)
        viewModelScope.launch { settingsRepository.save(settings) }
    }

    fun saveToken(token: String) {
        if (token.trim().length < 32) {
            _state.update {
                it.copy(connection = it.connection.copy(lastError = "Token muss mindestens 32 Zeichen lang sein"))
            }
            return
        }
        tokenStore.saveToken(token)
    }

    fun clearToken() {
        tokenStore.clearToken()
    }

    fun clearLocalData() {
        viewModelScope.launch {
            tokenStore.clearToken()
            settingsRepository.clear()
            _state.value = MobileUiState()
        }
    }

    fun testConnection() {
        viewModelScope.launch { fetchOnce(_state.value.settings, manual = true) }
    }

    fun discoverServers() {
        discoveryJob?.cancel()
        discoveryJob = viewModelScope.launch {
            _state.update { it.copy(discoveredServers = emptyList(), discoveryActive = true) }
            withTimeoutOrNull(6_000L) {
                serverDiscovery.discover().collect { server ->
                    val info = DiscoveredServerInfo(server.name, server.host, server.port)
                    _state.update { state ->
                        if (state.discoveredServers.any { it.host == info.host && it.port == info.port }) {
                            state
                        } else {
                            state.copy(discoveredServers = state.discoveredServers + info)
                        }
                    }
                }
            }
            _state.update { it.copy(discoveryActive = false) }
        }
    }

    fun useDiscoveredServer(server: DiscoveredServerInfo) {
        val port = server.port.takeIf { it in 1..65_535 } ?: 8766
        saveSettings(_state.value.settings.copy(scheme = "https", host = server.host, port = port))
    }

    fun setFilter(filter: EventFilter) {
        _state.update { it.copy(selectedFilter = filter) }
    }

    private fun restartPolling(settings: ServerSettings) {
        pollJob?.cancel()
        webSocket?.cancel()
        if (!settings.configured) return
        if (settings.webSocketEnabled) openWebSocket(settings)
        pollJob = viewModelScope.launch {
            while (true) {
                fetchOnce(settings, manual = false)
                val stale = isStale(
                    _state.value.connection.lastSuccessMillis,
                    System.currentTimeMillis(),
                    settings.refreshSeconds.coerceAtLeast(1) * 3_000L,
                )
                _state.update { state -> state.copy(connection = state.connection.copy(stale = stale)) }
                val pollSeconds = if (_state.value.connection.webSocketConnected) {
                    settings.refreshSeconds.coerceIn(5, 60)
                } else {
                    1
                }
                delay(pollSeconds * 1000L)
            }
        }
    }

    private suspend fun reconnectNow(settings: ServerSettings) {
        webSocket?.cancel()
        if (settings.webSocketEnabled) openWebSocket(settings)
        fetchOnce(settings, manual = false)
    }

    private fun openWebSocket(settings: ServerSettings) {
        webSocket = apiClient.openLiveSocket(
            settings,
            onStatus = { status -> applyWebSocketStatus(status) },
            onState = { socketState, message ->
                _state.update { state ->
                    state.copy(
                        connection = state.connection.copy(
                            webSocketConnected = socketState == LiveSocketState.Connected,
                            webSocketStatus = socketState.label,
                            webSocketError = if (socketState == LiveSocketState.Connected) null else message,
                        ),
                    )
                }
            },
        )
    }

    private suspend fun fetchOnce(settings: ServerSettings, manual: Boolean) {
        if (!settings.configured) {
            _state.update {
                it.copy(
                    connection = it.connection.copy(
                        online = false,
                        restConnected = false,
                        message = "Kein Server konfiguriert",
                        lastError = "Kein Server konfiguriert",
                    ),
                )
            }
            return
        }
        _state.update { it.copy(busy = manual) }
        runCatching {
            val response = apiClient.fetchStatusWithMeta(settings)
            val events = runCatching { apiClient.fetchEvents(settings, 100) }.getOrDefault(emptyList())
            response to events
        }.onSuccess { (response, events) ->
            consecutiveFailures = 0
            backoff.reset()
            applyRestStatus(response, "REST verbunden", webSocketConnected = _state.value.connection.webSocketConnected)
            _state.update { it.copy(events = events, busy = false) }
            notifier.evaluate(response.value, settings, serverOnline = true)
        }.onFailure { throwable ->
            consecutiveFailures += 1
            val delayMillis = backoff.nextDelayMillis()
            val lastSuccess = _state.value.connection.lastSuccessMillis
            val now = System.currentTimeMillis()
            val graceMillis = maxOf(30_000L, settings.refreshSeconds.coerceAtLeast(1) * 4_000L)
            val recentlyHealthy = lastSuccess != null && now - lastSuccess <= graceMillis
            val hardOffline = manual || !recentlyHealthy || consecutiveFailures >= 3
            val error = throwable.message ?: "Keine Verbindung zum Server"
            _state.update {
                it.copy(
                    busy = false,
                    connection = it.connection.copy(
                        online = if (hardOffline) false else it.connection.online,
                        restConnected = if (hardOffline) false else it.connection.restConnected,
                        stale = true,
                        message = if (hardOffline) "Keine Verbindung zum Server" else "REST kurz unterbrochen, verbinde neu",
                        webSocketConnected = false,
                        webSocketStatus = "getrennt",
                        lastError = error,
                    ),
                )
            }
            notifier.evaluate(_state.value.status, settings, serverOnline = false)
            if (!manual) delay(delayMillis)
        }
    }

    private fun applyStatus(status: ServerStatus, message: String, webSocketConnected: Boolean) {
        val now = System.currentTimeMillis()
        _state.update {
            it.copy(
                status = status,
                serverVersionText = listOfNotNull(status.version.server, status.version.gitCommit).joinToString(" ").ifBlank { "N/A" },
                connection = it.connection.copy(
                    online = true,
                    stale = false,
                    message = message,
                    lastSuccessMillis = now,
                    webSocketConnected = webSocketConnected,
                ),
            )
        }
    }

    private fun applyRestStatus(response: RestResponse<ServerStatus>, message: String, webSocketConnected: Boolean) {
        applyStatus(response.value, message, webSocketConnected)
        _state.update {
            it.copy(
                connection = it.connection.copy(
                    restConnected = true,
                    endpoint = response.endpoint,
                    httpStatus = response.httpStatus,
                    responseTimeMs = response.responseTimeMs,
                    lastError = null,
                ),
            )
        }
    }

    private fun applyWebSocketStatus(status: ServerStatus) {
        val now = System.currentTimeMillis()
        _state.update {
            it.copy(
                status = status,
                serverVersionText = listOfNotNull(status.version.server, status.version.gitCommit).joinToString(" ").ifBlank { "N/A" },
                connection = it.connection.copy(
                    webSocketConnected = true,
                    webSocketStatus = LiveSocketState.Connected.label,
                    webSocketLastSuccessMillis = now,
                    webSocketError = null,
                ),
            )
        }
    }

    override fun onCleared() {
        discoveryJob?.cancel()
        reconnectJob?.cancel()
        webSocket?.cancel()
        super.onCleared()
    }
}

class MainViewModelFactory(
    private val settingsRepository: SettingsRepository,
    private val tokenStore: SecureTokenStore,
    private val apiClient: PiApiClient,
    private val serverDiscovery: ServerDiscovery,
    private val networkMonitor: NetworkMonitor,
    private val notifier: AlertNotifier,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return MainViewModel(settingsRepository, tokenStore, apiClient, serverDiscovery, networkMonitor, notifier) as T
    }
}
