# Android-App

Die Handy-App liegt im Ordner `android-app` und nutzt das Paket `de.personenzaehler.mobile`.

## Server

Die App spricht mit der lokalen Status-API des Raspberry Pi:

```text
GET /api/v1/status
GET /api/v1/health
GET /api/v1/version
GET /api/v1/counts/current
GET /api/v1/telemetry/current
GET /api/v1/cameras
GET /api/v1/events
```

Die API bleibt standardmaessig auf `127.0.0.1:8766`. Fuer mobilen Zugriff sind ein lokaler HTTPS-Hostname, ein vom Android-Geraet vertrautes Zertifikat, drei Rollentokens und eine private Bind-Adresse erforderlich. Ohne TLS verweigert der Server eine Nicht-Loopback-Bindung. Siehe `PRIVACY_AND_SECURITY.md`.

```bash
mkdir -p ~/.config/systemd/user
cp systemd/visitor-counter-mobile-api-user.service ~/.config/systemd/user/visitor-counter-mobile-api.service
systemctl --user daemon-reload
systemctl --user enable --now visitor-counter-mobile-api.service
```

Danach ist die API im lokalen WLAN erreichbar:

```text
https://<pi-hostname>:8766/api/v1/status
```

Die Android-App nutzt keine feste IP-Adresse, akzeptiert aber ausschliesslich HTTPS zu lokalen/privaten Zielen und verlangt ein Zugriffstoken. Klartextverkehr und Screenshots sind gesperrt. Wenn WebSocket nicht verfuegbar ist, bleibt authentifiziertes REST-Polling aktiv.

Fuer WLAN-Roaming beobachtet die App das Android-Default-Netzwerk. Nach einem Access-Point- oder IP-Wechsel startet sie die REST-Verbindung automatisch neu. Einzelne verlorene Requests werden als kurze Unterbrechung angezeigt; erst mehrere Fehlschlaege oder laengere Funkstille setzen REST wirklich auf getrennt. In Dashboard und Einstellungen werden Handy-Netz, IP und Access Point angezeigt.

## Build

```powershell
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
gradle testDebugUnitTest assembleDebug
```

APK:

```text
android-app\app\build\outputs\apk\debug\app-debug.apk
```

## Teststart mit ADB

```powershell
adb install -r android-app\app\build\outputs\apk\debug\app-debug.apk
adb shell am start -n de.personenzaehler.mobile/.MainActivity --es server_host <pi-ip-oder-hostname> --ei server_port 8766
```

Die App speichert diese Werte als normale Einstellungen. Es ist keine IP-Adresse fest im Quellcode hinterlegt.
