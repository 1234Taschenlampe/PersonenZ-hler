package de.personenzaehler.mobile

import android.Manifest
import android.annotation.SuppressLint
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton
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
import androidx.compose.material3.darkColorScheme
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
import androidx.compose.ui.viewinterop.AndroidView
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
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
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
                                scheme = "https",
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
    val dark = isSystemInDarkTheme()
    val colors = if (dark) {
        darkColorScheme(
            primary = Color(0xFF8CD8CB),
            onPrimary = Color(0xFF00382F),
            primaryContainer = Color(0xFF145449),
            secondary = Color(0xFFAFC3DD),
            background = Color(0xFF101718),
            surface = Color(0xFF172021),
            surfaceVariant = Color(0xFF253132),
            error = Color(0xFFFFB4AB),
        )
    } else {
        lightColorScheme(
            primary = Color(0xFF006B5C),
            onPrimary = Color.White,
            primaryContainer = Color(0xFFB6F1E3),
            secondary = Color(0xFF445B74),
            background = Color(0xFFF6F8F8),
            surface = Color.White,
            surfaceVariant = Color(0xFFEAF1F1),
            error = Color(0xFFB3261E),
        )
    }
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
private fun NotificationPermissionRequest() {
    if (Build.VERSION.SDK_INT < 33) return
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) { launcher.launch(Manifest.permission.POST_NOTIFICATIONS) }
}

private enum class Screen(val route: String, val label: String, val icon: ImageVector) {
    Dashboard("dashboard", "Übersicht", Icons.Default.Dashboard),
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
    var moreExpanded by rememberSaveable { mutableStateOf(false) }
    val primaryScreens = listOf(Screen.Dashboard, Screen.History, Screen.Cameras, Screen.Settings)
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("PersonenZähler", fontWeight = FontWeight.SemiBold)
                        Text(
                            text = if (state.connection.restConnected) "Mit Raspberry Pi verbunden" else "Pi nicht erreichbar",
                            style = MaterialTheme.typography.bodySmall,
                            color = if (state.connection.restConnected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = viewModel::testConnection) {
                        Icon(Icons.Default.Refresh, contentDescription = "Daten aktualisieren")
                    }
                    Box {
                        IconButton(onClick = { moreExpanded = true }) {
                            Icon(Icons.Default.MoreVert, contentDescription = "Weitere Bereiche")
                        }
                        DropdownMenu(expanded = moreExpanded, onDismissRequest = { moreExpanded = false }) {
                            listOf(Screen.Events, Screen.System).forEach { screen ->
                                DropdownMenuItem(
                                    text = { Text(screen.label) },
                                    onClick = {
                                        moreExpanded = false
                                        navController.navigate(screen.route) { launchSingleTop = true }
                                    },
                                )
                            }
                        }
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                val backStack by navController.currentBackStackEntryAsState()
                val current = backStack?.destination
                primaryScreens.forEach { screen ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == screen.route } == true,
                        onClick = { navController.navigate(screen.route) { launchSingleTop = true } },
                        icon = { Icon(screen.icon, contentDescription = screen.label) },
                        label = { Text(screen.label, fontSize = 11.sp) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(navController, startDestination = Screen.Dashboard.route, modifier = Modifier.padding(padding)) {
            composable(Screen.Dashboard.route) { DashboardScreen(state) }
            composable(Screen.History.route) { HistoryScreen(state.status) }
            composable(Screen.Cameras.route) { CamerasScreen(state) }
            composable(Screen.Events.route) { EventsScreen(state, viewModel::setFilter) }
            composable(Screen.System.route) { SystemScreen(state.status, state) }
            composable(Screen.Settings.route) { SettingsScreen(state, viewModel) }
        }
    }
}

@Composable
private fun DashboardScreen(state: MobileUiState) {
    val status = state.status
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { StatusBanner(state) }
        item {
            Card(
                shape = RoundedCornerShape(22.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Personen aktuell im Gebäude", style = MaterialTheme.typography.titleMedium)
                    Text(formatInt(status?.counts?.inside), fontSize = 64.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Stand: ${state.connection.lastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "noch keine Daten"}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        item {
            MetricGrid(
                listOf(
                    "Besucher heute" to formatInt(status?.counts?.dailyUnique),
                    "Eintritte" to formatInt(status?.counts?.entered),
                    "Austritte" to formatInt(status?.counts?.exited),
                    "Gesamtdurchfluss" to formatInt(status?.counts?.throughput),
                    "Fehlrichtungen" to formatInt(status?.counts?.wrongWay),
                    "KI-Beschleuniger" to when (status?.hailo?.deviceDetected) {
                        true -> "Verbunden"
                        false -> "Nicht bereit"
                        null -> "Unbekannt"
                    },
                ),
            )
        }
    }
}

@Composable
private fun StatusBanner(state: MobileUiState) {
    val connected = state.connection.restConnected && !state.connection.stale
    val color = if (connected) MaterialTheme.colorScheme.secondaryContainer
                else MaterialTheme.colorScheme.errorContainer
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = color)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                if (connected) "System verbunden" else "Verbindung überprüfen",
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                if (connected) "Die Werte werden vom Raspberry Pi geladen."
                else "Prüfe das WLAN, die Server-IP und den Zugriff in Einstellungen.",
                style = MaterialTheme.typography.bodySmall,
            )
            if (!connected) {
                state.connection.lastError?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun HistoryScreen(status: ServerStatus?) {
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { SectionTitle("Verlauf") }
        item {
            EmptyCard(
                "Der Server liefert derzeit keine echte Zeitreihe. Hier werden deshalb " +
                "keine künstlichen Verlaufskurven aus verschiedenen Momentanwerten dargestellt."
            )
        }
        item {
            MetricGrid(
                listOf(
                    "Aktuell anwesend" to formatInt(status?.counts?.inside),
                    "Eintritte gesamt" to formatInt(status?.counts?.entered),
                    "Austritte gesamt" to formatInt(status?.counts?.exited),
                    "Besucher heute" to formatInt(status?.counts?.dailyUnique),
                )
            )
        }
    }
}

@Composable
private fun CamerasScreen(state: MobileUiState) {
    val cameras = state.status?.cameras.orEmpty()
    var selectedCameraId by rememberSaveable { mutableStateOf<String?>(null) }
    val selectedCamera = cameras.firstOrNull { it.cameraId == selectedCameraId }

    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { SectionTitle("Kameras") }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Videoquelle: ${state.settings.baseUrl}", fontWeight = FontWeight.Bold)
                    Text("REST: ${if (state.connection.restConnected) "verbunden" else "getrennt"} | WebSocket: ${state.connection.webSocketStatus}")
                    Text("Stream: MJPEG, max. 640 x 360, bis 10 FPS pro Kamera")
                    state.connection.lastError?.let { Text("REST-Fehler: $it", color = MaterialTheme.colorScheme.error) }
                }
            }
        }
        if (selectedCamera != null && state.settings.configured) {
            item {
                CameraVideoCard(
                    camera = selectedCamera,
                    settings = state.settings,
                    large = true,
                    onSelect = { selectedCameraId = null },
                )
            }
        }
        if (cameras.isEmpty()) {
            item { EmptyCard("Keine Kameradaten verfuegbar.") }
        }
        items(cameras) { camera ->
            CameraVideoCard(
                camera = camera,
                settings = state.settings,
                large = false,
                onSelect = { selectedCameraId = camera.cameraId },
            )
        }
    }
}

