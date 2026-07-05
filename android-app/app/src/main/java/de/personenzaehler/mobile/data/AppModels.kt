package de.personenzaehler.mobile.data

data class ServerSettings(
    val scheme: String = "http",
    val host: String = "",
    val port: Int = 8766,
    val refreshSeconds: Int = 5,
    val webSocketEnabled: Boolean = true,
    val notificationsEnabled: Boolean = true,
    val serverOfflineWarnSeconds: Int = 30,
    val temperatureLimitC: Double = 75.0,
    val cameraOfflineWarnSeconds: Int = 60,
    val uncertainWarnLimit: Int = 5,
) {
    val configured: Boolean get() = host.isNotBlank()
    val baseUrl: String get() = "$scheme://${host.trim()}:$port"
}

data class ServerStatus(
    val timestamp: Double?,
    val service: String?,
    val version: VersionInfo,
    val api: ApiInfo,
    val counts: CountSnapshot,
    val cameras: List<CameraSnapshot>,
    val detector: DetectorInfo,
    val reid: ReIdInfo,
    val hailo: HailoInfo,
    val runtime: RuntimeInfo,
    val host: HostTelemetry,
    val database: DatabaseInfo,
)

data class VersionInfo(
    val server: String?,
    val gitCommit: String?,
)

data class ApiInfo(
    val name: String?,
    val version: String?,
    val pairing: String?,
    val websocket: String?,
)

data class CountSnapshot(
    val inside: Int?,
    val entered: Int?,
    val exited: Int?,
    val visible: Int?,
    val suppressed: Int?,
    val uncertain: Int?,
    val lastEventTime: Double?,
)

data class CameraSnapshot(
    val cameraId: String,
    val name: String?,
    val role: String?,
    val source: String?,
    val device: String?,
    val status: String?,
    val width: Int?,
    val height: Int?,
    val wantedFps: Int?,
    val actualFps: Double?,
    val lastFrameTime: Double?,
    val secondsSinceLastFrame: Double?,
    val connectedSeconds: Double?,
    val reconnectCount: Int?,
    val droppedFrames: Int?,
    val decodeErrors: Int?,
    val lastError: String?,
    val visible: Int?,
    val entered: Int?,
    val exited: Int?,
) {
    val isWarning: Boolean
        get() = status in setOf("DEGRADED", "STALLED", "RECONNECTING", "OFFLINE")
}

data class DetectorInfo(
    val configuredModel: String?,
    val active: Boolean?,
    val hefExists: Boolean?,
    val message: String?,
    val error: String?,
)

data class ReIdInfo(
    val configuredModel: String?,
    val ready: Boolean?,
    val message: String?,
)

data class HailoInfo(
    val deviceDetected: Boolean?,
    val architecture: String?,
    val scan: String?,
    val identify: String?,
)

data class RuntimeInfo(
    val activeHef: String?,
    val hailoInferenceCount: Long?,
    val inferenceFps: Double?,
    val hailoLatencyMs: Double?,
    val totalLatencyMs: Double?,
    val frameAgeMs: Double?,
    val queueLength: Int?,
    val hailoStatus: String?,
) {
    val modelLoaded: Boolean?
        get() = activeHef?.takeIf { it.isNotBlank() }?.let { true }

    val inferenceActive: Boolean?
        get() = inferenceFps?.let { it > 0.0 } ?: hailoInferenceCount?.let { it > 0L }
}

data class HostTelemetry(
    val cpuPercent: Double?,
    val ramPercent: Double?,
    val swapPercent: Double?,
    val diskFreeBytes: Long?,
    val loadAverage: List<Double>,
    val temperatureC: Double?,
    val systemUptimeSeconds: Double?,
)

data class DatabaseInfo(
    val path: String?,
    val exists: Boolean?,
    val sizeBytes: Long?,
    val walSizeBytes: Long?,
)

data class EventItem(
    val eventId: Long?,
    val time: Double?,
    val cameraId: String?,
    val direction: String?,
    val eventType: String?,
    val counted: Boolean?,
    val uncertain: Boolean?,
    val confidence: Double?,
    val description: String?,
)

enum class EventFilter(val label: String) {
    All("Alle"),
    Counts("Zaehlereignisse"),
    Camera("Kamerafehler"),
    System("Systemwarnungen"),
    Uncertain("Uncertain"),
    Suppressed("Suppressed"),
}

data class ConnectionState(
    val online: Boolean = false,
    val restConnected: Boolean = false,
    val stale: Boolean = false,
    val message: String = "REST noch nicht verbunden",
    val lastSuccessMillis: Long? = null,
    val webSocketConnected: Boolean = false,
    val webSocketStatus: String = "getrennt",
    val webSocketLastSuccessMillis: Long? = null,
    val endpoint: String? = null,
    val httpStatus: Int? = null,
    val responseTimeMs: Long? = null,
    val lastError: String? = null,
    val webSocketError: String? = null,
)

data class DeviceNetworkState(
    val available: Boolean = false,
    val validated: Boolean = false,
    val transport: String = "N/A",
    val ssid: String? = null,
    val bssid: String? = null,
    val ipAddress: String? = null,
    val lastChangedMillis: Long? = null,
)

data class DiscoveredServerInfo(
    val name: String,
    val host: String,
    val port: Int,
)

data class MobileUiState(
    val settings: ServerSettings = ServerSettings(),
    val status: ServerStatus? = null,
    val events: List<EventItem> = emptyList(),
    val connection: ConnectionState = ConnectionState(),
    val network: DeviceNetworkState = DeviceNetworkState(),
    val selectedFilter: EventFilter = EventFilter.All,
    val discoveredServers: List<DiscoveredServerInfo> = emptyList(),
    val discoveryActive: Boolean = false,
    val serverVersionText: String = "N/A",
    val appVersionText: String = "0.1.0",
    val busy: Boolean = false,
)
