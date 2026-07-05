package de.personenzaehler.mobile

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import de.personenzaehler.mobile.data.CameraSnapshot
import de.personenzaehler.mobile.data.EventFilter
import de.personenzaehler.mobile.data.EventItem
import de.personenzaehler.mobile.data.MobileUiState
import de.personenzaehler.mobile.data.ServerSettings
import de.personenzaehler.mobile.data.ServerStatus
import de.personenzaehler.mobile.network.NetworkMonitor
import de.personenzaehler.mobile.network.PiApiClient
import de.personenzaehler.mobile.network.ServerDiscovery
import de.personenzaehler.mobile.notifications.AlertNotifier
import de.personenzaehler.mobile.settings.SecureTokenStore
import de.personenzaehler.mobile.settings.SettingsRepository
import de.personenzaehler.mobile.util.formatBytes
import de.personenzaehler.mobile.util.formatDouble
import de.personenzaehler.mobile.util.formatDuration
import de.personenzaehler.mobile.util.formatEpochSeconds
import de.personenzaehler.mobile.util.formatInt

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val launchIntent = intent
        setContent {
            PersonenzaehlerTheme {
                val context = LocalContext.current
                val tokenStore = remember { SecureTokenStore(context) }
                val viewModel: MainViewModel = viewModel(
                    factory = MainViewModelFactory(
                        settingsRepository = SettingsRepository(context),
                        tokenStore = tokenStore,
                        apiClient = PiApiClient(tokenStore),
                        serverDiscovery = ServerDiscovery(context),
                        networkMonitor = NetworkMonitor(context),
                        notifier = AlertNotifier(context),
                    ),
                )
                val state by viewModel.state.collectAsState()
                LaunchedEffect(Unit) {
                    val host = launchIntent.getStringExtra("server_host")
                    if (!host.isNullOrBlank()) {
                        viewModel.saveSettings(
                            state.settings.copy(
                                scheme = launchIntent.getStringExtra("server_scheme") ?: "http",
                                host = host,
                                port = launchIntent.getIntExtra("server_port", 8766),
                            ),
                        )
                    }
                }
                PersonenzaehlerApp(state, viewModel)
            }
        }
    }
}

@Composable
private fun PersonenzaehlerTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF315F56),
            secondary = Color(0xFFE8B84E),
            tertiary = Color(0xFF5B6C8D),
            error = Color(0xFFB3261E),
        ),
        content = content,
    )
}

@Composable
private fun NotificationPermissionRequest() {
    if (Build.VERSION.SDK_INT < 33) return
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) { launcher.launch(Manifest.permission.POST_NOTIFICATIONS) }
}

