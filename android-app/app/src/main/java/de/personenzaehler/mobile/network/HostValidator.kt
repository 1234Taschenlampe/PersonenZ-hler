package de.personenzaehler.mobile.network

object HostValidator {
    fun isAllowed(settingsScheme: String, host: String): Boolean {
        if (settingsScheme.lowercase() != "https") return false
        val normalized = host.trim().lowercase().removePrefix("[").removeSuffix("]")
        if (normalized.isBlank() || normalized.contains('/') || normalized.contains('@')) return false
        if (normalized == "localhost" || normalized == "::1") return true
        if (normalized.endsWith(".local") || normalized.endsWith(".lan") || normalized.endsWith(".fritz.box")) return true
        if (!normalized.contains(".")) return normalized.all { it.isLetterOrDigit() || it == '-' }
        val parts = normalized.split(".").mapNotNull { it.toIntOrNull() }
        if (parts.size != 4 || parts.any { it !in 0..255 }) return false
        return parts[0] == 10 ||
            parts[0] == 127 ||
            (parts[0] == 169 && parts[1] == 254) ||
            (parts[0] == 172 && parts[1] in 16..31) ||
            (parts[0] == 192 && parts[1] == 168)
    }
}
