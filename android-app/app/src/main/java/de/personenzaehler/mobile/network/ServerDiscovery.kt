package de.personenzaehler.mobile.network

import android.content.Context
import android.net.wifi.WifiManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

data class DiscoveredServer(val name: String, val host: String, val port: Int)

class ServerDiscovery(context: Context) {
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    private val serviceTypes = listOf("_personenzaehler._tcp.")

    fun discover(): Flow<DiscoveredServer> = callbackFlow {
        val multicastLock = wifiManager?.createMulticastLock("personenzaehler-nsd").also {
            it?.setReferenceCounted(false)
            it?.acquire()
        }
        val listeners = serviceTypes.map { expectedType ->
            object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(serviceType: String) = Unit
                override fun onDiscoveryStopped(serviceType: String) = Unit
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
                override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
                override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                    if (serviceInfo.serviceType != expectedType) return
                    nsdManager.resolveService(
                        serviceInfo,
                        object : NsdManager.ResolveListener {
                            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
                            override fun onServiceResolved(resolved: NsdServiceInfo) {
                                val host = resolved.host?.hostAddress ?: return
                                val port = resolved.port.takeIf { it > 0 } ?: 8766
                                trySend(DiscoveredServer(resolved.serviceName, host, port))
                            }
                        },
                    )
                }
            }
        }
        listeners.zip(serviceTypes).forEach { (listener, type) ->
            nsdManager.discoverServices(type, NsdManager.PROTOCOL_DNS_SD, listener)
        }
        awaitClose {
            listeners.forEach { listener -> runCatching { nsdManager.stopServiceDiscovery(listener) } }
            runCatching { multicastLock?.release() }
        }
    }
}