private enum class Screen(val route: String, val label: String, val icon: ImageVector) {
    Dashboard("dashboard", "Dashboard", Icons.Default.Dashboard),
    History("history", "Verlauf", Icons.Default.BarChart),
    Cameras("cameras", "Kameras", Icons.Default.CameraAlt),
    Events("events", "Ereignisse", Icons.Default.Event),
    System("system", "System", Icons.Default.Storage),
    Settings("settings", "Einstellungen", Icons.Default.Settings),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PersonenzaehlerApp(state: MobileUiState, viewModel: MainViewModel) {
    val navController = rememberNavController()
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Personenzaehler")
                        Text(
                            text = if (state.connection.restConnected) "REST verbunden" else "REST getrennt",
                            style = MaterialTheme.typography.bodySmall,
                            color = if (state.connection.restConnected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                        )
                    }
                },
                actions = {
                    OutlinedButton(onClick = viewModel::testConnection, modifier = Modifier.padding(end = 8.dp)) {
                        Icon(Icons.Default.Refresh, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Aktualisieren")
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                val backStack by navController.currentBackStackEntryAsState()
                val current = backStack?.destination
                Screen.entries.forEach { screen ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == screen.route } == true,
                        onClick = { navController.navigate(screen.route) { launchSingleTop = true } },
                        icon = { Icon(screen.icon, contentDescription = screen.label) },
                        label = { Text(screen.label, fontSize = 10.sp) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(navController, startDestination = Screen.Dashboard.route, modifier = Modifier.padding(padding)) {
            composable(Screen.Dashboard.route) { DashboardScreen(state) }
            composable(Screen.History.route) { HistoryScreen(state.status) }
            composable(Screen.Cameras.route) { CamerasScreen(state.status?.cameras.orEmpty()) }
            composable(Screen.Events.route) { EventsScreen(state, viewModel::setFilter) }
            composable(Screen.System.route) { SystemScreen(state.status, state) }
            composable(Screen.Settings.route) { SettingsScreen(state, viewModel) }
        }
    }
}

@Composable
private fun DashboardScreen(state: MobileUiState) {
    val status = state.status
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            StatusBanner(state)
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Column(Modifier.padding(18.dp)) {
                    Text("Aktuell anwesend", style = MaterialTheme.typography.titleMedium)
                    Text(formatInt(status?.counts?.inside), fontSize = 56.sp, fontWeight = FontWeight.Bold)
                    Text("Letzte Aktualisierung: ${state.connection.lastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "N/A"}")
                }
            }
        }
        item {
            MetricGrid(
                listOf(
                    "Eintritte gesamt" to formatInt(status?.counts?.entered),
                    "Austritte gesamt" to formatInt(status?.counts?.exited),
                    "Sichtbar global" to formatInt(status?.counts?.visible),
                    "Suppressed" to formatInt(status?.counts?.suppressed),
                    "Uncertain" to formatInt(status?.counts?.uncertain),
                    "Letztes Ereignis" to formatEpochSeconds(status?.counts?.lastEventTime),
                    "App-Laufzeit" to "N/A",
                    "System-Uptime" to formatDuration(status?.host?.systemUptimeSeconds),
                    "Datenbank" to if (status?.database?.exists == true) "OK" else "N/A",
                    "API" to (status?.api?.name ?: "N/A"),
                    "Hailo" to when (status?.hailo?.deviceDetected) { true -> "OK"; false -> "nicht verfuegbar"; null -> "N/A" },
                    "Serverversion" to state.serverVersionText,
                ),
            )
        }
    }
}

