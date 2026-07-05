package de.personenzaehler.mobile.network

class ReconnectBackoff(
    private val initialMillis: Long = 1_000,
    private val maxMillis: Long = 30_000,
) {
    private var current = initialMillis

    fun nextDelayMillis(): Long {
        val result = current
        current = (current * 2).coerceAtMost(maxMillis)
        return result
    }

    fun reset() {
        current = initialMillis
    }
}
