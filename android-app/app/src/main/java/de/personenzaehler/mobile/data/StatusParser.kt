package de.personenzaehler.mobile.data

import org.json.JSONArray
import org.json.JSONObject

object StatusParser {
    fun parseStatus(raw: String): ServerStatus {
        val json = JSONObject(raw)
        return ServerStatus(
            timestamp = json.optDoubleOrNull("timestamp"),
            service = json.optStringOrNull("service"),
            version = parseVersion(json.optJSONObject("version")),
            api = parseApi(json.optJSONObject("api")),
            counts = parseCounts(json.optJSONObject("counts")),
            cameras = parseCameras(json.optJSONArray("cameras")),
            detector = parseDetector(json.optJSONObject("detector")),
            reid = parseReid(json.optJSONObject("reid")),
            hailo = parseHailo(json.optJSONObject("hailo")),
            runtime = parseRuntime(json.optJSONObject("runtime")),
            host = parseHost(json.optJSONObject("host")),
            database = parseDatabase(json.optJSONObject("database")),
        )
    }

    fun parseEvents(raw: String): List<EventItem> {
        val root = JSONObject(raw)
        val events = root.optJSONArray("events") ?: JSONArray()
        return (0 until events.length()).mapNotNull { index ->
            events.optJSONObject(index)?.let { item ->
                EventItem(
                    eventId = item.optLongOrNull("event_id"),
                    time = item.optDoubleOrNull("time"),
                    cameraId = item.optStringOrNull("camera_id"),
                    direction = item.optStringOrNull("direction"),
                    eventType = item.optStringOrNull("event_type"),
                    counted = item.optBooleanOrNull("counted"),
                    uncertain = item.optBooleanOrNull("uncertain"),
                    confidence = item.optDoubleOrNull("confidence"),
                    description = item.optStringOrNull("description"),
                )
            }
        }
    }

    private fun parseVersion(json: JSONObject?) = VersionInfo(
        server = json?.optStringOrNull("server"),
        gitCommit = json?.optStringOrNull("git_commit"),
    )

    private fun parseApi(json: JSONObject?) = ApiInfo(
        name = json?.optStringOrNull("name"),
        version = json?.optStringOrNull("version"),
        pairing = json?.optStringOrNull("pairing"),
        websocket = json?.optStringOrNull("websocket"),
    )

    private fun parseCounts(json: JSONObject?) = CountSnapshot(
        inside = json?.optIntOrNull("inside"),
        entered = json?.optIntOrNull("entered"),
        exited = json?.optIntOrNull("exited"),
        visible = json?.optIntOrNull("visible"),
        suppressed = json?.optIntOrNull("suppressed"),
        uncertain = json?.optIntOrNull("uncertain"),
        lastEventTime = json?.optDoubleOrNull("last_event_time"),
    )

    private fun parseCameras(array: JSONArray?): List<CameraSnapshot> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let { json ->
                CameraSnapshot(
                    cameraId = json.optStringOrNull("camera_id") ?: "kamera-$index",
                    name = json.optStringOrNull("name"),
                    role = json.optStringOrNull("role"),
                    source = json.optStringOrNull("source"),
                    device = json.optStringOrNull("device"),
                    status = json.optStringOrNull("status"),
                    width = json.optIntOrNull("width"),
                    height = json.optIntOrNull("height"),
                    wantedFps = json.optIntOrNull("wanted_fps"),
                    actualFps = json.optDoubleOrNull("actual_fps"),
                    lastFrameTime = json.optDoubleOrNull("last_frame_time"),
                    secondsSinceLastFrame = json.optDoubleOrNull("seconds_since_last_frame"),
                    connectedSeconds = json.optDoubleOrNull("connected_seconds"),
                    reconnectCount = json.optIntOrNull("reconnect_count"),
                    droppedFrames = json.optIntOrNull("dropped_frames"),
                    decodeErrors = json.optIntOrNull("decode_errors"),
                    lastError = json.optStringOrNull("last_error"),
                    visible = json.optIntOrNull("visible"),
                    entered = json.optIntOrNull("entered"),
                    exited = json.optIntOrNull("exited"),
                )
            }
        }
    }

    private fun parseDetector(json: JSONObject?) = DetectorInfo(
        configuredModel = json?.optStringOrNull("configured_model"),
        active = json?.optBooleanOrNull("active"),
        hefExists = json?.optBooleanOrNull("hef_exists"),
        message = json?.optStringOrNull("message"),
        error = json?.optStringOrNull("error"),
    )

    private fun parseReid(json: JSONObject?) = ReIdInfo(
        configuredModel = json?.optStringOrNull("configured_model"),
        ready = json?.optBooleanOrNull("ready"),
        message = json?.optStringOrNull("message"),
    )

    private fun parseHailo(json: JSONObject?) = HailoInfo(
        deviceDetected = json?.optBooleanOrNull("device_detected"),
        architecture = json?.optStringOrNull("architecture"),
        scan = json?.optStringOrNull("scan"),
        identify = json?.optStringOrNull("identify"),
    )

    private fun parseRuntime(json: JSONObject?) = RuntimeInfo(
        activeHef = json?.optStringOrNull("active_hef"),
        hailoInferenceCount = json?.optLongOrNull("hailo_inference_count"),
        inferenceFps = json?.optDoubleOrNull("inference_fps"),
        hailoLatencyMs = json?.optDoubleOrNull("hailo_latency_ms"),
        totalLatencyMs = json?.optDoubleOrNull("total_latency_ms"),
        frameAgeMs = json?.optDoubleOrNull("frame_age_ms"),
        queueLength = json?.optIntOrNull("queue_length"),
        hailoStatus = json?.optStringOrNull("hailo_status"),
    )

    private fun parseHost(json: JSONObject?) = HostTelemetry(
        cpuPercent = json?.optDoubleOrNull("cpu_percent"),
        ramPercent = json?.optDoubleOrNull("ram_percent"),
        swapPercent = json?.optDoubleOrNull("swap_percent"),
        diskFreeBytes = json?.optLongOrNull("disk_free_bytes"),
        loadAverage = json?.optJSONArray("load_average")?.let { array ->
            (0 until array.length()).mapNotNull { array.optDoubleOrNull(it) }
        }.orEmpty(),
        temperatureC = json?.optDoubleOrNull("temperature_c"),
        systemUptimeSeconds = json?.optDoubleOrNull("system_uptime_seconds"),
    )

    private fun parseDatabase(json: JSONObject?) = DatabaseInfo(
        path = json?.optStringOrNull("path"),
        exists = json?.optBooleanOrNull("exists"),
        sizeBytes = json?.optLongOrNull("size_bytes"),
        walSizeBytes = json?.optLongOrNull("wal_size_bytes"),
    )
}

private fun JSONObject.optStringOrNull(name: String): String? =
    if (!has(name) || isNull(name)) null else optString(name).takeIf { it.isNotBlank() }

private fun JSONObject.optIntOrNull(name: String): Int? =
    if (!has(name) || isNull(name)) null else optInt(name)

private fun JSONObject.optLongOrNull(name: String): Long? =
    if (!has(name) || isNull(name)) null else optLong(name)

private fun JSONObject.optDoubleOrNull(name: String): Double? =
    if (!has(name) || isNull(name)) null else optDouble(name).takeIf { !it.isNaN() }

private fun JSONObject.optBooleanOrNull(name: String): Boolean? =
    if (!has(name) || isNull(name)) null else optBoolean(name)

private fun JSONArray.optDoubleOrNull(index: Int): Double? =
    if (isNull(index)) null else optDouble(index).takeIf { !it.isNaN() }