@Composable
private fun StatusBanner(state: MobileUiState) {
    val color = when {
        !state.connection.restConnected -> MaterialTheme.colorScheme.errorContainer
        state.connection.stale -> MaterialTheme.colorScheme.tertiaryContainer
        else -> MaterialTheme.colorScheme.secondaryContainer
    }
    Card(colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(14.dp)) {
            Text(if (state.connection.restConnected) "Server verbunden" else "Keine Verbindung zum Server", fontWeight = FontWeight.Bold)
            Text(state.connection.message)
            Text("REST: ${if (state.connection.restConnected) "verbunden" else "getrennt"}")
            Text("WebSocket: ${if (state.connection.webSocketConnected) "verbunden" else "nicht verfuegbar"}")
            Text("Endpunkt: ${state.connection.endpoint ?: state.settings.baseUrl}")
            Text("HTTP: ${state.connection.httpStatus ?: "N/A"} | Antwortzeit: ${state.connection.responseTimeMs?.let { "$it ms" } ?: "N/A"}")
            Text("Letzte Aktualisierung: ${state.connection.lastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "N/A"}")
            Text("Handy-Netz: ${state.network.transport} ${state.network.ssid ?: ""} ${state.network.ipAddress ?: ""}".trim())
            state.network.bssid?.let { Text("Access Point: $it") }
            state.connection.lastError?.let { Text("Fehler: $it", color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun HistoryScreen(status: ServerStatus?) {
    val values = listOfNotNull(
        status?.counts?.inside?.toFloat(),
        status?.counts?.entered?.toFloat(),
        status?.counts?.exited?.toFloat(),
        status?.counts?.visible?.toFloat(),
    )
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { SectionTitle("Verlauf") }
        item {
            Text("Die vorhandene Server-API liefert aktuell Momentaufnahmen, aber noch keine echten Historienreihen. Die App zeigt leere Reihen stabil an und nutzt echte Werte, sobald der Server Historie liefert.")
        }
        item { ChartCard("Personenbestand / Eintritte / Austritte", values) }
        item { ChartCard("CPU-Auslastung", listOfNotNull(status?.host?.cpuPercent?.toFloat()), "%") }
        item { ChartCard("CPU-Temperatur", listOfNotNull(status?.host?.temperatureC?.toFloat()), "C") }
        item { ChartCard("RAM-Auslastung", listOfNotNull(status?.host?.ramPercent?.toFloat()), "%") }
    }
}

@Composable
private fun CamerasScreen(cameras: List<CameraSnapshot>) {
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { SectionTitle("Kameras") }
        if (cameras.isEmpty()) {
            item { EmptyCard("Keine Kameradaten verfuegbar.") }
        }
        items(cameras) { camera ->
            Card(colors = CardDefaults.cardColors(containerColor = if (camera.isWarning) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(camera.name ?: camera.cameraId, fontWeight = FontWeight.Bold)
                    Text("${camera.cameraId} | Rolle: ${camera.role ?: "N/A"} | Quelle: ${camera.source ?: "N/A"}")
                    Text("Status: ${camera.status ?: "N/A"}")
                    Text("Aufloesung: ${camera.width ?: "N/A"} x ${camera.height ?: "N/A"} | FPS Soll/Ist: ${camera.wantedFps ?: "N/A"} / ${formatDouble(camera.actualFps)}")
                    Text("Letzter Frame: ${formatEpochSeconds(camera.lastFrameTime)} | seit ${formatDouble(camera.secondsSinceLastFrame, " s")}")
                    Text("Verbunden: ${formatDuration(camera.connectedSeconds)} | Reconnects: ${formatInt(camera.reconnectCount)}")
                    Text("Verworfen: ${formatInt(camera.droppedFrames)} | Decodefehler: ${formatInt(camera.decodeErrors)}")
                    Text("Sichtbar: ${formatInt(camera.visible)} | In: ${formatInt(camera.entered)} | Out: ${formatInt(camera.exited)}")
                    camera.lastError?.let { Text("Fehler: $it", color = MaterialTheme.colorScheme.error) }
                }
            }
        }
    }
}

@Composable
private fun EventsScreen(state: MobileUiState, onFilter: (EventFilter) -> Unit) {
    val filtered = state.events.filter { event ->
        when (state.selectedFilter) {
            EventFilter.All -> true
            EventFilter.Counts -> event.direction in setOf("in", "out")
            EventFilter.Camera -> event.eventType?.contains("camera", ignoreCase = true) == true
            EventFilter.System -> event.eventType?.contains("system", ignoreCase = true) == true
            EventFilter.Uncertain -> event.uncertain == true
            EventFilter.Suppressed -> event.counted == false
        }
    }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { SectionTitle("Ereignisse") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                EventFilter.entries.take(3).forEach { filter ->
                    AssistChip(onClick = { onFilter(filter) }, label = { Text(filter.label) })
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                EventFilter.entries.drop(3).forEach { filter ->
                    AssistChip(onClick = { onFilter(filter) }, label = { Text(filter.label) })
                }
            }
        }
        if (filtered.isEmpty()) item { EmptyCard("Keine Ereignisse fuer diesen Filter.") }
        items(filtered) { event -> EventRow(event) }
    }
}

@Composable
private fun SystemScreen(status: ServerStatus?, state: MobileUiState) {
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { SectionTitle("System") }
        item {
            MetricGrid(
                listOf(
                    "CPU" to formatDouble(status?.host?.cpuPercent, "%"),
                    "Temperatur" to formatDouble(status?.host?.temperatureC, " C"),
                    "RAM" to formatDouble(status?.host?.ramPercent, "%"),
                    "Swap" to formatDouble(status?.host?.swapPercent, "%"),
                    "Freier Speicher" to formatBytes(status?.host?.diskFreeBytes),
                    "Load Average" to status?.host?.loadAverage?.joinToString(", ") { formatDouble(it) }.orEmpty().ifBlank { "N/A" },
                    "System-Uptime" to formatDuration(status?.host?.systemUptimeSeconds),
                    "DB-Groesse" to formatBytes(status?.database?.sizeBytes),
                    "REST-Status" to if (state.connection.restConnected) "OK" else "Offline",
                    "WebSocket" to if (state.connection.webSocketConnected) "OK" else "nicht verfuegbar",
                    "Handy-Netz" to listOfNotNull(state.network.transport, state.network.ssid, state.network.ipAddress).joinToString(" ").ifBlank { "N/A" },
                    "Access Point" to (state.network.bssid ?: "N/A"),
                    "Git-Commit" to (status?.version?.gitCommit ?: "N/A"),
                    "Hailo erkannt" to when (status?.hailo?.deviceDetected) { true -> "ja"; false -> "nein"; null -> "N/A" },
                    "Modell geladen" to when (status?.detector?.active) { true -> "ja"; false -> "nein"; null -> "N/A" },
                    "Inferenz aktiv" to when (status?.detector?.active) { true -> "ja"; false -> "nein"; null -> "N/A" },
                    "Hailo-Temperatur" to "N/A",
                    "Hailo-Auslastung" to "N/A",
                ),
            )
        }
    }
}

