package de.personenzaehler.mobile.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackoffTest {
    @Test
    fun backoffDoublesAndCaps() {
        val backoff = ReconnectBackoff(initialMillis = 100, maxMillis = 250)
        assertEquals(100, backoff.nextDelayMillis())
        assertEquals(200, backoff.nextDelayMillis())
        assertEquals(250, backoff.nextDelayMillis())
        backoff.reset()
        assertEquals(100, backoff.nextDelayMillis())
    }

    @Test
    fun hostValidatorAllowsOnlyLocalHttpsTargets() {
        assertTrue(HostValidator.isAllowed("https", "10.0.0.5"))
        assertTrue(HostValidator.isAllowed("https", "raspberrypi.local"))
        assertFalse(HostValidator.isAllowed("http", "10.0.0.5"))
        assertFalse(HostValidator.isAllowed("https", "example.com"))
        assertFalse(HostValidator.isAllowed("https", "8.8.8.8"))
    }
}
