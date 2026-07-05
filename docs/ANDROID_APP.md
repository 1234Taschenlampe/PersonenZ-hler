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

Die API muss direkt im lokalen WLAN auf `0.0.0.0:8766` lauschen. Der User-Service startet sie dauerhaft auf diesem Port:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/visitor-counter-mobile-api-user.service ~/.config/systemd/user/visitor-counter-mobile-api.service
systemctl --user daemon-reload
systemctl --user enable --now visitor-counter-mobile-api.service
```

Danach ist die API im lokalen WLAN erreichbar:

```text
http://<pi-ip-oder-hostname>:8766/api/v1/status
```

Die Android-App nutzt keine feste IP-Adresse. In den Einstellungen koennen `http`, `personenzaehler.local` oder die aktuelle Pi-IP und Port `8766` gespeichert werden. Die App zeigt REST-Status, WebSocket-Status, Endpunkt, HTTP-Code, Antwortzeit, letzte erfolgreiche Aktualisierung und konkrete Fehler getrennt an. Wenn WebSocket nicht verfuegbar ist, bleibt REST-Polling aktiv.

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
