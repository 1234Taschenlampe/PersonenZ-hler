package de.personenzaehler.mobile.util

import java.text.DateFormat
import java.util.Date
import java.util.Locale

fun formatInt(value: Int?): String = value?.toString() ?: "N/A"

fun formatDouble(value: Double?, suffix: String = "", decimals: Int = 1): String {
    if (value == null) return "N/A"
    return "%.${decimals}f%s".format(Locale.US, value, suffix)
}

fun formatBytes(value: Long?): String {
    if (value == null) return "N/A"
    val units = listOf("B", "KB", "MB", "GB", "TB")
    var current = value.toDouble()
    var unit = 0
    while (current >= 1024.0 && unit < units.lastIndex) {
        current /= 1024.0
        unit += 1
    }
    return "%.1f %s".format(Locale.US, current, units[unit])
}

fun formatEpochSeconds(value: Double?): String {
    if (value == null) return "N/A"
    return DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM)
        .format(Date((value * 1000).toLong()))
}

fun formatDuration(seconds: Double?): String {
    if (seconds == null) return "N/A"
    val total = seconds.toLong().coerceAtLeast(0)
    val days = total / 86_400
    val hours = (total % 86_400) / 3_600
    val minutes = (total % 3_600) / 60
    val secs = total % 60
    return if (days > 0) {
        "%d Tage %02d:%02d:%02d".format(days, hours, minutes, secs)
    } else {
        "%02d:%02d:%02d".format(hours, minutes, secs)
    }
}

fun isStale(lastSuccessMillis: Long?, nowMillis: Long, maxAgeMillis: Long): Boolean =
    lastSuccessMillis == null || nowMillis - lastSuccessMillis > maxAgeMillis
