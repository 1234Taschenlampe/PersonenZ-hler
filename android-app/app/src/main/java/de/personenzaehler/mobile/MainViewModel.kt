package de.personenzaehler.mobile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import de.personenzaehler.mobile.data.EventFilter
import de.personenzaehler.mobile.data.MobileUiState
import de.personenzaehler.mobile.data.ServerSettings
import de.personenzaehler.mobile.data.ServerStatus
import de.personenzaehler.mobile.network.PiApiClient
import de.personenzaehler.mobile.network.ReconnectBackoff
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
import okhttp3.WebSocket

class MainViewModel(
    private val settingsRepository: SettingsRepository,
    private val tokenStore: SecureTokenStore,
    private val apiClient: PiApiClient,
    private val notifier: AlertNotifier,
) : ViewModel() {
    private val _state = MutableStateFlow(MobileUiState())
    val state: StateFlow<MobileUiState> = _state.asStateFlow()

    private val backoff = ReconnectBackoff()
    private var pollJob: Job? = null
    private var webSocket: WebSocket? = null

    init {
        viewModelScope.launch {
            settingsRepository.settings.collectLatest { settings ->
                _state.update { it.copy(settings = settings) }
                restartPolling(settings)
            }
        }
    }

    fun saveSettings(settings: ServerSettings) {
        viewModelScope.launch { settingsRepository.save(settings) }
    }

    fun saveToken(token: String) {
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
                delay(settings.refreshSeconds.coerceAtLeast(1) * 1000L)
            }
        }
    }

    private fun openWebSocket(settings: ServerSettings) {
        webSocket = apiClient.openLiveSocket(
            settings,
            onStatus = { status -> applyStatus(status, "Live verbunden", webSocketConnected = true) },
            onState = { connected, message ->
                _state.update { state ->
                    state.copy(connection = state.connection.copy(webSocketConnected = connected, message = message ?: state.connection.message))
                }
            },
        )
    }

    private suspend fun fetchOnce(settings: ServerSettings, manual: Boolean) {
        if (!settings.configured) {
            _state.update { it.copy(connection = it.connection.copy(online = false, message = "Kein Server konfiguriert")) }
            return
        }
        _state.update { it.copy(busy = manual) }
        runCatching {
            val status = apiClient.fetchStatus(settings)
            val events = runCatching { apiClient.fetchEvents(settings, 100) }.getOrDefault(emptyList())
            status to events
        }.onSuccess { (status, events) ->
            backoff.reset()
            applyStatus(status, "Verbunden", webSocketConnected = _state.value.connection.webSocketConnected)
            _state.update { it.copy(events = events, busy = false) }
            notifier.evaluate(status, settings, serverOnline = true)
        }.onFailure { throwable ->
            val delayMillis = backoff.nextDelayMillis()
            _state.update {
                it.copy(
                    busy = false,
                    connection = it.connection.copy(
                        online = false,
                        stale = true,
                        message = throwable.message ?: "Keine Verbindung zum Server",
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

    override fun onCleared() {
        webSocket?.cancel()
        super.onCleared()
    }
}

class MainViewModelFactory(
    private val settingsRepository: SettingsRepository,
    private val tokenStore: SecureTokenStore,
    private val apiClient: PiApiClient,
    private val notifier: AlertNotifier,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return MainViewModel(settingsRepository, tokenStore, apiClient, notifier) as T
    }
}