@Composable
private fun SettingsScreen(state: MobileUiState, viewModel: MainViewModel) {
    var host by rememberSaveable(state.settings.host) { mutableStateOf(state.settings.host) }
    var port by rememberSaveable(state.settings.port) { mutableStateOf(state.settings.port.toString()) }
    var scheme by rememberSaveable(state.settings.scheme) { mutableStateOf(state.settings.scheme) }
    var refresh by rememberSaveable(state.settings.refreshSeconds) { mutableStateOf(state.settings.refreshSeconds.toString()) }
    var ws by rememberSaveable(state.settings.webSocketEnabled) { mutableStateOf(state.settings.webSocketEnabled) }
    var notifications by rememberSaveable(state.settings.notificationsEnabled) { mutableStateOf(state.settings.notificationsEnabled) }
    var tempLimit by rememberSaveable(state.settings.temperatureLimitC) { mutableStateOf(state.settings.temperatureLimitC.toString()) }
    var token by rememberSaveable { mutableStateOf("") }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        SectionTitle("Einstellungen")
        OutlinedTextField(host, { host = it }, label = { Text("Serveradresse oder Hostname") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(scheme, { scheme = it.lowercase().take(5) }, label = { Text("Schema") }, modifier = Modifier.weight(1f), singleLine = true)
            OutlinedTextField(port, { port = it.filter(Char::isDigit) }, label = { Text("Port") }, modifier = Modifier.weight(1f), singleLine = true)
        }
        OutlinedTextField(refresh, { refresh = it.filter(Char::isDigit) }, label = { Text("Aktualisierung in Sekunden") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        SettingSwitch("WebSocket aktivieren", ws) { ws = it }
        SettingSwitch("Benachrichtigungen aktivieren", notifications) { notifications = it }
        if (Build.VERSION.SDK_INT >= 33) {
            OutlinedButton(onClick = { notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) }) {
                Text("Benachrichtigungen erlauben")
            }
        }
        OutlinedTextField(tempLimit, { tempLimit = it.filter { ch -> ch.isDigit() || ch == '.' } }, label = { Text("Temperaturgrenze C") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(token, { token = it }, label = { Text("Pairing-Code oder Token (optional)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                val settings = ServerSettings(
                    scheme = if (scheme == "https") "https" else "http",
                    host = host,
                    port = port.toIntOrNull() ?: 8766,
                    refreshSeconds = refresh.toIntOrNull() ?: 5,
                    webSocketEnabled = ws,
                    notificationsEnabled = notifications,
                    temperatureLimitC = tempLimit.toDoubleOrNull() ?: 75.0,
                )
                viewModel.saveSettings(settings)
                if (token.isNotBlank()) viewModel.saveToken(token)
            }) {
                Icon(Icons.Default.Save, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("Speichern")
            }
            OutlinedButton(onClick = viewModel::testConnection) { Text("Verbindung testen") }
        }
        OutlinedButton(onClick = viewModel::discoverServers) {
            Text(if (state.discoveryActive) "Suche laeuft..." else "Server automatisch suchen")
        }
        if (state.discoveredServers.isNotEmpty()) {
            Text("Gefundene Server")
            state.discoveredServers.forEach { server ->
                AssistChip(
                    onClick = {
                        host = server.host
                        port = server.port.toString()
                        scheme = "http"
                        viewModel.useDiscoveredServer(server)
                    },
                    label = { Text("${server.name} | ${server.host}:${server.port}") },
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = viewModel::clearToken) { Text("Token entfernen") }
            OutlinedButton(onClick = viewModel::clearLocalData) { Text("Lokale Daten loeschen") }
        }
        Divider()
        Text("REST: ${if (state.connection.restConnected) "verbunden" else "getrennt"}")
        Text("WebSocket: ${if (state.connection.webSocketConnected) "verbunden" else "nicht verfuegbar"}")
        Text("Endpunkt: ${state.connection.endpoint ?: state.settings.baseUrl}")
        Text("HTTP-Status: ${state.connection.httpStatus ?: "N/A"}")
        Text("Antwortzeit: ${state.connection.responseTimeMs?.let { "$it ms" } ?: "N/A"}")
        Text("Letzte erfolgreiche Aktualisierung: ${state.connection.lastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "N/A"}")
        Text("Handy-Netz: ${state.network.transport} | verfuegbar=${state.network.available} | validiert=${state.network.validated}")
        Text("SSID: ${state.network.ssid ?: "N/A"} | BSSID: ${state.network.bssid ?: "N/A"}")
        Text("Handy-IP: ${state.network.ipAddress ?: "N/A"}")
        state.connection.lastError?.let { Text("Letzter Fehler: $it", color = MaterialTheme.colorScheme.error) }
        Text("App-Version: ${state.appVersionText}")
        Text("Serverversion: ${state.serverVersionText}")
        Text("Pairing: Der aktuelle Server meldet kein vollstaendiges Pairing-Verfahren. Die App speichert optionale Bearer Tokens sicher und sendet sie mit, sobald der Server sie auswertet.")
        Text("Datenschutz: Die App fuehrt keine Bilderkennung aus und speichert keine Bilddaten.")
    }
}

@Composable
private fun SettingSwitch(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Text(label, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun MetricGrid(items: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { (label, value) -> MetricCard(label, value, Modifier.weight(1f)) }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, shape = RoundedCornerShape(8.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(12.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 20.sp)
        }
    }
}

@Composable
private fun ChartCard(title: String, values: List<Float>, unit: String = "") {
    Card {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(if (unit.isBlank()) "Einheit: Personen/Zaehler" else "Einheit: $unit", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(8.dp))
            SimpleLineChart(values)
        }
    }
}

@Composable
private fun SimpleLineChart(values: List<Float>) {
    val lineColor = MaterialTheme.colorScheme.primary
    val axisColor = MaterialTheme.colorScheme.outline
    Canvas(Modifier.fillMaxWidth().height(180.dp)) {
        val left = 34f
        val bottom = size.height - 24f
        drawLine(axisColor, Offset(left, 8f), Offset(left, bottom))
        drawLine(axisColor, Offset(left, bottom), Offset(size.width - 8f, bottom))
        if (values.isEmpty()) return@Canvas
        val max = values.maxOrNull()?.coerceAtLeast(1f) ?: 1f
        val step = (size.width - left - 16f) / (values.size - 1).coerceAtLeast(1)
        values.zipWithNext().forEachIndexed { index, (a, b) ->
            val x1 = left + index * step
            val x2 = left + (index + 1) * step
            val y1 = bottom - (a / max) * (bottom - 8f)
            val y2 = bottom - (b / max) * (bottom - 8f)
            drawLine(lineColor, Offset(x1, y1), Offset(x2, y2), strokeWidth = 4f)
        }
        if (values.size == 1) {
            val y = bottom - (values.first() / max) * (bottom - 8f)
            drawCircle(lineColor, 6f, Offset(left, y))
        }
    }
}

@Composable
private fun EventRow(event: EventItem) {
    Card(shape = RoundedCornerShape(8.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(event.eventType ?: "Ereignis", fontWeight = FontWeight.Bold)
            Text("${formatEpochSeconds(event.time)} | Kamera: ${event.cameraId ?: "N/A"} | Richtung: ${event.direction ?: "N/A"}")
            Text("Konfidenz: ${formatDouble(event.confidence)} | counted=${event.counted ?: "N/A"} | uncertain=${event.uncertain ?: "N/A"}")
            event.description?.let { Text(it) }
        }
    }
}

@Composable
private fun EmptyCard(message: String) {
    Card { Text(message, Modifier.padding(16.dp)) }
}

@Composable
private fun SectionTitle(title: String) {
    Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
}
