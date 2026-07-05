package de.personenzaehler.mobile.network

object HostValidator {
    fun isAllowed(settingsScheme: String, host: String): Boolean {
        val normalized = host.trim().lowercase()
        if (normalized.isBlank()) return false
        if (settingsScheme == "https") return true
        if (normalized == "localhost" || normalized.endsWith(".local") || normalized.endsWith(".lan") || normalized.endsWith(".fritz.box")) return true
        if (!normalized.contains(".")) return true
        val parts = normalized.split(".").mapNotNull { it.toIntOrNull() }
        if (parts.size != 4 || parts.any { it !in 0..255 }) return false
        return parts[0] == 10 ||
            parts[0] == 127 ||
            (parts[0] == 172 && parts[1] in 16..31) ||
            (parts[0] == 192 && parts[1] == 168)
    }
}
