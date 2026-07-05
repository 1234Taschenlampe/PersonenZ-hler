package de.personenzaehler.mobile.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import de.personenzaehler.mobile.data.DeviceNetworkState
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import java.net.Inet4Address

class NetworkMonitor(context: Context) {
    private val appContext = context.applicationContext
    private val connectivityManager = appContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager

    fun states(): Flow<DeviceNetworkState> = callbackFlow {
        fun sendSnapshot(network: Network? = connectivityManager.activeNetwork) {
            trySend(snapshot(network))
        }

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = sendSnapshot(network)
            override fun onLost(network: Network) = sendSnapshot(connectivityManager.activeNetwork)
            override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) = sendSnapshot(network)
            override fun onLinkPropertiesChanged(network: Network, linkProperties: LinkProperties) = sendSnapshot(network)
        }

        sendSnapshot()
        connectivityManager.registerDefaultNetworkCallback(callback)
        awaitClose { runCatching { connectivityManager.unregisterNetworkCallback(callback) } }
    }

    private fun snapshot(network: Network?): DeviceNetworkState {
        val capabilities = network?.let { connectivityManager.getNetworkCapabilities(it) }
        val linkProperties = network?.let { connectivityManager.getLinkProperties(it) }
        val wifiInfo = wifiManager?.connectionInfo
        return DeviceNetworkState(
            available = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true,
            validated = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true,
            transport = capabilities.transportLabel(),
            ssid = wifiInfo?.ssid.cleanWifiValue(),
            bssid = wifiInfo?.bssid.cleanWifiValue(),
            ipAddress = linkProperties?.linkAddresses
                ?.mapNotNull { it.address as? Inet4Address }
                ?.firstOrNull()
                ?.hostAddress,
            lastChangedMillis = System.currentTimeMillis(),
        )
    }

    private fun NetworkCapabilities?.transportLabel(): String {
        if (this == null) return "N/A"
        return when {
            hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WLAN"
            hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Mobilfunk"
            hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "VPN"
            else -> "Netzwerk"
        }
    }

    private fun String?.cleanWifiValue(): String? {
        val value = this?.trim()?.trim('"') ?: return null
        return value.takeUnless { it.isBlank() || it == "00:00:00:00:00:00" || it == "<unknown ssid>" }
    }
}