@Composable
private fun CameraVideoCard(
    camera: CameraSnapshot,
    settings: ServerSettings,
    large: Boolean,
    onSelect: () -> Unit,
) {
    val streamUrl = "${settings.baseUrl}/api/v1/video/${camera.cameraId}.mjpg?fps=${if (large) 12 else 8}"
    val containerColor = if (camera.isWarning) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceVariant
    Card(colors = CardDefaults.cardColors(containerColor = containerColor)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text(camera.name ?: camera.cameraId, fontWeight = FontWeight.Bold)
                    Text("${camera.cameraId} | Rolle: ${camera.role ?: "N/A"} | Quelle: ${camera.source ?: "N/A"}")
                }
                OutlinedButton(onClick = onSelect) {
                    Text(if (large) "Schliessen" else "Gross")
                }
            }
            if (settings.configured) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .aspectRatio(16f / 9f)
                        .background(Color.Black)
                        .clickable { onSelect() },
                ) {
                    MjpegPreview(
                        url = streamUrl,
                        label = camera.name ?: camera.cameraId,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            } else {
                EmptyCard("Serveradresse fehlt. Bitte in Einstellungen speichern.")
            }
            Text("Status: ${camera.status ?: "N/A"} | Aufloesung: ${camera.width ?: "N/A"} x ${camera.height ?: "N/A"} | FPS Soll/Ist: ${camera.wantedFps ?: "N/A"} / ${formatDouble(camera.actualFps)}")
            Text("Letzter Frame: ${formatEpochSeconds(camera.lastFrameTime)} | seit ${formatDouble(camera.secondsSinceLastFrame, " s")}")
            Text("Sichtbar: ${formatInt(camera.visible)} | In: ${formatInt(camera.entered)} | Out: ${formatInt(camera.exited)}")
            Text("Verbunden: ${formatDuration(camera.connectedSeconds)} | Reconnects: ${formatInt(camera.reconnectCount)} | Verworfen: ${formatInt(camera.droppedFrames)}")
            camera.lastError?.let { Text("Fehler: $it", color = MaterialTheme.colorScheme.error) }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun MjpegPreview(url: String, label: String, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                )
                webViewClient = WebViewClient()
                settings.javaScriptEnabled = false
                settings.loadWithOverviewMode = true
                settings.useWideViewPort = true
                setBackgroundColor(android.graphics.Color.BLACK)
            }
        },
        update = { webView ->
            if (webView.tag != url) {
                webView.tag = url
                val html = """
                    <!doctype html>
                    <html>
                    <head>
                      <meta name="viewport" content="width=device-width, initial-scale=1.0">
                      <style>
                        html, body { margin:0; padding:0; width:100%; height:100%; background:#000; overflow:hidden; }
                        img { width:100%; height:100%; object-fit:contain; display:block; }
                      </style>
                    </head>
                    <body><img src="$url" alt="$label"></body>
                    </html>
                """.trimIndent()
                webView.loadDataWithBaseURL(url, html, "text/html", "UTF-8", null)
            }
        },
    )
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
                    "WebSocket" to state.connection.webSocketStatus,
                    "Handy-Netz" to listOfNotNull(state.network.transport, state.network.ssid, state.network.ipAddress).joinToString(" ").ifBlank { "N/A" },
                    "Access Point" to (state.network.bssid ?: "N/A"),
                    "Git-Commit" to (status?.version?.gitCommit ?: "N/A"),
                    "Hailo erkannt" to when (status?.hailo?.deviceDetected) { true -> "ja"; false -> "nein"; null -> "N/A" },
                    "Modell geladen" to yesNoNa(status?.runtime?.modelLoaded),
                    "Inferenz aktiv" to yesNoNa(status?.runtime?.inferenceActive),
                    "Inferenz-FPS" to formatDouble(status?.runtime?.inferenceFps),
                    "Hailo-Latenz" to formatDouble(status?.runtime?.hailoLatencyMs, " ms"),
                    "Hailo-Status" to (status?.runtime?.hailoStatus ?: "N/A"),
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
    var offlineWarn by rememberSaveable(state.settings.serverOfflineWarnSeconds) { mutableStateOf(state.settings.serverOfflineWarnSeconds.toString()) }
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
        OutlinedTextField(offlineWarn, { offlineWarn = it.filter(Char::isDigit) }, label = { Text("Offline-Warnung nach Sekunden") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(tempLimit, { tempLimit = it.filter { ch -> ch.isDigit() || ch == '.' } }, label = { Text("Temperaturgrenze C") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(token, { token = it }, label = { Text("Zugriffstoken (mindestens 32 Zeichen)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                val settings = ServerSettings(
                    scheme = "https",
                    host = host,
                    port = port.toIntOrNull() ?: 8766,
                    refreshSeconds = refresh.toIntOrNull() ?: 5,
                    webSocketEnabled = ws,
                    notificationsEnabled = notifications,
                    serverOfflineWarnSeconds = offlineWarn.toIntOrNull() ?: 30,
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
                        scheme = "https"
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
        Text("WebSocket: ${state.connection.webSocketStatus}")
        Text("Endpunkt: ${state.connection.endpoint ?: state.settings.baseUrl}")
        Text("HTTP-Status: ${state.connection.httpStatus ?: "N/A"}")
        Text("Antwortzeit: ${state.connection.responseTimeMs?.let { "$it ms" } ?: "N/A"}")
        Text("Letzter REST-Erfolg: ${state.connection.lastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "N/A"}")
        Text("Letzter WebSocket-Empfang: ${state.connection.webSocketLastSuccessMillis?.let { formatEpochSeconds(it / 1000.0) } ?: "N/A"}")
        Text("Handy-Netz: ${state.network.transport} | verfuegbar=${state.network.available} | validiert=${state.network.validated}")
        Text("SSID: ${state.network.ssid ?: "N/A"} | BSSID: ${state.network.bssid ?: "N/A"}")
        Text("Handy-IP: ${state.network.ipAddress ?: "N/A"}")
        state.connection.lastError?.let { Text("Letzter REST-Fehler: $it", color = MaterialTheme.colorScheme.error) }
        state.connection.webSocketError?.let { Text("Letzter WebSocket-Fehler: $it", color = MaterialTheme.colorScheme.error) }
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
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary)
            Text(value, fontWeight = FontWeight.SemiBold, fontSize = 23.sp)
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
    Card(shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
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

private fun yesNoNa(value: Boolean?): String = when (value) {
    true -> "ja"
    false -> "nein"
    null -> "N/A"
}
