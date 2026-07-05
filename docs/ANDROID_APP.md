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

Wenn der vorhandene Systemdienst noch auf `127.0.0.1:8765` gebunden ist und kein sudo zur Verfuegung steht, kann der User-Service fuer die App genutzt werden:

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
